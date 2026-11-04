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
SNAPSHOT_STREAM = 'view_reconciliation_v1'
REQUIRED_ACKS = guarded.REQUIRED_ACKS + ('ack_sensitive_data',)


def require_approval(args):
    if not all(getattr(args, name, False) is True for name in REQUIRED_ACKS):
        raise ValueError('Full mirror write requires explicit source, retention, copy and sensitive-data approval')
    if (args.mode != 'utc_naive' or type(args.batch_size) is not int
        or not 1 <= args.batch_size <= 100
        or type(args.max_pages) is not int
        or not 1 <= args.max_pages <= 10
        or (args.command != 'snapshot-run' and args.max_pages != 1)):
        raise ValueError('Mirror writes require 1..100 rows/page; snapshot-run permits at most 10 pages')


def local_status(target):
    row = target.execute(
        'SELECT enabled FROM panadan_ingest.sources WHERE source_key=%s',
        (SOURCE_KEY,),
    ).fetchone()
    snapshot = checkpoint(target, source_key=SOURCE_KEY, stream=SNAPSHOT_STREAM)
    record_count = target.execute(
        'SELECT count(*) AS n FROM panadan_ingest.source_records WHERE source_key=%s AND is_deleted=FALSE',
        (SOURCE_KEY,),
    ).fetchone()['n']
    revision_count = target.execute(
        'SELECT count(*) AS n FROM panadan_ingest.raw_revisions WHERE source_key=%s',
        (SOURCE_KEY,),
    ).fetchone()['n']
    sync_activity = target.execute(
        """SELECT COUNT(*) AS committed_pages,
                  EXTRACT(EPOCH FROM clock_timestamp()-MAX(finished_at)) AS age_seconds
           FROM panadan_ingest.sync_runs
           WHERE source_key=%s AND stream=%s""",
        (SOURCE_KEY, SNAPSHOT_STREAM),
    ).fetchone()
    processing = target.execute(
        """SELECT COUNT(*) FILTER (WHERE j.status='pending') AS pending,
                  COUNT(*) FILTER (WHERE j.status='failed') AS failed
           FROM panadan_ingest.processing_jobs AS j
           JOIN panadan_ingest.raw_revisions AS r ON r.revision_id=j.revision_id
           WHERE r.source_key=%s""",
        (SOURCE_KEY,),
    ).fetchone()
    return {
        'source_registered': row is not None,
        'source_enabled': bool(row and row['enabled']),
        'local_records': record_count,
        'local_revisions': revision_count,
        'committed_pages': int(sync_activity['committed_pages']),
        'seconds_since_last_commit': (
            int(sync_activity['age_seconds'])
            if sync_activity['age_seconds'] is not None else None),
        'processing_pending': int(processing['pending']),
        'processing_failed': int(processing['failed']),
        'completed_passes': (
            max(0, snapshot['pass'] - 1)
            if isinstance(snapshot, dict) and type(snapshot.get('pass')) is int
            else None),
        'update_cursor_seeded': checkpoint(
            target, source_key=SOURCE_KEY, stream=UPDATES_STREAM) is not None,
        'id_cursor_started': checkpoint(
            target, source_key=SOURCE_KEY, stream=BACKFILL_STREAM) is not None,
        'snapshot_pass': snapshot['pass'] if isinstance(snapshot, dict) else None,
        'snapshot_in_progress': bool(snapshot and snapshot.get('last_id', 0)),
    }


def preview(*, limit: int = 100):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('Preview limit must be 1..100')
    with database.connect() as source:
        full.validate_schema(source)
        events, more, source_rows = full.read_snapshot_page(source, after_id=0, limit=limit)
    sizes = [
        len(json.dumps(entry.payload, sort_keys=True, ensure_ascii=False,
                       allow_nan=False, separators=(',', ':')).encode('utf-8'))
        for entry in events
    ]
    return {
        'fields': len(full.COLUMN_NAMES), 'rows_examined': source_rows,
        'calls_examined': len(events), 'more': more,
        'multiple_row_calls': sum(len(e.payload['source_rows']) > 1 for e in events),
        'max_payload_bytes': max(sizes, default=0),
        'over_2mb': sum(n > 2_000_000 for n in sizes),
        'source_is_read_only': True, 'target_unchanged': True,
    }


def verify_sample(source, target, *, limit: int):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('Invalid parity sample size')
    full.validate_schema(source)
    events, _, _ = full.read_snapshot_page(source, after_id=0, limit=limit)
    expected = {event.external_id: digest for event, digest in
                _validate_events(events)}
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
        'examined': len(events), 'matched': len(events) - missing - different,
        'missing': missing, 'different': different,
        'all_match': not missing and not different,
    }




