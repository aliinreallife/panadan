"""Disabled-by-default, loss-aware full-field Odoo reporting-view reader.

No scheduling, target writes, source mutations or auto-delete operation.
This is *not* production-enabled; it only implements a fixed, strictly checked
37-column source contract and bounded row readers for a future guarded pilot.

The production source exposes an ordinary reporting VIEW, not a change feed.
The view owner must verify ID uniqueness and joined-data write_date semantics
before any continuous sync can be considered reliable.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import json
import math
from typing import Any

from . import database, odoo_sync_adapter as existing
from .platform_ingest import SourceEvent

# Explicit observed metadata, 2026-11-04. Any drift requires code review.
# Keep this in the actual reported SELECT order; never dynamically SELECT *.
COLUMN_TYPES = (
    ('id', 'integer'),
    ('CALLDATE', 'date'),
    ('call_id', 'text'),
    ('tellstate', 'character varying'),
    ('tellside', 'character varying'),
    ('customername', 'character varying'),
    ('customertell', 'character varying'),
    ('tellnum', 'double precision'),
    ('voice_length', 'double precision'),
    ('call_time', 'integer'),
    ('aicallinfostate', 'character varying'),
    ('create_date', 'timestamp without time zone'),
    ('possibility_of_sale_ai', 'integer'),
    ('outcome', 'character varying'),
    ('ai_recommendation', 'character varying'),
    ('summary', 'character varying'),
    ('tell_state_desc', 'character varying'),
    ('vw_danix_base_info_users_userinfo', 'character varying'),
    ('vw_danix_base_info_users_name', 'character varying'),
    ('vw_danix_base_info_users', 'integer'),
    ('vw_how_to_know_name', 'character varying'),
    ('how_to_know_id', 'integer'),
    ('pipeline_expert_id', 'integer'),
    ('stage_id', 'integer'),
    ('vw_followup_stage_name', 'character varying'),
    ('team_id', 'integer'),
    ('crm_team_name', 'jsonb'),
    ('crm_team_user_id', 'integer'),
    ('crm_team_user_name', 'character varying'),
    ('invoiced_target', 'double precision'),
    ('deal_value', 'double precision'),
    ('currency_id', 'integer'),
    ('vw_res_currency_name', 'character varying'),
    ('vw_res_currency_full_name', 'character varying'),
    ('REFRECIDAICALLINFO', 'character varying'),
    ('transcription', 'text'),
    ('write_date', 'timestamp without time zone'),
)
COLUMN_NAMES = tuple(name for name, _ in COLUMN_TYPES)
COLUMN_TYPE_MAP = dict(COLUMN_TYPES)
MARKER = 'write_date'
VIEW = database.VIEW
# The source view is currently reported to return nullable metadata for all
# columns. Rely on runtime validation of required id/marker values instead.
SCHEMA_SQL = '''
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = %s AND table_name = %s
ORDER BY ordinal_position
'''
SELECT_COLUMNS = ', '.join('"' + name + '"' for name in COLUMN_NAMES)
# SQL identifiers are all hard-coded, reviewed identifiers, never user input.
ID_SQL = (f'SELECT {SELECT_COLUMNS} FROM {VIEW} '
          'WHERE id > %s ORDER BY id ASC LIMIT %s')
CHANGE_SQL = (f'SELECT {SELECT_COLUMNS} FROM {VIEW} '
              f'WHERE "{MARKER}" >= %s AND "{MARKER}" <= %s '
              f'AND ("{MARKER}", id) > (%s, %s) '
              f'ORDER BY "{MARKER}" ASC, id ASC LIMIT %s')


def validate_schema(source_conn, *, mode: str = 'utc_naive') -> str:
    """Reject unexpected view columns/types/order before reading payloads."""
    if mode != 'utc_naive':
        raise ValueError('The observed full mirror contract requires UTC-naive write_date')
    schema, view = VIEW.split('.', 1)
    rows = source_conn.execute(SCHEMA_SQL, (schema, view)).fetchall()
    observed = tuple((r['column_name'], r['data_type']) for r in rows)
    if observed != COLUMN_TYPES:
        # Never log customer values or arbitrary SQL metadata on failure.
        raise RuntimeError('Odoo full mirror schema drift; review before resuming')
    return MARKER


def _jsonb(value: Any) -> Any:
    """Accept only genuinely JSON-compatible values; preserve nested shapes."""
    def keys_are_strings(obj: Any) -> bool:
        if isinstance(obj, dict):
            return all(isinstance(k, str) and keys_are_strings(v) for k, v in obj.items())
        if isinstance(obj, list):
            return all(keys_are_strings(v) for v in obj)
        return obj is None or isinstance(obj, (str, bool, int, float)) and (
            not isinstance(obj, float) or math.isfinite(obj)
        )

    if not keys_are_strings(value):
        raise ValueError('Unsupported nested JSONB source type')
    try:
        # Reparse to produce a detached JSON-only tree; rejects accidental NaN.
        return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError, OverflowError, RecursionError):
        raise ValueError('Unsupported JSONB source value') from None


def _normal_value(name: str, value: Any) -> Any:
    """Serialize source types without truncation or timezone coercion."""
    if value is None:
        return None
    kind = COLUMN_TYPE_MAP[name]
    if kind in ('integer',):
        if type(value) is not int:
            raise ValueError('Unexpected integer source type')
        return value
    if kind in ('text', 'character varying'):
        if not isinstance(value, str):
            raise ValueError('Unexpected text source type')
        return value
    if kind == 'date':
        if type(value) is not date:
            raise ValueError('Unexpected date source type')
        return value.isoformat()
    if kind == 'timestamp without time zone':
        if type(value) is not datetime or value.tzinfo is not None:
            raise ValueError('Unexpected timestamp source type')
        # Preserve naive source representation exactly at microsecond precision.
        return value.isoformat(timespec='microseconds')
    if kind == 'double precision':
        # PostgreSQL float8 values are Python floats; reject NaN/Infinity
        # rather than silently converting to JSON null or another number.
        if type(value) is not float or not math.isfinite(value):
            raise ValueError('Unexpected floating-point source value')
        return value
    if kind == 'jsonb':
        return _jsonb(value)
    raise ValueError('Unrecognized source type')


def normalized(row: dict, *, mode: str = 'utc_naive') -> tuple[int, datetime, SourceEvent]:
    if mode != 'utc_naive' or not isinstance(row, dict) or set(row) != set(COLUMN_NAMES):
        raise ValueError('Unexpected full mirror source row shape')
    identity = row['id']
    if type(identity) is not int or identity <= 0:
        raise ValueError('Missing or invalid source identity')
    when = row[MARKER]
    if type(when) is not datetime or when.tzinfo is not None:
        raise ValueError('Missing or invalid source update timestamp')
    payload = {name: _normal_value(name, row[name]) for name in COLUMN_NAMES}
    # UTC semantics are used ONLY for incremental cursor arithmetic. The raw
    # naive write_date and create_date values remain unchanged in the payload.
    updated = when.replace(tzinfo=timezone.utc)
    return identity, updated, SourceEvent(str(identity), 'upsert', payload)


def read_id_page(source_conn, *, after_id: int, limit: int = 100,
                 mode: str = 'utc_naive', marker: str = MARKER):
    existing._limit(limit)
    if type(after_id) is not int or after_id < 0 or marker != MARKER:
        raise ValueError('Invalid full mirror ID page arguments')
    rows = source_conn.execute(ID_SQL, (after_id, limit)).fetchall()
    events = [normalized(row, mode=mode) for row in rows]
    previous = after_id
    for identity, _, _ in events:
        if identity <= previous:
            raise ValueError('Non-unique or unordered source IDs')
        previous = identity
    return events


def read_change_page(source_conn, *, lower: datetime, upper: datetime,
                     position: tuple[datetime, int], limit: int = 100,
                     mode: str = 'utc_naive', marker: str = MARKER):
    existing._limit(limit)
    if marker != MARKER or type(position[1]) is not int or position[1] < 0:
        raise ValueError('Invalid full mirror change page arguments')
    lo, hi, at = existing._utc(lower), existing._utc(upper), existing._utc(position[0])
    if hi < lo or not lo <= at <= hi:
        raise ValueError('Invalid change window')
    rows = source_conn.execute(
        CHANGE_SQL, (existing._source_param(lo, 'utc_naive'),
                     existing._source_param(hi, 'utc_naive'),
                     existing._source_param(at, 'utc_naive'), position[1], limit),
    ).fetchall()
    events = [normalized(row, mode=mode) for row in rows]
    previous = (at, position[1])
    for identity, updated, _ in events:
        if not lo <= updated <= hi or (updated, identity) <= previous:
            raise ValueError('Non-monotonic full mirror changes')
        previous = (updated, identity)
    return events


def source_upper_bound(source_conn):
    return existing.source_upper_bound(source_conn)


def initial_change_cursor(source_clock: datetime, *, marker: str = MARKER):
    if marker != MARKER:
        raise ValueError('Unexpected source update marker')
    return existing.initial_change_cursor(source_clock, marker=marker)


def id_next_cursor(rows, previous):
    return existing.id_next_cursor(rows, previous)


def plan_change_window(cursor, source_now):
    return existing.plan_change_window(cursor, source_now)


def change_next_cursor(cursor, window, rows, limit):
    return existing.change_next_cursor(cursor, window, rows, limit)
