"""Incremental complete-field Odoo mirror using only create_date and write_date.

A changed-id candidate query filters by the two available timestamps.
Every selected ID is then fetched as a complete group of all 37 view fields.
The ID is only a tie-breaker and mirror join key, never a new-call high-water
mark. The view may return multiple rows per ID; no row is dropped.

A frozen bounded timestamp window and keyset position live in a separate
atomic staging checkpoint. A bounded overlap catches delayed writes. This
cannot detect changes whose create_date/write_date are unchanged, source IDs
that change identity, or records that vanish entirely from the view.
No full-view scans, source writes, deletion, scheduling or backups here.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
import sys

from . import database, odoo_full_mirror_adapter as full
from . import odoo_full_mirror_pilot as pilot
from . import odoo_mirror_target as target
from . import odoo_mirror_transfer as wire
from . import odoo_sync_pilot as guarded
from .platform_ingest import SourceEvent, _validate_events, checkpoint, ingest_batch

STREAM = "created_or_modified_v1"
KIND = "write_create_v1"
SOURCE_KEY = pilot.SOURCE_KEY
PAGE_LIMIT = 80
MAX_SOURCE_ROWS = 100
LOOKBACK = timedelta(hours=24)
OVERLAP = timedelta(minutes=15)
SETTLE = timedelta(seconds=60)
MAX_WINDOW = timedelta(days=30)
MAX_BYTES = wire.MAX_WIRE_BYTES
PIPED_ENV = "PANADAN_MIRROR_INCREMENTAL_PIPE"

# Explicitly scoped to the existing approved Odoo reporting view.
CANDIDATE_SQL = f"""
WITH candidates AS (
 SELECT "id", MAX(GREATEST("write_date", "create_date")) AS touched
 FROM {full.VIEW}
 WHERE ("write_date" >= %s AND "write_date" <= %s)
    OR ("create_date" >= %s AND "create_date" <= %s)
 GROUP BY "id"
)
SELECT "id", touched FROM candidates
WHERE touched >= %s AND touched <= %s
  AND (touched, "id") > (%s, %s)
