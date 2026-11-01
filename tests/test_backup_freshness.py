"""No-network tests for independent encrypted backup freshness checks."""
from datetime import datetime, timezone, timedelta
import importlib.util
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/check_backup_freshness.py"
spec = importlib.util.spec_from_file_location("backup_freshness", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

NOW = datetime(2026, 11, 1, 14, 0, tzinfo=timezone.utc)
SQLITE = "auth-20261101T090000Z-123456.sqlite.age"
PG = "panadan-20261101T110000Z-0123456789abcdef.dump.age"
ENVS = {
    "PANADAN_BACKUP_RCLONE_DEST": "offsite:panadan/auth",
    "PANADAN_PLATFORM_BACKUP_RCLONE_DEST": "offsite:panadan/owned-postgres",
}


def item(name: str, size: int = 1024) -> dict:
    return {"Name": name, "Size": size, "IsDir": False}


def test_valid_both_archives_have_independent_age_and_no_content_reads(monkeypatch, capsys):
    calls = []
    def fake(remote, include):
        calls.append((remote, include))
        return [item(SQLITE)] if "sqlite" in include else [item(PG)]
    monkeypatch.setattr(module, "read_remote", fake)
    assert module.run("both", 10, ENVS, NOW) == 0
    assert len(calls) == 2
    output = capsys.readouterr().out
    assert "PASS: sqlite" in output and "PASS: platform" in output
    assert "offsite:" not in output
    assert "123456" not in output


def test_stale_only_one_store_causes_failure(monkeypatch, capsys):
    def fake(remote, include):
        return [item(SQLITE)] if "sqlite" in include else [item("panadan-20261001T000000Z-0123456789abcdef.dump.age")]
    monkeypatch.setattr(module, "read_remote", fake)
    assert module.run("both", 10, ENVS, NOW) == 1
    captured = capsys.readouterr()
    assert "PASS: sqlite" in captured.out
    assert "FAIL: platform" in captured.err


@pytest.mark.parametrize("content", [
    [], {}, "untrusted", [item("random-file.age")],
    [item(PG, 12)],
    [item("panadan-20261103T110000Z-0123456789abcdef.dump.age")],
    [item("panadan-20260230T110000Z-0123456789abcdef.dump.age")],
])
def test_missing_invalid_future_or_tiny_archives_rejected(monkeypatch, content, capsys):
    monkeypatch.setattr(module, "read_remote", lambda remote, include: content)
    assert module.run("platform", 10, ENVS, NOW) == 1
    assert "FAIL: platform" in capsys.readouterr().err


def test_metadata_listing_failure_fails_closed_and_redacts_remote(monkeypatch, capsys):
    def failed(remote, include):
        raise RuntimeError("remote secret details")
    monkeypatch.setattr(module, "read_remote", failed)
    assert module.run("sqlite", 10, ENVS, NOW) == 1
    err = capsys.readouterr().err
    assert "metadata unavailable" in err
    assert "remote secret details" not in err


def test_config_missing_or_local_path_never_invokes_rclone(monkeypatch, capsys):
    def forbidden(*args):
        raise AssertionError("Should reject config before remote access")
    monkeypatch.setattr(module, "read_remote", forbidden)
    assert module.run("both", 24, {"PANADAN_BACKUP_RCLONE_DEST": "offsite:auth"}, NOW) == 2
    assert module.run("sqlite", 24, {"PANADAN_BACKUP_RCLONE_DEST": "/data/local"}, NOW) == 2
    assert module.run("sqlite", 24, {"PANADAN_BACKUP_RCLONE_DEST": "offsite:path\nbad"}, NOW) == 2
    assert "CONFIG ERROR" in capsys.readouterr().err


def test_recent_filename_not_remote_modtime_drives_age():
    old = item("auth-20261001T000000Z-99999.sqlite.age")
    old["ModTime"] = "2026-11-01T13:59:59Z"
    assert module.backup_age_hours([old], module.STORES["sqlite"][1], NOW) > 24
    assert module.backup_age_hours([item(SQLITE)], module.STORES["sqlite"][1], NOW) == 5


@pytest.mark.parametrize("hours", ("nan", "inf", "0", "-1", "721"))
def test_explicit_safe_threshold_required(hours):
    result = subprocess.run(
        ["python3", str(SCRIPT), "--max-age-hours", hours],
        text=True, capture_output=True, timeout=8,
    )
    assert result.returncode != 0
    assert "max-age-hours" in result.stderr


def test_read_remote_uses_metadata_only_bounded_rclone_command(monkeypatch):
    seen = []
    class Result:
        stdout = '[{"Name":"auth-20261101T090000Z-12.sqlite.age","Size":500}]'
    def fake(cmd, **kwargs):
        seen.append((cmd, kwargs))
        return Result()
    monkeypatch.setattr(module.subprocess, "run", fake)
    items = module.read_remote("offsite:auth", "auth-*.sqlite.age")
    assert len(items) == 1
    cmd, opts = seen[0]
    assert cmd[:2] == ["rclone", "lsjson"]
    assert "--files-only" in cmd and "--max-depth" in cmd
    assert "cat" not in cmd and "copy" not in cmd
    assert opts["timeout"] == 30 and opts["check"] is True
