"""Synthetic-only, no-database safety gates for supervised staging import."""
from pathlib import Path
import os
import subprocess

import pytest


SUPERVISOR = Path("tools/run-odoo-mirror-staging-supervised.sh")
CHILD = Path("tools/run-odoo-mirror-staging-next.sh")
FLAGS = [
    "--ack-source-contract",
    "--ack-retention",
    "--ack-copy",
    "--ack-sensitive-data",
]


@pytest.mark.parametrize("path", [SUPERVISOR, CHILD])
def test_staging_shell_syntax(path):
    result = subprocess.run(["bash", "-n", str(path)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("args", [
    [], ["supervised"], ["supervised", *FLAGS[:-1]],
    ["supervised", FLAGS[0], FLAGS[0], FLAGS[1], FLAGS[2]],
])
def test_supervisor_rejects_missing_or_duplicate_approvals(args):
    result = subprocess.run(["bash", str(SUPERVISOR), *args],
                            capture_output=True, text=True)
    assert result.returncode == 2
    assert "approval" in (result.stdout + result.stderr).lower() or "Usage" in result.stderr


def test_supervised_runner_limits_work_and_never_reconfigures_production():
    text = SUPERVISOR.read_text()
    assert "set -euo pipefail" in text and "set +x" in text
    assert "CHUNKS=3" in text
    assert "ROWS_PER_CHUNK=300" in text
    assert "BASE_PAGES=24" in text
    assert "TARGET_PAGES=$((BASE_PAGES + CHUNKS * 3))" in text
    assert "MIN_AVAILABLE_KIB=$((6 * 1024 * 1024))" in text
    assert "PANADAN_MIRROR_PAGE_LIMIT" in text
    assert "PANADAN_MIRROR_MIN_AVAILABLE_KIB" in text
    assert "SOURCE=odoo_calls_full_v1" in text
    assert "STREAM=view_reconciliation_v1" in text
    assert "panadan_restore_825" in text
    assert "panadan-mirror-staging-pg18" in text
    assert "panadan-mirror-data-restore-drill-pg18" in text
    assert "HostConfig.NetworkMode" in text
    assert "127.0.0.1:55432" in text
    assert "flock -n 8" in text
    assert "age -r" in text and "age -d" in text
    assert "pg_dump" in text and "pg_restore -l" in text
    assert "integrity_check" in text
    assert "write_progress" in text
    assert "supervised-progress.state" in text
    assert "active_import=1" in text and "active_import=0" in text
    assert "docker compose up" not in text
    assert "docker network connect" not in text
    assert "docker network create" not in text
    assert "TRUNCATE " not in text
    assert "DROP DATABASE" not in text


def test_page_helper_accepts_only_1_to_3_supervised_pages_and_disk_floor():
    source = CHILD.read_text()
    assert "PAGES=3" in source
    assert "PAGE_SIZE=100" in source
    assert '1|2|3) PAGES="$PANADAN_MIRROR_PAGE_LIMIT"' in source
    assert "PANADAN_MIRROR_MIN_AVAILABLE_KIB" in source
    assert "6291456" in source
    assert "check_disk_floor" in source
    assert "trap on_exit EXIT" in source
    assert "flock -n 9" in source
    assert "--log-driver=none" in source
    assert source.count("--log-driver=none") == 2
    assert "MAX_WIRE_BYTES" not in source  # transport enforces it


def test_unapproved_page_override_fails_before_any_database_access(tmp_path):
    env = dict(os.environ, HOME=str(tmp_path),
               PANADAN_MIRROR_PAGE_LIMIT="4")
    result = subprocess.run(
        ["bash", str(CHILD), "next-batch", *FLAGS],
        capture_output=True, text=True, env=env)
    assert result.returncode == 2
    assert "Only 1, 2 or 3 staging pages" in result.stderr
