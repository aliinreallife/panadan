"""Offline admin sync-status tests: no Odoo, staging or Docker required."""
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from server import mirror_health as health

NOW = datetime(2026, 11, 9, 6, 10, tzinfo=timezone.utc)


def sample(**overrides):
    value = {
        "version": 1,
        "generated_at": "2026-11-09T06:09:00+00:00",
        "database_ok": True,
        "timer_active": True,
        "vpn_healthy": True,
        "service_ok": True,
        "disk_free_bytes": 7_100_000_000,
        "records": 97038,
        "revisions": 98719,
        "pages": 58,
        "last_commit": "2026-11-09T06:05:24Z",
        "completed_through": "2026-11-09T06:05:00+00:00",
        "last_processed": None,
        "window_upper": None,
        "source_enabled": False,
    }
    value.update(overrides)
    return value


def test_caught_up_and_catching_up_have_distinct_states():
    result = health.evaluate(sample(), now=NOW)
    assert result["state"] == "caught_up"
    assert result["records"] == 97038
    assert result["lag_seconds"] == 300
    assert result["detail"] == "telemetry_only"

    progress = health.evaluate(sample(
        last_processed="2026-11-08T12:07:50Z",
        window_upper="2026-11-09T06:09:00Z",
        completed_through="2026-11-05T00:00:00Z",
    ), now=NOW)
    assert progress["state"] == "catching_up"
    assert progress["window_upper"].startswith("2026-11-09")


@pytest.mark.parametrize(("changes", "expected"), [
    ({"timer_active": False}, "paused"),
    ({"vpn_healthy": False}, "vpn_down"),
    ({"service_ok": False}, "service_failed"),
    ({"disk_free_bytes": 1024}, "disk_low"),
    ({"database_ok": False}, "unavailable"),
    ({"completed_through": "2026-11-08T00:00:00Z"}, "behind"),
    ({"generated_at": "2026-11-09T06:00:00Z"}, "unavailable"),
])
def test_health_reason_states(changes, expected):
    assert health.evaluate(sample(**changes), now=NOW)["state"] == expected


def test_untrusted_health_file_and_missing_mount_fail_closed(tmp_path, monkeypatch):
    path = tmp_path / "mirror-health.json"
    monkeypatch.setattr(health, "HEALTH_FILE", path)
    assert health.load_admin_mirror_health()["state"] == "not_configured"
    path.write_text("not json", encoding="utf-8")
    assert health.load_admin_mirror_health()["state"] == "unavailable"
    path.write_text(json.dumps(sample(customer_phone="0123456789")))
    assert health.load_admin_mirror_health()["state"] == "unavailable"
    path.write_text(json.dumps(sample()))
    # A timestamp from 2026 must not be treated as fresh at test run time.
    assert health.load_admin_mirror_health()["state"] == "unavailable"

    target = tmp_path / "target"
    target.write_text(json.dumps(sample()))
    path.unlink()
    path.symlink_to(target)
    assert health.load_admin_mirror_health()["state"] == "unavailable"


def test_counter_boolean_and_future_time_rejected():
    with pytest.raises(ValueError):
        health.evaluate(sample(records=True), now=NOW)
    with pytest.raises(ValueError):
        health.evaluate(sample(generated_at="2026-11-09T06:15:00Z"), now=NOW)
    with pytest.raises(ValueError):
        health.evaluate(sample(last_processed="2026-11-09T08:00:00Z",
                               window_upper="2026-11-09T07:00:00Z"), now=NOW)


def _publisher():
    name = "publish-odoo-mirror-admin-health"
    path = Path("tools") / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_host_publisher_uses_only_aggregate_metadata(monkeypatch, tmp_path):
    publish = _publisher()
    db = {
        "database": "panadan_ci", "version": "180006",
        "snapshot_pass": "3", "snapshot_last_id": "0",
        "source_enabled": False, "records": 97038,
        "revisions": 98719, "pages": 58,
        "completed_through": "2026-11-09T06:05:00+00:00",
        "last_processed": None, "window_upper": None,
        "last_commit": "2026-11-09T06:05:24Z",
    }
    def fake_command(args, timeout=15):
        if args[:2] == ["systemctl", "is-active"]:
            return "active"
        if args[:2] == ["systemctl", "show"]:
            return "success"
        if args[:2] == ["docker", "inspect"]:
            return "healthy"
        if args[:2] == ["docker", "port"]:
            return "127.0.0.1:55432"
        if args[:2] == ["docker", "exec"]:
            return json.dumps(db)
        raise AssertionError(args)

    monkeypatch.setattr(publish, "command", fake_command)
    monkeypatch.setattr(
        publish.shutil, "disk_usage",
        lambda _: SimpleNamespace(free=7_100_000_000))
    value = publish.collect(now=NOW)
    assert value["timer_active"] and value["vpn_healthy"]
    assert value["database_ok"] and value["records"] == 97038
    assert set(value) == health._FIELDS
    path = tmp_path / "health" / "mirror-health.json"
    monkeypatch.setattr(publish, "OUT", path)
    publish.publish(value, path=path)
    assert json.loads(path.read_text()) == value
    assert path.stat().st_mode & 0o777 == 0o644
    assert health.evaluate(value, now=NOW)["state"] == "caught_up"


def test_publisher_degrades_safely_when_vpn_or_postgres_missing(monkeypatch):
    publish = _publisher()
    def fail_command(args, timeout=15):
        raise RuntimeError("secret connection string should not leak")
    monkeypatch.setattr(publish, "command", fail_command)
    monkeypatch.setattr(
        publish.shutil, "disk_usage",
        lambda _: SimpleNamespace(free=7_100_000_000))
    value = publish.collect(now=NOW)
    assert not value["database_ok"]
    assert value["records"] is None
    assert "secret" not in json.dumps(value)


def test_admin_health_installer_requires_ack_and_pinned_release():
    script = Path("tools/install-odoo-mirror-admin-health-systemd.sh")
    check = subprocess.run(["bash", "-n", str(script)],
                           capture_output=True, text=True)
    assert check.returncode == 0, check.stderr
    args = subprocess.run(
        ["bash", str(script), "install"], capture_output=True,
        text=True, timeout=5)
    assert args.returncode == 2
    assert "Usage" in args.stderr
    body = script.read_text()
    assert "ack-admin-health-publisher" in body
    assert 'git -C "$ROOT" archive --format=tar "$REV"' in body
    assert "sudo -n chown -R root:root" in body
    assert "systemctl start panadan-mirror-health-publisher.service" in body
    assert "systemctl enable --now panadan-mirror-health-publisher.timer" in body
    assert "OnCalendar=*:0/1" in body
    assert "docker compose" not in body
    assert "DELETE FROM" not in body
    assert "pg_dump" not in body
    assert "run-odoo-mirror-incremental-cycle.sh" not in body


def test_admin_js_never_interprets_remote_status_as_html():
    src = Path("static/mirror-health.js").read_text()
    assert "/dashboard/mirror-health" in src
    assert "textContent" in src
    assert "innerHTML" not in src
    assert "setInterval" in src
    page = Path("templates/dashboard.html").read_text()
    assert "session.role == 'admin'" in page
    assert "mirror-health-panel" in page