def _check_identity_reuse(target, events):
    """Refuse an existing call ID whose stable source identity was replaced.

    Neither call_id nor create_date is printed; legacy payloads must be
    explicitly migrated, never silently overwritten by the new envelope.
    """
    if not events:
        return
    keys = [event.external_id for event in events]
    rows = target.execute(
        """
        SELECT current.external_id, revision.payload
        FROM panadan_ingest.source_records AS current
        JOIN panadan_ingest.raw_revisions AS revision
          ON revision.source_key = current.source_key
         AND revision.external_id = current.external_id
         AND revision.revision_no = current.revision_no
        WHERE current.source_key = %s
          AND current.external_id = ANY(%s)
          AND current.is_deleted = FALSE
        """,
        (SOURCE_KEY, keys),
    ).fetchall()
    by_id = {event.external_id: event for event in events}
    for previous in rows:
        saved = previous['payload']
        incoming = by_id[previous['external_id']].payload
        if (
            not isinstance(saved, dict)
            or saved.get('source_schema') != 'odoo_view_37_v1'
            or not isinstance(saved.get('source_rows'), list)
            or not saved['source_rows']
        ):
            raise ValueError('Existing local source shape is incompatible')
        old = saved['source_rows'][0]
        new = incoming['source_rows'][0]
        if (old.get('call_id'), old.get('create_date')) != (
            new['call_id'], new['create_date']
        ):
            raise ValueError('Source call identity appears reused; refusing overwrite')


def _snapshot(source, target, *, limit):
    """One manual, checkpointed reconciliation page. Never tombstone absence."""
    full.validate_schema(source)
    if (checkpoint(target, source_key=SOURCE_KEY, stream=BACKFILL_STREAM) is not None
        or checkpoint(target, source_key=SOURCE_KEY, stream=UPDATES_STREAM) is not None):
        raise ValueError('Legacy full-mirror cursors require explicit migration')

    before = checkpoint(target, source_key=SOURCE_KEY, stream=SNAPSHOT_STREAM)
    if before is None:
        pass_number, after_id = 1, 0
    elif (
        not isinstance(before, dict) or set(before) != {'pass', 'last_id'}
        or type(before['pass']) is not int or before['pass'] < 1
        or type(before['last_id']) is not int or before['last_id'] < 0
    ):
        raise ValueError('Invalid reconciliation checkpoint')
    else:
        pass_number, after_id = before['pass'], before['last_id']

    events, more, source_rows = full.read_snapshot_page(
        source, after_id=after_id, limit=limit)
    _check_identity_reuse(target, events)
    if more:
        if not events:
            raise ValueError('Snapshot page made no progress')
        next_cursor = {'pass': pass_number, 'last_id': int(events[-1].external_id)}
    else:
        # Completed pass. The next manual invocation starts a new pass.
        next_cursor = {'pass': pass_number + 1, 'last_id': 0}
    result = ingest_batch(
        target, source_key=SOURCE_KEY, stream=SNAPSHOT_STREAM,
        events=events, expected_cursor=before, next_cursor=next_cursor)
    return {
        'operation': 'snapshot', 'pass': pass_number,
        'source_rows': source_rows, 'calls': result.examined,
        'changed': result.upserted, 'unchanged': result.unchanged,
        'more': more, 'pass_complete': not more,
    }



def _snapshot_run(source, target, *, limit: int, max_pages: int):
    """Supervised finite replay, stopping at the first completed pass.

    Commit each page with its cursor. A failed later page leaves earlier
    pages durable; the next invocation safely resumes. No timer or auto-loop.
    """
    if type(max_pages) is not int or not 1 <= max_pages <= 10:
        raise ValueError('Invalid manual snapshot-run page budget')
    totals = {'operation': 'snapshot-run', 'pages': 0,
              'source_rows': 0, 'calls': 0,
              'changed': 0, 'unchanged': 0, 'pass_complete': False}
    for _ in range(max_pages):
        part = _snapshot(source, target, limit=limit)
        if totals['pages'] == 0:
            totals['pass'] = part['pass']
        elif part['pass'] != totals['pass']:
            raise RuntimeError('Snapshot pass changed unexpectedly')
        totals['pages'] += 1
        for key in ('source_rows', 'calls', 'changed', 'unchanged'):
            totals[key] += part[key]
        totals['pass_complete'] = part['pass_complete']
        if part['pass_complete']:
            break
    return totals


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
                if args.command == 'snapshot':
                    return _snapshot(source_conn, target, limit=args.batch_size)
                if args.command == 'snapshot-run':
                    return _snapshot_run(
                        source_conn, target,
                        limit=args.batch_size, max_pages=args.max_pages)
                raise ValueError('Unknown mirror operation')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=('status', 'preview', 'verify', 'snapshot', 'snapshot-run'))
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
