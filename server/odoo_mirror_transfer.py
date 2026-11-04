"""One-shot, pipe-only transfer of ONE bounded Odoo snapshot page.

Exporter runs in the existing VPN network namespace with source READ ONLY.
Importer runs on host localhost with ONLY the restricted staging writer DSN.
Customer data is passed via anonymous stdout/stdin pipe, never in CLI
arguments, logs or persistent plaintext files.

This is a manual staging acceptance tool, NOT a public API, production sync
daemon, replacement for a whole-source reconciliation or trustless protocol.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime
from hashlib import sha256
import json
import math
import sys

from . import database, odoo_full_mirror_adapter as full
from . import odoo_full_mirror_pilot as pilot
from . import odoo_mirror_target as target
from . import odoo_sync_pilot as guarded
from .platform_ingest import SourceEvent, _validate_events, checkpoint, ingest_batch

WIRE_VERSION = 1
MAX_CALLS = 25
MAX_WIRE_BYTES = 55_000_000
_KEYS = {"version", "source_key", "after_id", "limit",
         "source_rows", "more", "events"}
_ALLOWED = _KEYS | {"sha256"}


def _canonical(value) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False,
        allow_nan=False, separators=(",", ":"),
    ).encode("utf-8")


def make_packet(source, *, after_id: int, limit: int) -> dict:
    """Only the restricted Odoo view is queried; no staging connection."""
    if (type(after_id) is not int or after_id < 0
            or type(limit) is not int or not 1 <= limit <= MAX_CALLS):
        raise ValueError("Invalid bounded export request")
    identity = source.execute(
        "SELECT current_database() AS db, current_user AS role, "
        "current_setting('transaction_read_only') AS read_only"
    ).fetchone()
    if (not identity or identity["db"] != "odoo"
            or identity["role"] != "report_user"
            or identity["read_only"] != "on"):
        raise PermissionError("Approved read-only source identity required")
    full.validate_schema(source)
    events, more, rows = full.read_snapshot_page(
        source, after_id=after_id, limit=limit)
    _validate_events(events)
    packet = {
        "version": WIRE_VERSION,
        "source_key": pilot.SOURCE_KEY,
        "after_id": after_id,
        "limit": limit,
        "source_rows": rows,
        "more": more,
        "events": [
            {"external_id": e.external_id, "operation": e.operation,
             "payload": e.payload}
            for e in events
        ],
    }
    digest = sha256(_canonical(packet)).hexdigest()
    packet["sha256"] = digest
    if len(_canonical(packet)) > MAX_WIRE_BYTES:
        raise ValueError("Export exceeds staging transfer size")
    return packet


def _check_field_type(name, value):
    if value is None:
        return
    kind = full.COLUMN_TYPE_MAP[name]
    if kind == "integer":
        valid = type(value) is int
    elif kind == "double precision":
        valid = type(value) is float and math.isfinite(value)
    elif kind in ("text", "character varying"):
        valid = type(value) is str
    elif kind == "date":
        try:
            valid = type(value) is str and date.fromisoformat(value).isoformat() == value
        except ValueError:
            valid = False
    elif kind == "timestamp without time zone":
        try:
            timestamp = datetime.fromisoformat(value)
            valid = (type(value) is str and timestamp.tzinfo is None
                     and timestamp.isoformat(timespec="microseconds") == value)
        except (TypeError, ValueError):
            valid = False
    elif kind == "jsonb":
        valid = True  # Canonical strict JSON serialization checks nested values.
    else:
        valid = False
    if not valid:
        raise ValueError("Transfer source field type drift")


def validate_packet(packet, *, expected_limit: int, expected_after_id: int):
    """Verify the data shape *before* any staging write transaction."""
    if (not isinstance(packet, dict) or set(packet) != _ALLOWED
            or type(expected_limit) is not int or not 1 <= expected_limit <= MAX_CALLS
            or type(expected_after_id) is not int or expected_after_id < 0):
        raise ValueError("Invalid staging transfer envelope")
    if (packet["version"] != WIRE_VERSION
            or packet["source_key"] != pilot.SOURCE_KEY
            or type(packet["after_id"]) is not int
            or packet["after_id"] != expected_after_id
            or type(packet["limit"]) is not int
            or packet["limit"] != expected_limit
            or type(packet["source_rows"]) is not int
            or type(packet["more"]) is not bool
            or not isinstance(packet["events"], list)
            or len(packet["events"]) > expected_limit
            or not isinstance(packet["sha256"], str)
            or len(packet["sha256"]) != 64):
        raise ValueError("Untrusted staging transfer metadata")
    digest = sha256(_canonical({k: packet[k] for k in _KEYS})).hexdigest()
    if digest != packet["sha256"]:
        raise ValueError("Staging transfer digest mismatch")

    checked = []
    previous = expected_after_id
    rows_total = 0
    for item in packet["events"]:
        if (not isinstance(item, dict)
                or set(item) != {"external_id", "operation", "payload"}
                or item["operation"] != "upsert"
                or not isinstance(item["external_id"], str)
                or not item["external_id"].isdigit()
                or not isinstance(item["payload"], dict)):
            raise ValueError("Malformed staging source event")
        external = int(item["external_id"])
        if (external <= previous or str(external) != item["external_id"]
                or set(item["payload"]) != {"id", "source_schema", "source_rows"}
                or item["payload"]["id"] != external
                or item["payload"]["source_schema"] != "odoo_view_37_v1"):
            raise ValueError("Source event ordering or schema changed")
        variants = item["payload"]["source_rows"]
        if not isinstance(variants, list) or not 1 <= len(variants) <= expected_limit:
            raise ValueError("Invalid grouped Odoo rows")
        anchors = set()
        order = []
        for row in variants:
            if not isinstance(row, dict) or set(row) != set(full.COLUMN_NAMES):
                raise ValueError("Source row schema mismatch")
            for name in full.COLUMN_NAMES:
                _check_field_type(name, row[name])
            if row["id"] != external or row["write_date"] is None:
                raise ValueError("Source row identity mismatch")
            anchors.add((row["call_id"], row["create_date"]))
            order.append(_canonical(row))
        if len(anchors) != 1 or order != sorted(order):
            raise ValueError("Source row group is not canonical")
        rows_total += len(variants)
        checked.append(SourceEvent(str(external), "upsert", item["payload"]))
        previous = external
    _validate_events(checked)
    if (rows_total != packet["source_rows"]
            or rows_total > expected_limit
            or (packet["more"] and not checked)
            or (not packet["more"] and rows_total > expected_limit)):
        raise ValueError("Invalid transfer page boundary")
    return checked


def import_page(packet: dict, *, expected_limit: int, approvals: argparse.Namespace):
    # Require four intentional approvals and the opt-in isolated staging DSN.
    pilot.require_approval(approvals)
    if approvals.batch_size != expected_limit or approvals.max_pages != 1:
        raise ValueError("Transfer approval budget mismatch")
    target.validate_staging_writer_config()
    with target.owned_connection() as owned:
        with guarded.exclusive_pilot(owned):
            source = owned.execute(
                "SELECT enabled FROM panadan_ingest.sources WHERE source_key=%s",
                (pilot.SOURCE_KEY,),
            ).fetchone()
            if not source or not source["enabled"]:
                raise ValueError("Staging source must be explicitly enabled")
            if (checkpoint(owned, source_key=pilot.SOURCE_KEY,
                           stream=pilot.BACKFILL_STREAM) is not None
                or checkpoint(owned, source_key=pilot.SOURCE_KEY,
                              stream=pilot.UPDATES_STREAM) is not None):
                raise ValueError("Legacy cursor requires a migration")
            before = checkpoint(
                owned, source_key=pilot.SOURCE_KEY, stream=pilot.SNAPSHOT_STREAM)
            if before is None:
                pass_no, after_id = 1, 0
            elif (not isinstance(before, dict)
                  or set(before) != {"pass", "last_id"}
                  or type(before["pass"]) is not int or before["pass"] < 1
                  or type(before["last_id"]) is not int or before["last_id"] < 0):
                raise ValueError("Invalid snapshot checkpoint")
            else:
                pass_no, after_id = before["pass"], before["last_id"]
            events = validate_packet(
                packet, expected_limit=expected_limit,
                expected_after_id=after_id)
            pilot._check_identity_reuse(owned, events)
            if packet["more"]:
                next_cursor = {"pass": pass_no,
                               "last_id": int(events[-1].external_id)}
            else:
                next_cursor = {"pass": pass_no + 1, "last_id": 0}
            result = ingest_batch(
                owned, source_key=pilot.SOURCE_KEY,
                stream=pilot.SNAPSHOT_STREAM,
                events=events, expected_cursor=before,
                next_cursor=next_cursor)
            return {
                "pages": 1, "pass": pass_no,
                "source_rows": packet["source_rows"],
                "calls": result.examined, "changed": result.upserted,
                "unchanged": result.unchanged,
                "pass_complete": not packet["more"],
            }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("export", "import"))
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--after-id", type=int, default=0)
    for name in pilot.REQUIRED_ACKS:
        parser.add_argument("--" + name.replace("_", "-"), action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            if not 1 <= args.batch_size <= MAX_CALLS:
                raise ValueError("Export exceeds first-stage page limit")
            with database.connect() as source:
                packet = make_packet(
                    source, after_id=args.after_id, limit=args.batch_size)
            sys.stdout.buffer.write(_canonical(packet))
            sys.stdout.buffer.flush()
        else:
            if args.after_id != 0:
                raise ValueError("Import cursor comes exclusively from DB")
            if not 1 <= args.batch_size <= MAX_CALLS:
                raise ValueError("Import exceeds first-stage page limit")
            raw = sys.stdin.buffer.read(MAX_WIRE_BYTES + 1)
            if not raw or len(raw) > MAX_WIRE_BYTES:
                raise ValueError("Invalid bounded pipe input")
            packet = json.loads(raw)
            outcome = import_page(
                packet, expected_limit=args.batch_size,
                approvals=argparse.Namespace(
                    command="snapshot", mode="utc_naive",
                    batch_size=args.batch_size, max_pages=1,
                    **{name: getattr(args, name) for name in pilot.REQUIRED_ACKS},
                ))
            print("STAGING PIPE IMPORT:", outcome)
        return 0
    except Exception as exc:
        # Never expose payloads/DSNs/user IDs from driver or parse errors.
        print(f"STAGING PIPE FAILED: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
