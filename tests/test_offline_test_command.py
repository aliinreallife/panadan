"""Offline regression guard: test command works in detached Git worktrees."""
from pathlib import Path


def test_python_test_command_never_requires_odoo_secrets_or_vpn():
    shell = Path("panadan.sh").read_text(encoding="utf-8")
    test_case = shell.split("\n  test)\n", 1)[1].split("\n    ;;", 1)[0]
    assert "require_uv" in test_case
    assert "uv sync --locked --dev" in test_case
    assert "python -m pytest -q" in test_case
    assert 'check_config' not in test_case
    assert 'compose_dev' not in test_case
    assert '.env' not in test_case
    assert 'vpn/client.ovpn' not in test_case
