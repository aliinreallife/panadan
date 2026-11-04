"""Operator-only full-fidelity Odoo mirror pilot (never auto-started).

Separate from the legacy eight-field pilot and its source/cursors. Reads only
the approved source view; writes only to an explicitly enabled owned PG18 source
via the existing restricted DSN. No scheduler, HTTP endpoint, deletion, or
dashboard cutover. NOT production-approved by virtue of being merged.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import sys

from . import database, odoo_full_mirror_adapter as full
from . import odoo_sync_pilot as guarded
from .platform_ingest import checkpoint, ingest_batch, _validate_events

SOURCE_KEY = 'odoo_calls_full_v1'
BACKFILL_STREAM = 'id_backfill_and_new'
UPDATES_STREAM = 'updated_at'
REQUIRED_ACKS = guarded.REQUIRED_ACKS + ('ack_sensitive_data',)


def require_approval(args):
    if not all(getattr(args, name, False) is True for name in REQUIRED_ACKS):
        raise ValueError('Full mirror write requires explicit source, retention, copy and sensitive-data approval')
    if args.mode != 'utc_naive' or not 1 <= args.batch_size <= 100 or args.max_pages != 1:
        raise ValueError('Full mirror pilot is restricted to one page of at most 100 records')


def local_status(target):
    row = target.execute(
        'SELECT enabled FROM panadan_ingest.sources WHERE source_key=%s',
        (SOURCE_KEY,),
    ).fetchone()
    record_count = target.execute(
        'SELECT count(*) AS n FROM panadan_ingest.source_records WHERE source_key=%s AND is_deleted=FALSE',
        (SOURCE_KEY,),
    ).fetchone()['n']
    revision_count = target.execute(
        'SELECT count(*) AS n FROM panadan_ingest.raw_revisions WHERE source_key=%s',
        (SOURCE_KEY,),
    ).fetchone()['n']
    return {
        'source_registered': row is not None,
        'source_enabled': bool(row and row['enabled']),
        'local_records': record_count,
        'local_revisions': revision_count,
        'update_cursor_seeded': checkpoint(
            target, source_key=SOURCE_KEY, stream=UPDATES_STREAM) is not None,
        'id_cursor_started': checkpoint(
            target, source_key=SOURCE_KEY, stream=BACKFILL_STREAM) is not None,
    }


def preview(*, limit: int = 100):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('Preview limit must be 1..100')
    with database.connect() as source:
        full.validate_schema(source)
        events = full.read_id_page(source, after_id=0, limit=limit)
    sizes = [
        len(json.dumps(entry.payload, sort_keys=True, ensure_ascii=False,
                       allow_nan=False, separators=(',', ':')).encode('utf-8'))
        for _, _, entry in events
    ]
    return {
        'fields': len(full.COLUMN_NAMES), 'rows_examined': len(events),
        'max_payload_bytes': max(sizes, default=0),
        'over_2mb': sum(n > 2_000_000 for n in sizes),
        'source_is_read_only': True, 'target_unchanged': True,
    }


def verify_sample(source, target, *, limit: int):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('Invalid parity sample size')
    full.validate_schema(source)
    rows = full.read_id_page(source, after_id=0, limit=limit)
    expected = {event.external_id: digest for event, digest in
                _validate_events([event for _, _, event in rows])}
    known = target.execute(
        'SELECT external_id, current_digest FROM panadan_ingest.source_records '
        'WHERE source_key=%s AND external_id = ANY(%s) AND is_deleted=FALSE',
        (SOURCE_KEY, list(expected)),
    ).fetchall() if expected else []
    present = {item['external_id']: item['current_digest'] for item in known}
    missing = sum(k not in present for k in expected)
    different = sum(k in present and present[k] != digest
                    for k, digest in expected.items())
    return {
        'examined': len(rows), 'matched': len(rows) - missing - different,
        'missing': missing, 'different': different,
        'all_match': not missing and not different,
    }


def _seed(source, target):
    full.validate_schema(source)
    if checkpoint(target, source_key=SOURCE_KEY, stream=BACKFILL_STREAM) is not None:
        raise ValueError('Cannot seed after backfill began')
    if checkpoint(target, source_key=SOURCE_KEY, stream=UPDATES_STREAM) is not None:
        raise ValueError('Update cursor already seeded')
    start = full.initial_change_cursor(full.source_upper_bound(source))
    ingest_batch(target, source_key=SOURCE_KEY, stream=UPDATES_STREAM,
                 events=[], expected_cursor=None, next_cursor=start)
    return {'operation': 'seed', 'cursor_stored': True}


def _backfill(source, target, *, limit):
    full.validate_schema(source)
    seeded = checkpoint(target, source_key=SOURCE_KEY, stream=UPDATES_STREAM)
    if seeded is None or seeded.get('marker') != full.MARKER:
        raise ValueError('Seed the full mirror update cursor first')
    before = checkpoint(target, source_key=SOURCE_KEY, stream=BACKFILL_STREAM)
    if before is not None and (
        set(before) != {'last_id'} or
        type(before['last_id']) is not int or before['last_id'] < 0
    ):
        raise ValueError('Invalid ID checkpoint')
    rows = full.read_id_page(
        source, after_id=0 if before is None else before['last_id'], limit=limit)
    after = full.id_next_cursor(rows, before)
    result = ingest_batch(
        target, source_key=SOURCE_KEY, stream=BACKFILL_STREAM,
        events=[event for _, _, event in rows],
        expected_cursor=before, next_cursor=after)
    return {
        'operation': 'backfill', 'examined': result.examined,
        'changed': result.upserted, 'unchanged': result.unchanged,
        'more': len(rows) == limit,
    }


def _updates(source, target, *, limit):
    full.validate_schema(source)
    before = checkpoint(target, source_key=SOURCE_KEY, stream=UPDATES_STREAM)
    if before is None or before.get('marker') != full.MARKER:
        raise ValueError('Seed the full mirror update cursor first')
    window = full.plan_change_window(before, full.source_upper_bound(source))
    if window is None:
        return {'operation': 'updates', 'examined': 0, 'changed': 0, 'more': False}
    low, high, pos = window
    rows = full.read_change_page(
        source, lower=low, upper=high, position=pos, limit=limit)
    after = full.change_next_cursor(before, window, rows, limit)
    result = ingest_batch(
        target, source_key=SOURCE_KEY, stream=UPDATES_STREAM,
        events=[event for _, _, event in rows],
        expected_cursor=before, next_cursor=after)
    return {
        'operation': 'updates', 'examined': result.examined,
        'changed': result.upserted, 'unchanged': result.unchanged,
        'more': len(rows) == limit,
    }


def apply(args):
    require_approval(args)
    with guarded.owned_connection() as target:
        with guarded.exclusive_pilot(target):
            # Confirm explicitly registered and ENABLED separate mirror source
            # before querying source payloads; the restricted writer has no
            # right to register/enable it.
            source = target.execute(
                'SELECT enabled FROM panadan_ingest.sources WHERE source_key=%s',
                (SOURCE_KEY,),
            ).fetchone()
            if not source or not source['enabled']:
                raise ValueError('Full mirror source is not explicitly enabled')
            with database.connect() as source_conn:
                if args.command == 'seed':
                    return _seed(source_conn, target)
                if args.command == 'backfill':
                    return _backfill(source_conn, target, limit=args.batch_size)
                if args.command == 'updates':
                    return _updates(source_conn, target, limit=args.batch_size)
                raise ValueError('Unknown mirror operation')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=('status', 'preview', 'verify', 'seed', 'backfill', 'updates'))
    p.add_argument('--batch-size', type=int, default=100)
    p.add_argument('--max-pages', type=int, default=1)
    p.add_argument('--mode', choices=('utc_naive',), default='utc_naive')
    for name in REQUIRED_ACKS:
        p.add_argument('--' + name.replace('_', '-'), action='store_true')
    args = p.parse_args(argv)
    try:
        if args.command == 'preview':
            print('FULL MIRROR PREVIEW:', preview(limit=args.batch_size))
        elif args.command == 'status':
            with guarded.owned_connection() as target:
                print('FULL MIRROR STATUS:', local_status(target))
        elif args.command == 'verify':
            with guarded.owned_connection() as target:
                with database.connect() as source:
                    print('FULL MIRROR PARITY:', verify_sample(
                        source, target, limit=args.batch_size))
        else:
            print('FULL MIRROR PILOT:', apply(args))
        return 0
    except Exception as exc:
        # No database exceptions, source payloads, connection strings or IDs.
        state = getattr(exc, 'sqlstate', None)
        state = state if isinstance(state, str) and len(state) == 5 and state.isalnum() else 'unknown'
        print('FULL MIRROR PILOT FAILED: '
              f'{type(exc).__name__} SQLSTATE={state}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
