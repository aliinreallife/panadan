"""Read-only, full-view Odoo vs isolated-stage parity census.

Two isolated containers communicate exclusively by a JSON-lines anonymous
pipe. Source exports bounded authenticated 37-field wire packets. Target
validates each packet and compares SHA256 content digests with the completed
first-pass mirror, without ingesting revisions, changing checkpoints, or
discarding records absent from the view.

No row payload, external ID, customer name or transcript is printed or saved.
This is a succession of READ ONLY views, not a transactionally consistent
whole-source snapshot or a production synchronization engine.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
import json
import os
import sys

from . import database
from . import odoo_mirror_transfer as transfer
from . import odoo_mirror_target as target
from . import odoo_full_mirror_pilot as pilot
from .platform_ingest import _validate_events, checkpoint

PAGE_SIZE = 100
MAX_PAGES = 2000
SOURCE_APPROVAL_ENV = "PANADAN_MIRROR_PARITY_SOURCE_PIPE"


def export_pages() -> dict:
    """Stream only to a positively acknowledged private process pipe."""
    if (os.environ.get(SOURCE_APPROVAL_ENV) != "YES"
            or sys.stdout.isatty()):
        raise PermissionError("Approved anonymous parity pipe required")
    cursor = 0
    pages = 0
    with database.connect() as source:
        while True:
            if pages >= MAX_PAGES:
                raise ValueError("Parity source page budget exceeded")
            packet = transfer.make_packet(source, after_id=cursor, limit=PAGE_SIZE)
            # Exactly one JSON record per line, bounded by transfer.MAX_WIRE_BYTES.
            sys.stdout.buffer.write(transfer._canonical(packet) + b"\n")
            sys.stdout.buffer.flush()
            pages += 1
            if not packet["more"]:
                break
            events = packet["events"]
            if not events:
                raise ValueError("Source page made no progress")
            next_cursor = int(events[-1]["external_id"])
            if next_cursor <= cursor:
                raise ValueError("Source page cursor failed to advance")
            cursor = next_cursor
    return {"pages": pages}


def compare_packets(lines: Iterable[bytes],
                    staged: Mapping[str, tuple[str, bool]]) -> dict:
    """Compare complete groups and digests; no writing and no raw-data output."""
    total = {
        "pages": 0,
        "source_view_rows": 0,
        "source_call_groups": 0,
        "matched": 0,
        "changed_at_staging": 0,
        "missing_at_staging": 0,
        "not_visible_in_source": 0,
        "duplicate_row_groups": 0,
    }
    seen = set()
    after_id = 0
    terminal_seen = False
    for raw in lines:
        if terminal_seen:
            raise ValueError("Unexpected data after parity terminal packet")
        if not raw or len(raw) > transfer.MAX_WIRE_BYTES + 2:
            raise ValueError("Parity packet exceeds wire budget")
        if total["pages"] >= MAX_PAGES:
            raise ValueError("Parity page count exceeds safety budget")
        packet = json.loads(raw)
        events = transfer.validate_packet(
            packet, expected_limit=PAGE_SIZE, expected_after_id=after_id)
        checks = _validate_events(events)
        total["pages"] += 1
        total["source_view_rows"] += packet["source_rows"]
        total["source_call_groups"] += len(events)
        for event, digest in checks:
            if event.external_id in seen:
                raise ValueError("Duplicate call group across source pages")
            seen.add(event.external_id)
            total["duplicate_row_groups"] += (
                len(event.payload["source_rows"]) > 1
            )
            record = staged.get(event.external_id)
            if record is None or record[1]:
                total["missing_at_staging"] += 1
            elif record[0] != digest:
                total["changed_at_staging"] += 1
            else:
                total["matched"] += 1
        if events:
            after_id = int(events[-1].external_id)
        if not packet["more"]:
            terminal_seen = True
    if not terminal_seen:
        raise ValueError("Source parity stream ended before terminal page")
    if total["source_view_rows"] > MAX_PAGES * PAGE_SIZE:
        raise ValueError("Source exceeded parity row budget")
    total["not_visible_in_source"] = len(set(staged) - seen)
    if (total["matched"] + total["changed_at_staging"]
            + total["missing_at_staging"] != total["source_call_groups"]):
        raise ValueError("Parity totals did not balance")
    return total


def verify_pages() -> dict:
    """Require isolated staging, pass-2 checkpoint and READ ONLY transaction."""
    target.validate_staging_writer_config()
    with target.owned_connection() as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            row = conn.execute(
                """SELECT enabled FROM panadan_ingest.sources
                   WHERE source_key=%s""", (pilot.SOURCE_KEY,)
            ).fetchone()
            if not row or row["enabled"] is not False:
                raise ValueError("Staging source must be disabled")
            before = checkpoint(
                conn, source_key=pilot.SOURCE_KEY, stream=pilot.SNAPSHOT_STREAM)
            if before != {"pass": 2, "last_id": 0}:
                raise ValueError("First-pass checkpoint must be complete")
            if (checkpoint(conn, source_key=pilot.SOURCE_KEY,
                           stream=pilot.BACKFILL_STREAM) is not None
                    or checkpoint(conn, source_key=pilot.SOURCE_KEY,
                                  stream=pilot.UPDATES_STREAM) is not None):
                raise ValueError("Legacy cursor must not be present")
            rows = conn.execute(
                """SELECT external_id, current_digest, is_deleted
                   FROM panadan_ingest.source_records
                   WHERE source_key=%s""", (pilot.SOURCE_KEY,)
            ).fetchall()
            stored = {row["external_id"]:
                      (row["current_digest"], row["is_deleted"])
                      for row in rows}
            if len(stored) != len(rows) or not stored:
                raise ValueError("Invalid staging record set")
            summary = compare_packets(sys.stdin.buffer, stored)
            still_disabled = conn.execute(
                """SELECT enabled FROM panadan_ingest.sources
                   WHERE source_key=%s""", (pilot.SOURCE_KEY,)
            ).fetchone()
            if not still_disabled or still_disabled["enabled"] is not False:
                raise ValueError("Staging source changed during scan")
            if checkpoint(
                    conn, source_key=pilot.SOURCE_KEY,
                    stream=pilot.SNAPSHOT_STREAM) != before:
                raise ValueError("Staging checkpoint changed during parity scan")
            summary["staged_call_groups"] = len(stored)
            summary["source_read_only"] = True
            summary["staging_read_only"] = True
            summary["checkpoint_unchanged"] = True
            return summary


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("source", "staging"))
    args = parser.parse_args(argv)
    try:
        if args.mode == "source":
            export_pages()  # Source stdout is PRIVATE wire; never echo a summary.
        else:
            summary = verify_pages()
            print("READ-ONLY ODOO MIRROR PARITY CENSUS COMPLETE")
            print(json.dumps(summary, sort_keys=True))
        return 0
    except Exception as exc:
        # Never log data fields, source IDs, personal information, SQL or DSNs.
        print(f"PARITY CENSUS FAILED: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
