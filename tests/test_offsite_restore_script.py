"""Non-mutating safety checks for the offsite PG restore drill wrapper."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_isolated_pg_restore_script_has_valid_bash_syntax():
    result = subprocess.run(
        ["bash", "-n", str(ROOT / "tools/verify-offsite-platform-restore.sh")],
        capture_output=True, text=True, timeout=8,
    )
    assert result.returncode == 0, result.stderr


def test_restore_script_requires_explicit_archive_and_identity():
    script = ROOT / "tools/verify-offsite-platform-restore.sh"
    result = subprocess.run(
        ["bash", str(script)], capture_output=True, text=True, timeout=8,
    )
    assert result.returncode == 2
    assert "Usage:" in result.stderr


def test_restore_script_never_touches_host_services_or_external_network():
    script = (ROOT / "tools/verify-offsite-platform-restore.sh").read_text()
    assert "--network none" in script
    assert "--tmpfs /var/lib/postgresql" in script
    assert "--single-transaction --exit-on-error" in script
    assert "--no-owner --no-acl" in script
    assert "docker rm -f" in script
    assert "ssh " not in script
    assert "docker compose down" not in script
    assert "--publish" not in script
    assert "--privileged" not in script
