"""Offline safety checks for explicitly installed five-minute sync service."""
from pathlib import Path
import subprocess


SCRIPT = Path("tools/install-odoo-mirror-incremental-systemd.sh")
CYCLE = Path("tools/run-odoo-mirror-incremental-cycle.sh")


def test_install_entrypoint_parses():
    for script in (SCRIPT, CYCLE):
        check = subprocess.run(["bash", "-n", str(script)],
                               capture_output=True, text=True)
        assert check.returncode == 0, check.stderr


def test_install_requires_explicit_sensitive_data_schedule_approval():
    for args in ([], ["install"], ["install", "--wrong"],
                 ["install", "--ack-scheduled-sensitive-sync", "--extra"]):
        r = subprocess.run(
            ["bash", str(SCRIPT), *args],
            capture_output=True, text=True, timeout=5,
        )
        assert r.returncode == 2
        assert "Usage" in r.stderr


def test_installer_never_executes_user_writable_repo_as_root():
    s = SCRIPT.read_text()
    assert "set -euo pipefail" in s
    assert "set +x" in s and "umask 077" in s
    assert "git -C \"$ROOT\" status --porcelain" in s
    assert 'git -C "$ROOT" archive --format=tar "$REV"' in s
    assert "server tools/run-odoo-mirror-incremental-cycle.sh" in s
    assert "sudo -n tar -xf - -C \"$DEST\" --no-same-owner" in s
    assert "sudo -n chown -R root:root \"$DEST\"" in s
    assert "sudo -n chmod -R go-w \"$DEST\"" in s
    assert "ExecStart=/usr/bin/bash $DEST/tools/run-odoo-mirror-incremental-cycle.sh cycle" in s
    assert "NoNewPrivileges=true" in s
    assert "ProtectSystem=full" in s
    assert "OnCalendar=*:0/5" in s
    assert "Persistent=true" in s
    assert "panadan-mirror-incremental.timer" in s
    assert "systemctl enable --now" in s
    assert "STAGE=panadan-mirror-staging-pg18" in s
    assert "127.0.0.1:55432" in s
    assert "source_key='odoo_calls_full_v1'" in s
    assert "ack-scheduled-sensitive-sync" in s
    assert "pg_dump" not in s and "age -r" not in s
    assert "docker compose up" not in s
    assert "docker network connect" not in s
    assert "DROP DATABASE" not in s
    assert "DELETE FROM" not in s


def test_cycle_has_no_implicit_full_replay_or_privileged_host_code_dependency():
    s = CYCLE.read_text()
    assert "STREAM=created_or_modified_v1" in s
    assert "MAX_PAGES=10" in s
    assert "MIN_AVAILABLE_KIB=6291456" in s
    assert "flock -n 9" in s
    assert 'USER_ID="$(id -u panafor)"' in s
    assert 'GROUP_ID="$(id -g panafor)"' in s
    assert '--user "$USER_ID:$GROUP_ID"' in s
    assert "run-odoo-mirror-staging-full-pass.sh" not in s
    assert "run-odoo-mirror-staging-reconcile-pass2.sh" not in s
    assert "odoo_mirror_parity_stream" not in s
    assert "pg_dump" not in s
    assert "PANADAN_MIRROR_EXPECTED_PASS" not in s


def test_status_is_read_only_and_contains_no_sensitive_fields():
    status = Path("tools/check-odoo-mirror-incremental-status.sh")
    result = subprocess.run(["bash", "-n", str(status)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    source = status.read_text()
    assert "created_or_modified_v1" in source
    assert "view_reconciliation_v1" in source
    assert "panadan-mirror-staging-pg18" in source
    assert "source_enabled=" in source
    assert "incremental_checkpoint=" in source
    assert "last_incremental_commit=" in source
    assert "customername" not in source
    assert "transcription" not in source
    assert "DELETE FROM" not in source
    assert "pg_dump" not in source
