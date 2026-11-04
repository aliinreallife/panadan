"""Regression guards for the operator-only staging continuation entrypoint.

These tests use synthetic source only; never connect to Odoo or PostgreSQL.
"""
from pathlib import Path
import subprocess


SCRIPT = Path("tools/run-odoo-mirror-staging-next.sh")


def test_continuation_shell_parses():
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_staging_transport_is_bounded_and_does_not_join_live_db_networks():
    script = SCRIPT.read_text(encoding="utf-8")
    assert "set -euo pipefail" in script
    assert "set +x" in script
    assert 'PAGES=3' in script
    assert 'PAGE_SIZE=100' in script
    assert "--after-id \"$before\"" in script
    assert "--network container:panadan-vpn-1" in script
    assert "--network host" in script
    assert "--log-driver=none" in script
    assert script.count("--log-driver=none") == 2
    assert "PANADAN_FULL_MIRROR_TARGET_MODE=isolated-staging" in script
    assert "PANADAN_FULL_MIRROR_STAGING_ISOLATED=YES" in script
    assert "PANADAN_FULL_MIRROR_STAGING_WRITER_DSN_FILE" in script
    assert "trap on_exit EXIT" in script
    assert "flock -n 9" in script
    assert "SOURCE=\"odoo_calls_full_v1\"" in script
    assert "stream='view_reconciliation_v1'" in script
    assert "pass" in script and "cursor" in script
    assert "disable ||" in script
    assert "docker network connect" not in script
    assert "docker compose up" not in script
    assert "docker network create" not in script
    assert "DELETE FROM" not in script
    assert "TRUNCATE" not in script
    assert "DROP " not in script


def test_resume_has_no_new_pass_or_stale_cursor_and_enforces_memory_limits():
    script = SCRIPT.read_text(encoding="utf-8")
    assert '"$pass" == 1 && "$cursor" -gt 0' in script
    assert '"$cursor" == "$max_id"' in script
    assert '"$records" -ge 275' in script
    assert '--memory=512m' in script
    assert script.count('--memory=512m') == 2
    assert '--after-id "$before"' in script
    assert "ENABLED=1" in script
    assert "trap on_exit EXIT" in script
    assert 'disable ||' in script
    assert 'PAGES=3' in script
    assert 'PAGE_SIZE=100' in script
