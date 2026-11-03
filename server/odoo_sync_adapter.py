"""Read-only, *disabled by default* Odoo report-view polling adapter.

Three logical flows share two safe queries:
- initial backfill by id, in bounded keyset pages
- new rows by id (same cursor, polled after backfill)
- changed existing rows by (verified timestamp marker, id) in bounded windows

No connection credentials, scheduling, source writes or live data migration.
Source model owners must confirm stable IDs, update coverage and timestamp
semantics before enabling any live sync. Only explicitly approved, non-sensitive
fields are read. Deleted IDs cannot be inferred from this adapter.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

from . import database
from .platform_ingest import SourceEvent

VIEW = database.VIEW  # fixed SQL identifier, never taken from user input
UPDATE_COLUMN = 'sync_updated_at'  # backwards-compatible default for existing tests/cursors
# Source-owned whole-view markers take precedence. Real Odoo view currently
# exposes write_date (UTC-naive), subject to operator verification of edits.
# Never dynamically interpolate untrusted SQL or silently switch a saved cursor.
UPDATE_COLUMNS = ('sync_updated_at', 'updated_at', 'write_date')
DATA_COLUMNS = (
    'id', 'CALLDATE', 'tellstate', 'tellside', 'aicallinfostate',
    'voice_length', 'possibility_of_sale_ai', 'deal_value',
)
COLUMNS = DATA_COLUMNS + (UPDATE_COLUMN,)
# Only hardcoded, reviewed identifiers can appear in SQL. Never use an
# arbitrary source-column name or request parameter to construct SQL.
SELECT_COLUMNS_BY_MARKER = {
    marker: ', '.join('"' + name + '"' for name in DATA_COLUMNS + (marker,))
    for marker in UPDATE_COLUMNS
}
SELECT_COLUMNS = SELECT_COLUMNS_BY_MARKER[UPDATE_COLUMN]
PAGE_MIN, PAGE_MAX = 1, 200
OVERLAP = timedelta(minutes=5)
SAFETY_DELAY = timedelta(seconds=60)
TIMESTAMP_TYPES = {'timestamp with time zone', 'timestamp without time zone'}

SCHEMA_SQL = """
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = %s AND table_name = %s
"""
SOURCE_CLOCK_SQL = 'SELECT clock_timestamp() AS source_now'
ID_SQL_BY_MARKER = {
    marker: (f'SELECT {columns} FROM {VIEW} '
             'WHERE id > %s ORDER BY id ASC LIMIT %s')
    for marker, columns in SELECT_COLUMNS_BY_MARKER.items()
}
# The row-value comparison guarantees same-timestamp pagination does not skip
# any IDs. Fixed inclusive bound supports overlap re-reading.
CHANGE_SQL_BY_MARKER = {
    marker: (f'SELECT {columns} FROM {VIEW} '
             f'WHERE "{marker}" >= %s AND "{marker}" <= %s '
             f'AND ("{marker}", id) > (%s, %s) '
             f'ORDER BY "{marker}" ASC, id ASC LIMIT %s')
    for marker, columns in SELECT_COLUMNS_BY_MARKER.items()
}
ID_SQL = ID_SQL_BY_MARKER[UPDATE_COLUMN]
CHANGE_SQL = CHANGE_SQL_BY_MARKER[UPDATE_COLUMN]
# Could be faster with source indexes; no indexes/DDL are created in Odoo.


def _limit(value: int) -> int:
    if type(value) is not int or not PAGE_MIN <= value <= PAGE_MAX:
        raise ValueError('Page size must be 1..200')
    return value


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError('Expected timestamp')
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('Expected timezone-aware UTC timestamp')
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _utc(value).isoformat(timespec='microseconds')


def _parse(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError('Invalid timestamp cursor')
    try:
        return _utc(datetime.fromisoformat(value.replace('Z', '+00:00')))
    except (ValueError, TypeError) as exc:
        raise ValueError('Invalid timestamp cursor') from None


def _source_param(value: datetime, mode: Literal['utc_naive', 'timestamptz']):
    instant = _utc(value)
    return instant.replace(tzinfo=None) if mode == 'utc_naive' else instant


def _source_time(value: datetime, mode: Literal['utc_naive', 'timestamptz']) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError('Invalid source update timestamp')
    if mode == 'utc_naive':
        if value.tzinfo is not None:
            raise ValueError('Expected Odoo UTC-naive source timestamp')
        return value.replace(tzinfo=timezone.utc)
    return _utc(value)


def validate_schema(source_conn, *, mode: Literal['utc_naive', 'timestamptz']) -> str:
    if mode not in ('utc_naive', 'timestamptz'):
        raise ValueError('Source timestamp mode must be explicitly configured')
    schema, table = VIEW.split('.', 1)
    rows = source_conn.execute(SCHEMA_SQL, (schema, table)).fetchall()
    columns = {row['column_name']: row['data_type'] for row in rows}
    markers = [name for name in UPDATE_COLUMNS if name in columns]
    if not set(DATA_COLUMNS) <= columns.keys() or not markers:
        raise RuntimeError('Odoo view lacks required allowlisted sync columns')
    # Prefer source-owned whole-view change marker when both are present.
    marker = markers[0]
    expected_type = ('timestamp without time zone' if mode == 'utc_naive'
                     else 'timestamp with time zone')
    if columns[marker] != expected_type:
        raise RuntimeError('Odoo sync timestamp type does not match configured mode')
    if columns['id'] not in ('integer', 'bigint'):
        raise RuntimeError('Odoo source ID must be an integer')
    if columns[marker] not in TIMESTAMP_TYPES:
        raise RuntimeError('Odoo source timestamp must be a PostgreSQL timestamp')
    return marker


def source_upper_bound(source_conn) -> datetime:
    """Capture source DB clock, subtract settling delay in coordinator."""
    row = source_conn.execute(SOURCE_CLOCK_SQL).fetchone()
    return _utc(row['source_now'])


def _normalized(row: dict, *, mode: Literal['utc_naive', 'timestamptz'],
                marker: str = UPDATE_COLUMN) -> tuple[int, datetime, SourceEvent]:
    if marker not in UPDATE_COLUMNS:
        raise ValueError('Unsupported source marker')
    if not isinstance(row, dict) or set(row) != set(DATA_COLUMNS + (marker,)):
        raise ValueError('Unexpected source columns')
    record_id = row['id']
    if type(record_id) is not int or record_id < 1:
        raise ValueError('Invalid Odoo record ID')
    updated = _source_time(row[marker], mode)
    payload = {}
    for key in DATA_COLUMNS:
        if key == 'id':
            continue
        value = row[key]
        if isinstance(value, (datetime, date)):
            value = value.isoformat()
        elif isinstance(value, Decimal):
            value = str(value)
        if value is not None and not isinstance(value, (str, float, int, bool)):
            raise ValueError('Unexpected source field type')
        payload[key] = value
    payload['id'] = record_id
    # Keep source event time as metadata so local hash reflects changes in
    # update marker, but never guess any business semantics from it.
    payload[marker] = _iso(updated)
    return record_id, updated, SourceEvent(str(record_id), 'upsert', payload)


def read_id_page(source_conn, *, after_id: int, limit: int = 100,
                 mode: Literal['utc_naive', 'timestamptz'],
                 marker: str = UPDATE_COLUMN) -> list[tuple[int, datetime, SourceEvent]]:
    _limit(limit)
    if type(after_id) is not int or after_id < 0:
        raise ValueError('Invalid ID checkpoint')
    if marker not in ID_SQL_BY_MARKER:
        raise ValueError('Unsupported source marker')
    rows = source_conn.execute(ID_SQL_BY_MARKER[marker], (after_id, limit)).fetchall()
    values = [_normalized(row, mode=mode, marker=marker) for row in rows]
    last = after_id
    for record_id, _, _ in values:
        if record_id <= last:
            raise ValueError('Source IDs are not strictly increasing or unique')
        last = record_id
    return values


def read_change_page(source_conn, *, lower: datetime, upper: datetime,
                     position: tuple[datetime, int], limit: int = 100,
                     mode: Literal['utc_naive', 'timestamptz'],
                     marker: str = UPDATE_COLUMN) -> list[tuple[int, datetime, SourceEvent]]:
    _limit(limit)
    if type(position[1]) is not int or position[1] < 0:
        raise ValueError('Invalid change ID checkpoint')
    lo, hi, at = _utc(lower), _utc(upper), _utc(position[0])
    if hi < lo or at < lo or at > hi:
        raise ValueError('Invalid change window')
    if marker not in CHANGE_SQL_BY_MARKER:
        raise ValueError('Unsupported source marker')
    rows = source_conn.execute(
        CHANGE_SQL_BY_MARKER[marker],
        (_source_param(lo, mode), _source_param(hi, mode),
         _source_param(at, mode), position[1], limit),
    ).fetchall()
    values = [_normalized(row, mode=mode, marker=marker) for row in rows]
    previous = (at, position[1])
    for record_id, updated, _ in values:
        if updated < lo or updated > hi or (updated, record_id) <= previous:
            raise ValueError('Non-monotonic or out-of-range source changes')
        previous = (updated, record_id)
    return values


def initial_change_cursor(source_clock: datetime, *, marker: str = UPDATE_COLUMN) -> dict:
    """Seed *before* an ID backfill so concurrent source edits are not lost.

    Lower bound is deliberately earlier than backfill; later replay is safe.
    This does NOT establish that updates/deletes are reliably recorded.
    """
    if marker not in UPDATE_COLUMNS:
        raise ValueError('Unsupported source marker')
    return {'completed_through': _iso(_utc(source_clock) - SAFETY_DELAY),
            'marker': marker}


def id_next_cursor(rows: list[tuple[int, datetime, SourceEvent]],
                   previous: dict | None) -> dict | None:
    last_id = 0 if previous is None else previous.get('last_id')
    if type(last_id) is not int or last_id < 0:
        raise ValueError('Invalid ID cursor')
    if rows:
        if rows[0][0] <= last_id:
            raise ValueError('Invalid ID page ordering')
        return {'last_id': rows[-1][0]}
    return previous


def plan_change_window(cursor: dict, source_now: datetime, *,
                       overlap: timedelta = OVERLAP,
                       settle: timedelta = SAFETY_DELAY) -> tuple[datetime, datetime, tuple[datetime, int]] | None:
    """Continue the same frozen window across pages; never restart page 1.

    An overlap replays recent changes on the NEXT completed window, and
    digest-based ingestion avoids creating duplicate revisions.
    """
    if (not isinstance(cursor, dict) or 'completed_through' not in cursor
        or cursor.get('marker') not in UPDATE_COLUMNS):
        raise ValueError('Seed change cursor and source marker before initial ID backfill')
    completed = _parse(cursor['completed_through'])
    if overlap < timedelta(0) or settle < timedelta(0):
        raise ValueError('Invalid window timing')
    active = cursor.get('window')
    if active is not None:
        if not isinstance(active, dict):
            raise ValueError('Invalid active window')
        low, upper = _parse(active['lower']), _parse(active['upper'])
        last_ts, last_id = _parse(active['last_ts']), active['last_id']
        if type(last_id) is not int or last_id < 0 or not low <= last_ts <= upper:
            raise ValueError('Invalid active window position')
        return low, upper, (last_ts, last_id)
    upper = _utc(source_now) - settle
    if upper <= completed:
        return None
    lower = completed - overlap
    return lower, upper, (lower, 0)


def change_next_cursor(cursor: dict, window: tuple[datetime, datetime, tuple[datetime, int]],
                       rows: list[tuple[int, datetime, SourceEvent]], limit: int) -> dict:
    _limit(limit)
    lower, upper, _ = window
    if len(rows) < limit:
        return {'completed_through': _iso(upper), 'marker': cursor['marker']}
    last_id, last_ts, _ = rows[-1]
    return {
        'completed_through': cursor['completed_through'],
        'marker': cursor['marker'],
        'window': {
            'lower': _iso(lower), 'upper': _iso(upper),
            'last_ts': _iso(last_ts), 'last_id': last_id,
        },
    }
