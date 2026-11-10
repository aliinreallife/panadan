"""Offline admin sync-status tests: no Odoo, staging or Docker required."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

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
        "source_enabled": True,
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
    ({"source_enabled": False}, "not_configured"),
    ({"source_enabled": None}, "not_configured"),
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



def test_strict_consumer_contract_rejects_customer_data_and_unknown_keys():
    # Privileged publisher implementation is not part of this standalone
    # web-only PR. Validate its data contract without importing host scripts.
    good = sample()
    assert set(good) == health._FIELDS
    assert health.evaluate(good, now=NOW)["state"] == "caught_up"
    for forbidden in ("customer_phone", "odoo_dsn", "source_row_id", "transcript"):
        with pytest.raises(ValueError, match="Unexpected"):
            health.evaluate({**good, forbidden: "not exposed"}, now=NOW)


def test_consumer_does_not_claim_healthy_without_active_source():
    for source_enabled in (False, None):
        response = health.evaluate(sample(source_enabled=source_enabled), now=NOW)
        assert response["state"] != "caught_up"
        assert response["source_enabled"] is source_enabled
    # A stale publisher must never show green even when previously enabled.
    assert health.evaluate(
        sample(generated_at="2026-11-09T06:00:00+00:00"), now=NOW
    )["state"] == "unavailable"


def test_missing_publisher_is_explicitly_unconfigured_not_a_working_sync(tmp_path, monkeypatch):
    missing_file = tmp_path / "unmounted" / "mirror-health.json"
    monkeypatch.setattr(health, "HEALTH_FILE", missing_file)
    response = health.load_admin_mirror_health()
    assert response["state"] == "not_configured"
    assert response["records"] is None
    assert response["source_enabled"] is None



def test_admin_js_never_interprets_remote_status_as_html():
    src = Path("static/mirror-health.js").read_text()
    assert "/dashboard/mirror-health" in src
    assert "textContent" in src
    assert "innerHTML" not in src
    assert "setInterval" in src
    dashboard = Path("templates/dashboard.html").read_text()
    page = Path("templates/system.html").read_text()
    assert "mirror-health-panel" not in dashboard
    assert "mirror-health-panel" in page
    assert 'href="/dashboard/system"' in dashboard
    assert "وضعیت نسخهٔ محلی Odoo" in page
    assert "نمایش وضعیت هنوز متصل نشده" not in src
    assert "همگام‌سازی نسخهٔ محلی غیرفعال است" in src
