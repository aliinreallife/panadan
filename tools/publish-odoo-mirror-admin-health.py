#!/usr/bin/env python3
"""Publish aggregate-only Odoo staging mirror sync health for the admin UI.

The publisher runs on the VPS host under a separately opt-in systemd timer.
No production database access, no Odoo query, no user-data rows, no DSN.
Outputs a single atomic whitelisted JSON snapshot which must be mounted
read-only inside the production web container by a separate reviewed deploy.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

STAGE = "panadan-mirror-staging-pg18"
VPN = "panadan-vpn-1"
SOURCE = "odoo_calls_full_v1"
OUT = Path("/var/lib/panadan-mirror-staging/health/mirror-health.json")
VERSION = 1

# SQL reads only aggregate metadata. Never select raw_revisions.payload or
# source_records customer row identifiers. Match expected instance identity.
SQL = """
SELECT json_build_object(
  'database', current_database(),
  'version', current_setting('server_version_num'),
  'records', (SELECT count(*) FROM panadan_ingest.source_records
              WHERE source_key='odoo_calls_full_v1'),
  'revisions', (SELECT count(*) FROM panadan_ingest.raw_revisions
                WHERE source_key='odoo_calls_full_v1'),
  'pages', (SELECT count(*) FROM panadan_ingest.sync_runs
            WHERE source_key='odoo_calls_full_v1'
              AND stream='created_or_modified_v1'),
  'source_enabled', (SELECT enabled FROM panadan_ingest.sources
                     WHERE source_key='odoo_calls_full_v1'),
  'snapshot_pass', (SELECT cursor->>'pass'
                    FROM panadan_ingest.sync_checkpoints
                    WHERE source_key='odoo_calls_full_v1'
                      AND stream='view_reconciliation_v1'),
  'snapshot_last_id', (SELECT cursor->>'last_id'
                       FROM panadan_ingest.sync_checkpoints
                       WHERE source_key='odoo_calls_full_v1'
                         AND stream='view_reconciliation_v1'),
  'completed_through', (SELECT cursor->>'completed_through'
                        FROM panadan_ingest.sync_checkpoints
                        WHERE source_key='odoo_calls_full_v1'
                          AND stream='created_or_modified_v1'),
  'last_processed', (SELECT cursor->'window'->>'last_ts'
                     FROM panadan_ingest.sync_checkpoints
                     WHERE source_key='odoo_calls_full_v1'
                       AND stream='created_or_modified_v1'),
  'window_upper', (SELECT cursor->'window'->>'upper'
                   FROM panadan_ingest.sync_checkpoints
                   WHERE source_key='odoo_calls_full_v1'
                     AND stream='created_or_modified_v1'),
  'last_commit', (SELECT to_char(MAX(finished_at) AT TIME ZONE 'UTC',
                        'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
                  FROM panadan_ingest.sync_runs
                  WHERE source_key='odoo_calls_full_v1'
                    AND stream='created_or_modified_v1')
)::text;
"""


def command(argv, timeout=15):
    result = subprocess.run(
        argv, capture_output=True, text=True, check=False, timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError("Health metadata command unavailable")
    return result.stdout.strip()


def collect(now=None):
    """Read only fixed control-plane metadata, returning a fixed schema."""
    timestamp = now or datetime.now(timezone.utc)
    disk_free = shutil.disk_usage("/var/lib/panadan-mirror-staging").free
    snapshot = {
        "version": VERSION,
        "generated_at": timestamp.astimezone(timezone.utc).isoformat(
            timespec="seconds"),
        "database_ok": False,
        "timer_active": False,
        "vpn_healthy": False,
        "service_ok": False,
        "disk_free_bytes": disk_free,
        "records": None,
        "revisions": None,
        "pages": None,
        "last_commit": None,
        "completed_through": None,
        "last_processed": None,
        "window_upper": None,
        "source_enabled": None,
    }

    try:
        snapshot["timer_active"] = command([
            "systemctl", "is-active", "panadan-mirror-incremental.timer",
        ]) == "active"
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        pass
    try:
        snapshot["service_ok"] = command([
            "systemctl", "show", "--property=Result", "--value",
            "panadan-mirror-incremental.service",
        ]) == "success"
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        pass
    try:
        snapshot["vpn_healthy"] = command([
            "docker", "inspect", VPN, "--format",
            "{{.State.Health.Status}}",
        ]) == "healthy"
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        pass

    try:
        if command(["docker", "port", STAGE, "5432/tcp"]) != "127.0.0.1:55432":
            raise RuntimeError("Unexpected staging loopback binding")
        raw = command([
            "docker", "exec", STAGE, "psql", "-X", "-Atq",
            "-v", "ON_ERROR_STOP=1", "-U", "panadan_stage_owner",
            "-d", "panadan_ci", "-c", SQL,
        ], timeout=20)
        data = json.loads(raw)
        if (type(data) is not dict or data.get("database") != "panadan_ci"
                or data.get("version") != "180006"
                or not str(data.get("snapshot_pass", "")).isdigit()
                or int(data["snapshot_pass"]) < 3
                or data.get("snapshot_last_id") != "0"
                or type(data.get("source_enabled")) is not bool):
            raise RuntimeError("Unexpected mirror metadata identity")
        for field in ("records", "revisions", "pages"):
            value = data.get(field)
            if type(value) is not int or value < 0 or value > 10**15:
                raise RuntimeError("Invalid aggregate metadata")
            snapshot[field] = value
        for field in ("last_commit", "completed_through",
                      "last_processed", "window_upper"):
            value = data.get(field)
            if value is not None and (type(value) is not str or len(value) > 40):
                raise RuntimeError("Invalid checkpoint timestamp")
            snapshot[field] = value
        snapshot["source_enabled"] = data["source_enabled"]
        snapshot["database_ok"] = True
    except (OSError, ValueError, TypeError, RuntimeError,
            subprocess.TimeoutExpired, json.JSONDecodeError):
        # Do not leak SQL, credentials, output or driver errors into logs.
        snapshot.update({
            "database_ok": False, "records": None, "revisions": None,
            "pages": None, "last_commit": None, "completed_through": None,
            "last_processed": None, "window_upper": None,
            "source_enabled": None,
        })
    return snapshot


def publish(snapshot, path=OUT):
    """Atomic replacement; a web reader cannot observe half-written JSON."""
    path = Path(path)
    if path != OUT:
        raise ValueError("Unsupported health output path")
    directory = path.parent
    directory.mkdir(mode=0o755, parents=True, exist_ok=True)
    data = json.dumps(snapshot, ensure_ascii=True, sort_keys=True,
                      allow_nan=False, separators=(",", ":")).encode("ascii")
    if len(data) > 8192:
        raise ValueError("Health document exceeds limit")
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".health-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if args != ["publish"]:
        print("Usage: publish-odoo-mirror-admin-health.py publish",
              file=sys.stderr)
        return 2
    try:
        publish(collect())
        print("PASS: Aggregate-only mirror admin health published")
        return 0
    except (OSError, ValueError, TypeError):
        print("FAIL: Mirror admin health publisher unavailable",
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
