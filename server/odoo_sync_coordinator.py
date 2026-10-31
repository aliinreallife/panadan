"""Explicitly invoked, disabled-by-default Odoo sync page coordinator.

The Odoo source connection MUST be supplied by the reporting read-only
database.connect() context; the Panadan local connection MUST be a separate
authorized owned PostgreSQL connection (autocommit=True, dict_row).

No CLI/scheduler is connected: this never runs against live source data.
In production all streams for one source must be scheduled serially.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from . import odoo_sync_adapter as src
from .platform_ingest import BatchResult, SourceEvent, checkpoint, ingest_batch

ODOO_SOURCE_KEY = 'odoo_calls'
BACKFILL_STREAM = 'id_backfill_and_new'
UPDATES_STREAM = 'updated_at'
Mode = Literal['utc_naive', 'timestamptz']


@dataclass(frozen=True)
class SyncPageResult:
    stream: str
    examined: int
    changed: int
    skipped: int
    has_more: bool
    cursor: dict | None


def _result(stream: str, result: BatchResult, more: bool,
            cursor: dict | None) -> SyncPageResult:
    return SyncPageResult(stream, result.examined, result.upserted,
                          result.unchanged, more, cursor)


def seed_update_stream(source_conn, owned_conn, *, mode: Mode,
                       source_key: str = ODOO_SOURCE_KEY) -> dict:
    """Must run before first history import to capture concurrent changes.

    Requires an approved, explicitly enabled source. Cannot be used to reset
    an existing stream or to backfill an already-started ID import.
    """
    src.validate_schema(source_conn, mode=mode)
    if checkpoint(owned_conn, source_key=source_key, stream=BACKFILL_STREAM) is not None:
        raise ValueError('Cannot seed updates after ID import already started')
    if checkpoint(owned_conn, source_key=source_key, stream=UPDATES_STREAM) is not None:
        raise ValueError('Updates stream already seeded')
    seed = src.initial_change_cursor(src.source_upper_bound(source_conn))
    ingest_batch(
        owned_conn, source_key=source_key, stream=UPDATES_STREAM,
        events=[], expected_cursor=None, next_cursor=seed,
    )
    return seed


def poll_id_page(source_conn, owned_conn, *, mode: Mode, limit: int = 100,
                 source_key: str = ODOO_SOURCE_KEY) -> SyncPageResult:
    """Works for both initial backfill and future new IDs.

    Poll forever after the initial backfill: newly inserted rows with an ID
    larger than the saved cursor are fetched; existing row edits are fetched
    by the separate timestamp stream. Requires immutable monotonic source IDs.
    """
    src.validate_schema(source_conn, mode=mode)
    initial = checkpoint(owned_conn, source_key=source_key, stream=UPDATES_STREAM)
    if initial is None:
        raise ValueError('Seed update stream BEFORE initial ID import')
    before = checkpoint(owned_conn, source_key=source_key, stream=BACKFILL_STREAM)
    if before is not None and (set(before) != {'last_id'}
                               or type(before['last_id']) is not int
                               or before['last_id'] < 0):
        raise ValueError('Invalid existing ID checkpoint')
    last_id = 0 if before is None else before['last_id']
    rows = src.read_id_page(source_conn, after_id=last_id, limit=limit, mode=mode)
    after = src.id_next_cursor(rows, before)
    result = ingest_batch(
        owned_conn, source_key=source_key, stream=BACKFILL_STREAM,
        events=[entry for _, _, entry in rows],
        expected_cursor=before, next_cursor=after,
    )
    return _result(BACKFILL_STREAM, result, len(rows) == limit, after)


def poll_update_page(source_conn, owned_conn, *, mode: Mode, limit: int = 100,
                     source_key: str = ODOO_SOURCE_KEY) -> SyncPageResult:
    """Process one frozen timestamp+ID window page with overlap.

    No new-row data is missed purely due to a same-timestamp page boundary.
    Source times, upper bound and cursor are not derived from client clocks.
    """
    src.validate_schema(source_conn, mode=mode)
    before = checkpoint(owned_conn, source_key=source_key, stream=UPDATES_STREAM)
    if before is None:
        raise ValueError('Update cursor must be seeded before import')
    now = src.source_upper_bound(source_conn)
    window = src.plan_change_window(before, now)
    if window is None:
        return SyncPageResult(UPDATES_STREAM, 0, 0, 0, False, before)
    lower, upper, position = window
    rows = src.read_change_page(
        source_conn, lower=lower, upper=upper,
        position=position, mode=mode, limit=limit,
    )
    after = src.change_next_cursor(before, window, rows, limit)
    result = ingest_batch(
        owned_conn, source_key=source_key, stream=UPDATES_STREAM,
        events=[entry for _, _, entry in rows],
        expected_cursor=before, next_cursor=after,
    )
    return _result(UPDATES_STREAM, result, len(rows) == limit, after)
