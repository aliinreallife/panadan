"""Synthetic-only safety tests for full second reconciliation pass.

Never access Odoo, staging, credentials or production infrastructure.
"""
from pathlib import Path
import os
import subprocess

import pytest


RUNNER = Path("tools/run-odoo-mirror-staging-reconcile-pass2.sh")
CHILD = Path("tools/run-odoo-mirror-staging-next.sh")
ACKS = [
    "--ack-source-contract",
    "--ack-retention",
    "--ack-copy",
    "--ack-sensitive-data",
]


@pytest.mark.parametrize("script", [RUNNER, CHILD])
def test_reconciliation_shell_syntax(script):
    result = subprocess.run(["bash", "-n", str(script)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("args", [
    [], ["reconcile-pass-2"],
    ["reconcile-pass-2", *ACKS[:-1]],
    ["reconcile-pass-2", ACKS[0], ACKS[0], ACKS[1], ACKS[2]],
    ["reconcile-pass-1", *ACKS],
])
def test_unsafe_invocation_fails_before_sudo(args):
    result = subprocess.run(["bash", str(RUNNER), *args],
                            capture_output=True, text=True, timeout=5)
    assert result.returncode == 2
    assert "Usage" in result.stderr or "approval" in result.stderr


def test_replay_runner_is_staging_only_resumable_and_disk_bounded():
    s = RUNNER.read_text(encoding="utf-8")
    assert "set -euo pipefail" in s
    assert "set +x" in s
    assert "umask 077" in s
    assert "STAGE=panadan-mirror-staging-pg18" in s
    assert "RESTORE=panadan-mirror-data-restore-drill-pg18" in s
    assert "SOURCE=odoo_calls_full_v1" in s
    assert "STREAM=view_reconciliation_v1" in s
    assert "flock -n 8" in s
    assert "panadan_restore_95912" in s
    assert "BASELINE_RECORDS=95912" in s
    assert "BASELINE_PAGES=975" in s
    assert "PAGE_BUDGET=2600" in s
    assert "BACKUP_EVERY_PAGES=300" in s
    assert "MIN_AVAILABLE_KIB=6291456" in s
    assert "BACKUP_RESERVE_KIB=131072" in s
    assert "PANADAN_MIRROR_EXPECTED_PASS=2" in s
    assert "PANADAN_MIRROR_PAGE_LIMIT=3" in s
    assert 'PANADAN_MIRROR_MIN_AVAILABLE_KIB="$MIN_AVAILABLE_KIB"' in s
    assert "while (( pass == 2 ))" in s
    assert '"$pass" == 3 && "$cursor" == 0' in s
    assert "staging source disabled" in s
    assert "run-odoo-mirror-staging-next.sh" in s
    assert "LAST_BACKUP_PAGES" in s
    assert "pg_dump" in s and "pg_restore -l >/dev/null && cat >/dev/null" in s
    assert "age -r" in s and "age -d" in s
    assert "revision_no>=1" in s
    assert "current_digest=digest" in s
    assert "TRUNCATE " not in s
    assert "DELETE FROM " not in s
    assert "DROP DATABASE" not in s
    assert "docker compose" not in s
    assert "docker network connect" not in s


def test_child_requires_explicit_pass_2_override_and_stops_at_pass_3():
    s = CHILD.read_text(encoding="utf-8")
    assert "PASS_TO_RUN=1" in s
    assert '2) PASS_TO_RUN=2' in s
    assert "Only reconciliation pass 2 is a valid explicit override" in s
    assert "NEXT_PASS=$((PASS_TO_RUN + 1))" in s
    assert '"$pass" == "$NEXT_PASS" && "$cursor" == 0' in s
    assert '"$pass" == "$PASS_TO_RUN" && "$cursor" -gt "$before"' in s
    assert '"$pass" == 1 && "$cursor" -gt 0' in s
    assert "flock -n 9" in s
    assert "check_disk_floor" in s
    assert "trap on_exit EXIT" in s
    assert s.count("--log-driver=none") == 2
    assert "--network container:panadan-vpn-1" in s
    assert "PANADAN_FULL_MIRROR_TARGET_MODE=isolated-staging" in s


def test_valid_approvals_reach_sudo_gate_without_touching_databases(tmp_path):
    """Catch the former escaped ${1:-} bug with a real shell invocation.

    A fake sudo blocks execution before any Docker/database operation.
    No repository secrets, real Odoo source, or staging are used.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("age", "age-keygen", "sudo"):
        command = bin_dir / name
        command.write_text("#!/bin/sh\\nexit 73\\n".replace("\\n", "\n"))
        command.chmod(0o700)

    env = dict(os.environ)
    env["HOME"] = str(tmp_path)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    run = subprocess.run(
        ["bash", str(RUNNER), "reconcile-pass-2", *ACKS],
        capture_output=True, text=True, env=env, timeout=10,
    )
    assert run.returncode == 73, (run.stdout, run.stderr)
    assert "Usage:" not in run.stderr
    assert "FAIL: Exactly four" not in run.stderr


def test_reconciliation_bash_expansions_are_not_escaped():
    s = RUNNER.read_text(encoding="utf-8")
    assert "\\${" not in s
    assert '"${1:-}" != reconcile-pass-2' in s
    assert '"${BASH_SOURCE[0]}"' in s
    assert '"${1:-0}"' in s