ORDER BY touched ASC, "id" ASC
LIMIT %s
"""
GROUP_SQL = (f'SELECT {full.SELECT_COLUMNS} FROM {full.VIEW} '
             'WHERE "id" = ANY(%s) ORDER BY "id" ASC')


def _iso(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("Timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _parse(value: str) -> datetime:
    if type(value) is not str:
        raise ValueError("Invalid timestamp")
    try:
        val = datetime.fromisoformat(value)
        if val.tzinfo is None:
            raise ValueError("Timezone missing")
        return val.astimezone(timezone.utc)
    except ValueError:
        raise ValueError("Invalid timestamp") from None


def _cursor(before):
    """Validate a stored checkpoint; no coercion or implicit rewind."""
    if before is None:
        return None
    if (type(before) is not dict
            or set(before) not in ({'kind', 'completed_through'},
                                   {'kind', 'completed_through', 'window'})
            or before.get('kind') != KIND):
        raise ValueError("Invalid incremental checkpoint shape")
    completed = _parse(before["completed_through"])
    window = before.get("window")
    if window is not None:
        if (type(window) is not dict
                or set(window) != {'lower', 'upper', 'last_ts', 'last_id'}
                or type(window['last_id']) is not int
                or window['last_id'] < 0):
            raise ValueError("Invalid active incremental window")
        low, upper, last = (_parse(window[k]) for k in
                            ('lower', 'upper', 'last_ts'))
        if not low <= last <= upper or not completed - OVERLAP <= low:
            raise ValueError("Invalid active incremental position")
        if upper - low > MAX_WINDOW:
            raise ValueError("Unbounded incremental window")
    return before


def _plan(before, source_now: datetime):
    before = _cursor(before)
    now = source_now.astimezone(timezone.utc)
    if before and before.get("window") is not None:
        w = before['window']
        return before, _parse(w['lower']), _parse(w['upper']), (
            _parse(w['last_ts']), w['last_id'])
    completed = (_parse(before['completed_through']) if before
                 else now - LOOKBACK)
    upper = now - SETTLE
    if upper <= completed:
        return before, None, None, None
    lower = completed - OVERLAP
    if upper - lower > MAX_WINDOW:
        # Long VPN outages require a supervised explicit recovery decision
        # rather than silently scanning an unbounded source backlog.
        raise ValueError("Incremental source outage exceeds 30-day window")
    return before, lower, upper, (lower, 0)


def _group_events(source, chosen):
    """Fetch all variants for each selected ID under one read-only snapshot."""
    ids = [row['id'] for row in chosen]
    if not ids:
        return [], 0
    rows = source.execute(GROUP_SQL, (ids,)).fetchall()
    groups = {identity: [] for identity in ids}
    if len(rows) > MAX_SOURCE_ROWS:
        raise ValueError("More source-view rows than one bounded packet")
    for row in rows:
        identity, _, event = full.normalized(row)
        if identity not in groups:
            raise ValueError("Source ID group drift")
        groups[identity].append(event.payload)
    events = []
    for identity in ids:
        variants = groups[identity]
        if not variants:
            raise ValueError("Source view candidate disappeared within transaction")
        variants.sort(key=wire._canonical)
        if len({(r['call_id'], r['create_date']) for r in variants}) != 1:
            raise ValueError("Conflicting stable source identity anchors")
        events.append(SourceEvent(str(identity), 'upsert', {
            'id': identity, 'source_schema': 'odoo_view_37_v1',
            'source_rows': variants,
        }))
    _validate_events(events)
    return events, len(rows)


def make_incremental_packet(source, before, *, now=None):
    before = _cursor(before)
    full.validate_schema(source)
    identity = source.execute(
        "SELECT current_database() AS db, current_user AS role, "
        "current_setting('transaction_read_only') AS read_only"
    ).fetchone()
    if (not identity or identity["db"] != "odoo"
            or identity["role"] != "report_user"
            or identity["read_only"] != "on"):
        raise PermissionError("Read-only Odoo reporting identity required")
    if now is None:
        now = source.execute("SELECT clock_timestamp() AS source_now").fetchone()["source_now"]
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("Source clock must be timezone-aware")
    before, low, upper, position = _plan(before, now)
    chosen = []
    if low is not None:
        # The timestamp filter is the ONLY discovery mechanism; id only orders
        # equal timestamps and groups multiple joined view rows.
        rows = source.execute(
            CANDIDATE_SQL, (
                low.replace(tzinfo=None), upper.replace(tzinfo=None),
                low.replace(tzinfo=None), upper.replace(tzinfo=None),
                low.replace(tzinfo=None), upper.replace(tzinfo=None),
                position[0].replace(tzinfo=None), position[1],
                PAGE_LIMIT + 1,
            ),
        ).fetchall()
        if len(rows) > PAGE_LIMIT + 1:
            raise ValueError("Incremental candidate query exceeded page budget")
        chosen = rows[:PAGE_LIMIT]
        last = position
        for row in rows:
            key = (row['touched'], row['id'])
            if (type(row['id']) is not int or row['id'] <= 0
                    or type(row['touched']) is not datetime
                    or row['touched'].tzinfo is not None):
                raise ValueError("Invalid candidate identity/time")
            observed = row['touched'].replace(tzinfo=timezone.utc)
            if (observed, row['id']) <= last or not low <= observed <= upper:
                raise ValueError("Unordered incremental source candidates")
            last = (observed, row['id'])
        events, view_rows = _group_events(source, chosen)
        more = len(rows) > PAGE_LIMIT
    else:
        events, view_rows, more = [], 0, False

    if low is None:
        next_cursor = before
    elif more:
        last = chosen[-1]
        completed = (before['completed_through'] if before
                     else _iso(now - LOOKBACK))
        next_cursor = {
            'kind': KIND, 'completed_through': completed,
            'window': {
                'lower': _iso(low), 'upper': _iso(upper),
                'last_ts': _iso(last['touched'].replace(tzinfo=timezone.utc)),
                'last_id': last['id'],
            },
        }
    else:
        next_cursor = {'kind': KIND, 'completed_through': _iso(upper)}

    packet = {
        'version': 1, 'source_key': SOURCE_KEY, 'stream': STREAM,
        'expected_cursor': before, 'next_cursor': next_cursor,
        'source_rows': view_rows, 'more': more, 'noop': low is None,
        'events': [{'external_id': e.external_id, 'operation': 'upsert',
                    'payload': e.payload} for e in events],
    }
    packet['sha256'] = sha256(wire._canonical(packet)).hexdigest()
    if len(wire._canonical(packet)) > MAX_BYTES:
        raise ValueError("Incremental packet exceeds 55 MB limit")
    return packet


def validate_incremental_packet(packet):
    fields = {'version', 'source_key', 'stream', 'expected_cursor',
              'next_cursor', 'source_rows', 'more', 'noop', 'events', 'sha256'}
    if type(packet) is not dict or set(packet) != fields:
        raise ValueError("Unexpected incremental packet fields")
    if (packet['version'] != 1 or packet['source_key'] != SOURCE_KEY
            or packet['stream'] != STREAM
            or type(packet['source_rows']) is not int
            or packet['source_rows'] < 0
            or packet['source_rows'] > MAX_SOURCE_ROWS
            or type(packet['more']) is not bool
            or type(packet['noop']) is not bool
            or not isinstance(packet['events'], list)
            or len(packet['events']) > PAGE_LIMIT):
        raise ValueError("Invalid incremental packet envelope")
    if (type(packet['sha256']) is not str
            or packet['sha256'] != sha256(wire._canonical({
                k: v for k, v in packet.items() if k != 'sha256'
            })).hexdigest()):
        raise ValueError("Incremental transport digest mismatch")
    before = _cursor(packet['expected_cursor'])
    after = _cursor(packet['next_cursor'])
    if (packet['noop'] and
            (packet['events'] or packet['source_rows'] != 0 or
             after != before or packet['more'])):
        raise ValueError("Invalid no-op incremental page")
    if not packet['noop'] and after is None:
        raise ValueError("Uninitialized incremental cursor")
    if packet['more'] and (not packet['events']
                           or after is None or after.get('window') is None):
        raise ValueError("Invalid incremental continuation")
    if not packet['more'] and not packet['noop'] and after.get('window') is not None:
        raise ValueError("Incremental completed window still active")
    if (not packet['noop'] and before
            and _parse(after['completed_through']) <
                _parse(before['completed_through'])):
        raise ValueError("Incremental watermark moved backwards")
    checked = []
    count = 0
    for item in packet['events']:
        if (type(item) is not dict or
                set(item) != {'external_id', 'operation', 'payload'} or
                item['operation'] != 'upsert' or
                not isinstance(item['external_id'], str) or
                not item['external_id'].isdigit() or
                type(item['payload']) is not dict or
                set(item['payload']) != {'id', 'source_schema', 'source_rows'} or
                item['payload']['id'] != int(item['external_id']) or
                item['payload']['source_schema'] != 'odoo_view_37_v1'):
            raise ValueError("Malformed incremental source event")
        variants = item['payload']['source_rows']
        if not isinstance(variants, list) or not variants:
            raise ValueError("Missing source-view variants")
        canonical = []
        anchors = set()
        for v in variants:
            if type(v) is not dict or set(v) != set(full.COLUMN_NAMES):
                raise ValueError("Invalid full-field incremental payload")
            for key in full.COLUMN_NAMES:
                wire._check_field_type(key, v[key])
            if v['id'] != item['payload']['id'] or v['write_date'] is None:
                raise ValueError("Source-view identity or timestamp drift")
            anchors.add((v['call_id'], v['create_date']))
            canonical.append(wire._canonical(v))
        if canonical != sorted(canonical) or len(anchors) != 1:
            raise ValueError("Non-canonical or conflicting source group")
        count += len(variants)
        checked.append(SourceEvent(item['external_id'], 'upsert', item['payload']))
    _validate_events(checked)
    if count != packet['source_rows']:
        raise ValueError("Incorrect grouped source row count")
    return checked


def import_incremental_packet(packet):
    events = validate_incremental_packet(packet)
    target.validate_staging_writer_config()
    with target.owned_connection() as conn:
        with guarded.exclusive_pilot(conn):
            state = conn.execute(
                'SELECT enabled FROM panadan_ingest.sources WHERE source_key=%s',
                (SOURCE_KEY,),
            ).fetchone()
            if not state or state['enabled'] is not True:
                raise ValueError("Incremental source must be explicitly enabled")
            snapshot = checkpoint(
                conn, source_key=SOURCE_KEY, stream=pilot.SNAPSHOT_STREAM)
            if (type(snapshot) is not dict
                    or set(snapshot) != {'pass', 'last_id'}
                    or type(snapshot['pass']) is not int
                    or snapshot['pass'] < 3
                    or snapshot['last_id'] != 0):
                raise ValueError("Verified complete mirror baseline required")
            if (checkpoint(conn, source_key=SOURCE_KEY,
                           stream=pilot.BACKFILL_STREAM) is not None
                    or checkpoint(conn, source_key=SOURCE_KEY,
                                  stream=pilot.UPDATES_STREAM) is not None):
                raise ValueError("Conflicting legacy sync cursors")
            current = checkpoint(conn, source_key=SOURCE_KEY, stream=STREAM)
            if current != packet['expected_cursor']:
                raise ValueError("Incremental checkpoint advanced elsewhere")
            if packet['noop']:
                return {'source_rows': 0, 'calls': 0, 'changed': 0,
                        'unchanged': 0, 'window_complete': False,
                        'noop': True}
            pilot._check_identity_reuse(conn, events)
            result = ingest_batch(
                conn, source_key=SOURCE_KEY, stream=STREAM,
                events=events, expected_cursor=current,
                next_cursor=packet['next_cursor'],
            )
            return {'source_rows': packet['source_rows'],
                    'calls': result.examined, 'changed': result.upserted,
                    'unchanged': result.unchanged,
                    'window_complete': not packet['more'],
                    'noop': False}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('export', 'import'))
    p.add_argument('--cursor-json', default=None)
    args = p.parse_args(argv)
    try:
        if args.action == 'export':
            if os.environ.get(PIPED_ENV) != 'YES' or sys.stdout.isatty():
                raise PermissionError("Explicit private transfer pipe required")
            before = json.loads(args.cursor_json) if args.cursor_json else None
            with database.connect() as source:
                # Candidate IDs and complete joined rows must share a snapshot.
                source.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                packet = make_incremental_packet(source, before)
            sys.stdout.buffer.write(wire._canonical(packet))
            sys.stdout.buffer.flush()
        else:
            if args.cursor_json is not None:
                raise ValueError("Import cursor must come from staging database")
            raw = sys.stdin.buffer.read(MAX_BYTES + 1)
            if not raw or len(raw) > MAX_BYTES:
                raise ValueError("Invalid bounded incremental transfer")
            outcome = import_incremental_packet(json.loads(raw))
            print("STAGING INCREMENTAL:", outcome)
        return 0
    except Exception as exc:
        # Never log source payloads, customer data, source IDs, SQL or DSNs.
        print(f"INCREMENTAL FAILED: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
