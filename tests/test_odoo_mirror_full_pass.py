"""Regression gates for finite-supervision full first-pass staging backfill.

The tests use synthetic shell checks only: never access Odoo or PG18.
"""
from pathlib import Path
import os
import subprocess

import pytest


SCRIPT = Path("tools/run-odoo-mirror-staging-full-pass.sh")
NEXT = Path("tools/run-odoo-mirror-staging-next.sh")
FLAGS = [
    "--ack-source-contract", "--ack-retention",
    "--ack-copy", "--ack-sensitive-data",
]


def test_full_pass_shell_parses():
    check = subprocess.run(["bash", "-n", str(SCRIPT)],
                           capture_output=True, text=True)
    assert check.returncode == 0, check.stderr


@pytest.mark.parametrize("args", [
    [], ["full-pass"], ["full-pass", *FLAGS[:-1]],
    ["full-pass", FLAGS[0], FLAGS[0], FLAGS[1], FLAGS[2]],
    ["wrong-command", *FLAGS],
])
def test_invalid_approvals_stop_before_db_access(args):
    check = subprocess.run(["bash", str(SCRIPT), *args],
                           capture_output=True, text=True,
                           timeout=5)
    assert check.returncode == 2
    assert "approval" in (check.stdout + check.stderr).lower() or "Usage" in check.stderr


def test_full_pass_staging_only_guardrails():
    s = SCRIPT.read_text(encoding="utf-8")
    assert "set -euo pipefail" in s
    assert "set +x" in s
    assert "umask 077" in s
    assert "DB=panadan-mirror-staging-pg18" in s
    assert "RESTORE=panadan-mirror-data-restore-drill-pg18" in s
    assert "SOURCE=odoo_calls_full_v1" in s
    assert "STREAM=view_reconciliation_v1" in s
    assert "INITIAL_RECORDS=825" in s
    assert "MIN_AVAILABLE_KIB=6291456" in s
    assert "BACKUP_RESERVE_KIB=131072" in s
    assert "BACKUP_EVERY_RECORDS=5000" in s
    assert "PAGE_BUDGET=2000" in s
    assert "flock -n 8" in s
    assert "HostConfig.NetworkMode" in s
    assert "127.0.0.1:55432" in s
    assert "panadan_restore_825" in s
    assert "PANADAN_MIRROR_PAGE_LIMIT=3" in s
    assert 'PANADAN_MIRROR_MIN_AVAILABLE_KIB="$MIN_AVAILABLE_KIB"' in s
    assert "next-batch --ack-source-contract" in s
    assert "while (( pass == 1 ))" in s
    assert '"$pass" == 2 && "$cursor" == 0' in s
    assert "integrity_check" in s
    assert "backup_checkpoint" in s
    assert "pg_dump" in s and "pg_restore -l" in s
    assert "age -r" in s and "age -d" in s
    assert "active_child=1" in s and "active_child=0" in s
    assert "MAX_WIRE_BYTES" not in s  # underlying importer validates
    assert "docker network connect" not in s
    assert "docker compose up" not in s
    assert "TRUNCATE " not in s
    assert "DROP DATABASE" not in s


def test_child_transfer_has_per_page_disk_gate_and_restricted_credentials():
    s = NEXT.read_text(encoding="utf-8")
    assert "PANADAN_MIRROR_MIN_AVAILABLE_KIB" in s
    assert "check_disk_floor" in s
    assert "127.0.0.1:55432" in s
    assert "--network container:panadan-vpn-1" in s
    assert "--network host" in s
    assert s.count("--log-driver=none") == 2
    assert "PANADAN_FULL_MIRROR_TARGET_MODE=isolated-staging" in s
    assert "PANADAN_FULL_MIRROR_STAGING_ISOLATED=YES" in s
    assert "trap on_exit EXIT" in s
