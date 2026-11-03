"""Operator-invoked, bounded, fail-closed Odoo -> owned-PG sync pilot.

No scheduler, HTTP route, automatic source registration, source writes, or
dashboard read-path switch. The source uses Panadan's Odoo READ ONLY connection;
the target is *only* the existing Panadan-owned PG18 ingest-writer role.
Payloads and secrets are never printed. A deliberate approval is required
for every write command. Intended to be executed inside an approved isolated
Panadan Web/VPN namespace after staging, NEVER as an unattended production job.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import stat
import sys

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from . import database, odoo_sync_adapter as adapter, odoo_sync_coordinator as sync
from .platform_ingest import checkpoint

DSN_FILE_ENV = "PANADAN_SYNC_OWNED_DSN_FILE"
REQUIRED_ACKS = ("ack_source_contract", "ack_retention", "ack_copy")
TARGET_HOST = "panadan-auth-postgres"
TARGET_DB = "panadan"
TARGET_ROLE = "panadan_ingest_writer"
LOCK_KEYS = (0x50616E61, 0x64616E53)  # fixed application-level serial worker lock


def require_approval(args) -> None:
    if not all(getattr(args, field, False) is True for field in REQUIRED_ACKS):
        raise ValueError("Write blocked: source contract, local retention, and copy approval are required")
    if not 1 <= args.batch_size <= 200 or not 1 <= args.max_pages <= 5:
        raise ValueError("Pilot batch size must be 1..200 and pages 1..5")
    if args.mode not in ("utc_naive", "timestamptz"):
        raise ValueError("Explicit source timestamp mode is required")


def validate_owned_dsn(dsn: str) -> None:
    """Reject source Odoo, owner/admin, redirected or ambiguous target DSNs."""
    if not isinstance(dsn, str) or len(dsn) > 4096 or not dsn.strip():
        raise ValueError("Invalid owned PostgreSQL DSN")
    try:
        opts = conninfo_to_dict(dsn)
    except Exception:
        raise ValueError("Invalid owned PostgreSQL DSN") from None
    allowed = {"host", "port", "dbname", "user", "password",
               "sslmode", "connect_timeout"}
    if (set(opts) - allowed
            or opts.get("host") != TARGET_HOST
            or opts.get("port") != "5432"
            or opts.get("dbname") != TARGET_DB
            or opts.get("user") != TARGET_ROLE
            or not opts.get("password")):
        raise ValueError("Target must be Panadan PG18 with its restricted ingest writer")
    if opts.get("sslmode", "prefer") not in ("prefer", "require", "verify-full"):
        raise ValueError("Target SSL setting is not supported")
    for name in ("PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE", "PGOPTIONS",
                 "PGPASSFILE"):
        if os.environ.get(name):
            raise ValueError("Unexpected libpq environment redirect")


def _read_target_dsn() -> str:
    path_value = os.environ.get(DSN_FILE_ENV, "")
    if not path_value or not Path(path_value).is_absolute():
        raise ValueError("Set an absolute path to a private owned-DB DSN file")
    path = Path(path_value)
    try:
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode) & 0o077
                or info.st_uid not in (os.geteuid(), 0)
                or info.st_size < 16 or info.st_size > 4096):
            raise ValueError("Owned-DB DSN file must be private, regular, and small")
        dsn = path.read_text(encoding="utf-8").strip()
    except OSError:
        raise ValueError("Cannot read owned-DB DSN file") from None
    if "\n" in dsn or "\r" in dsn:
        raise ValueError("Owned-DB DSN file must contain a single DSN line")
    validate_owned_dsn(dsn)
    return dsn


@contextmanager
def owned_connection():
    """Different database and restricted credentials; never the source role."""
    dsn = _read_target_dsn()
    with psycopg.connect(dsn, connect_timeout=5, autocommit=True, row_factory=dict_row,
                         options="-c statement_timeout=12000") as conn:
        identity = conn.execute(
            "SELECT current_database() AS db, current_user AS role, "
            "current_setting('server_version_num') AS version"
        ).fetchone()
        if (identity["db"] != TARGET_DB or identity["role"] != TARGET_ROLE
                or not 180000 <= int(identity["version"]) < 190000):
            raise ValueError("Target PostgreSQL identity/version mismatch")
        yield conn


@contextmanager
def exclusive_pilot(conn):
    """Serialize backfill and updates, not merely writes to one cursor stream."""
    locked = conn.execute(
        "SELECT pg_try_advisory_lock(%s, %s) AS ok", LOCK_KEYS
    ).fetchone()["ok"]
    if not locked:
        raise ValueError("Another Odoo pilot process is already active")
    try:
        yield
    finally:
        conn.execute("SELECT pg_advisory_unlock(%s, %s)", LOCK_KEYS)


def preview(*, mode: str, limit: int = 100) -> dict:
    """Source-only plan; prints aggregates, never returns Odoo row payloads."""
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Preview sample must be 1..100 rows")
    with database.connect() as source:
        marker = adapter.validate_schema(source, mode=mode)
        rows = adapter.read_id_page(source, after_id=0, limit=limit,
                                    mode=mode, marker=marker)
    return {
        "marker": marker, "rows_examined": len(rows),
        "missing_update_timestamps": 0,
        "page_size_limit": 200,
        "source_is_read_only": True,
        "target_unchanged": True,
    }


def status(target) -> dict:
    """Local counts/cursors only. Never return IDs, row payloads or timestamps."""
    src = target.execute(
        "SELECT enabled FROM panadan_ingest.sources WHERE source_key=%s",
        (sync.ODOO_SOURCE_KEY,),
    ).fetchone()
    records = target.execute(
        "SELECT COUNT(*) AS n FROM panadan_ingest.source_records "
        "WHERE source_key=%s AND is_deleted=FALSE",
        (sync.ODOO_SOURCE_KEY,),
    ).fetchone()
    changes = target.execute(
        "SELECT COUNT(*) AS n FROM panadan_ingest.raw_revisions "
        "WHERE source_key=%s",
        (sync.ODOO_SOURCE_KEY,),
    ).fetchone()
    runs = target.execute(
        "SELECT COUNT(*) AS runs, "
        "EXTRACT(EPOCH FROM (clock_timestamp()-MAX(finished_at))) AS age "
        "FROM panadan_ingest.sync_runs WHERE source_key=%s",
        (sync.ODOO_SOURCE_KEY,),
    ).fetchone()
    return {
        "source_registered": src is not None,
        "source_enabled": bool(src and src["enabled"]),
        "local_records": records["n"],
        "local_revisions": changes["n"],
        "committed_pages": runs["runs"],
        "seconds_since_last_commit": int(runs["age"]) if runs["age"] is not None else None,
        "update_cursor_seeded": checkpoint(
            target, source_key=sync.ODOO_SOURCE_KEY,
            stream=sync.UPDATES_STREAM) is not None,
        "id_cursor_started": checkpoint(
            target, source_key=sync.ODOO_SOURCE_KEY,
            stream=sync.BACKFILL_STREAM) is not None,
    }


def apply(args) -> list[dict]:
    require_approval(args)
    with owned_connection() as target:
        with exclusive_pilot(target):
            with database.connect() as source:
                # Stop before any local write if a later source deployment
                # removed the verified marker or changed its timestamp type.
                marker = adapter.validate_schema(source, mode=args.mode)
                if marker == "write_date" and args.mode != "utc_naive":
                    raise ValueError("Odoo write_date requires approved UTC-naive timestamp mode")
                if args.command == "seed":
                    seed = sync.seed_update_stream(source, target, mode=args.mode)
                    return [{"operation": "seed", "marker": seed["marker"],
                             "cursor_stored": True}]
                streams = (("backfill", "updates") if args.command == "sync-once"
                           else (args.command,))
                rows = []
                for stream in streams:
                    for page in range(args.max_pages):
                        if stream == "backfill":
                            result = sync.poll_id_page(
                                source, target, mode=args.mode, limit=args.batch_size)
                        elif stream == "updates":
                            result = sync.poll_update_page(
                                source, target, mode=args.mode, limit=args.batch_size)
                        else:
                            raise ValueError("Unsupported write operation")
                        rows.append({
                            "page": page + 1,
                            "operation": stream,
                            "examined": result.examined,
                            "changed": result.changed,
                            "unchanged": result.skipped,
                            "more": result.has_more,
                        })
                        if not result.has_more:
                            break
                return rows


def parse(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("preview", "status", "seed", "backfill", "updates", "sync-once"))
    p.add_argument("--mode", choices=("utc_naive", "timestamptz"),
                   default="utc_naive", help="Must match the source owner timestamp contract")
    p.add_argument("--batch-size", type=int, default=100)
    p.add_argument("--max-pages", type=int, default=1)
    for option in REQUIRED_ACKS:
        p.add_argument("--" + option.replace("_", "-"), action="store_true")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse(argv)
    try:
        if args.command == "preview":
            result = preview(mode=args.mode, limit=min(args.batch_size, 100))
            print("PREVIEW:", result)
        elif args.command == "status":
            with owned_connection() as target:
                print("STATUS:", status(target))
        else:
            for line in apply(args):
                print("PILOT:", line)
        return 0
    except Exception as exc:
        # Neither DB exception messages nor DSNs ever leave the process.
        state = getattr(exc, "sqlstate", None)
        state = state if isinstance(state, str) and len(state) == 5 and state.isalnum() else "unknown"
        print(f"SYNC PILOT FAILED: {type(exc).__name__} SQLSTATE={state}",
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
