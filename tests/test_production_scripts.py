"""Safe CLI regression tests: no Docker, production data, OAuth or network."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("command", ["up", "down"])
@pytest.mark.parametrize("overlay", [
    "compose.panadan.yaml", "compose.web.release.yaml", "compose.web.https.yaml",
])
def test_legacy_prod_commands_refuse_hardened_deployments(tmp_path, command, overlay):
    (tmp_path / "data/ingress").mkdir(parents=True)
    (tmp_path / "data/ingress" / overlay).write_text("services: {}\n")
    shutil.copy2(ROOT / "panadan.sh", tmp_path / "panadan.sh")
    result = subprocess.run(
        ["bash", str(tmp_path / "panadan.sh"), command],
        text=True, capture_output=True, timeout=8,
    )
    assert result.returncode == 64
    assert "REFUSED" in result.stderr
    assert "prodctl-production.sh" in result.stderr


@pytest.mark.parametrize("script", [
    "panadan.sh", "tools/prodctl-production.sh", "tools/backup-auth-offsite.sh",
])
def test_production_shell_syntax(script):
    result = subprocess.run(
        ["bash", "-n", str(ROOT / script)], capture_output=True, text=True,
        timeout=8,
    )
    assert result.returncode == 0, result.stderr


def test_controller_missing_files_fails_closed(tmp_path):
    source = ROOT / "tools/prodctl-production.sh"
    (tmp_path / "tools").mkdir()
    shutil.copy2(source, tmp_path / "tools/prodctl-production.sh")
    result = subprocess.run(
        ["bash", str(tmp_path / "tools/prodctl-production.sh"), "check"],
        text=True, capture_output=True, timeout=8,
        env={"PATH": "/usr/bin:/bin"},
    )
    assert result.returncode != 0
    assert "MISSING" in result.stderr


def test_backup_requires_age_recipient_and_offsite_remote(tmp_path):
    (tmp_path / "tools").mkdir()
    shutil.copy2(ROOT / "tools/backup-auth-offsite.sh",
                 tmp_path / "tools/backup-auth-offsite.sh")
    result = subprocess.run(
        ["bash", str(tmp_path / "tools/backup-auth-offsite.sh"), "--check"],
        text=True, capture_output=True, timeout=8,
    )
    assert result.returncode != 0
    assert "BACKUP FAILED" in result.stderr
