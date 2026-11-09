"""Strict read-only sync-health snapshot for the authenticated admin dashboard.

The web application NEVER connects to the staging writer, Odoo, Docker or
systemd. A separate privileged host publisher creates a whitelisted,
aggregate-only JSON snapshot and the hardened web deployment may mount that
one file read-only at /run/panadan/mirror-health.json.

A missing or stale snapshot is not a healthy sync. No customer payload,
source row ID, DSN, VPN configuration, raw SQL or tokens are exposed.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import stat

HEALTH_FILE = Path("/run/panadan/mirror-health.json")
MAX_BYTES = 8192
MAX_AGE_SECONDS = 180
FRESH_THRESHOLD_SECONDS = 600
STATUS_VALUES = frozenset({
    "caught_up", "catching_up", "vpn_down", "paused", "service_failed",
    "disk_low", "unavailable", "behind", "not_configured",
})
_FIELDS = frozenset({
    "version", "generated_at", "database_ok", "timer_active",
    "vpn_healthy", "service_ok", "disk_free_bytes",
    "records", "revisions", "pages", "last_commit",
    "completed_through", "last_processed", "window_upper",
    "source_enabled",
})


def _timestamp(value):
    if value is None:
        return None
    if type(value) is not str or len(value) > 40:
        raise ValueError("Invalid mirror timestamp")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Mirror timestamp must include UTC offset")
    return dt.astimezone(timezone.utc)


def unavailable(reason="not_configured"):
    return {
        "state": reason, "records": None, "revisions": None,
        "pages": None, "lag_seconds": None, "completed_through": None,
        "last_processed": None, "window_upper": None,
        "last_commit": None, "generated_at": None,
        "vpn_healthy": None, "timer_active": None,
        "disk_free_bytes": None, "source_enabled": None,
        "detail": "telemetry_only",
    }


def evaluate(snapshot, *, now=None):
    """Compute health without trusting publisher-defined UI status."""
    if type(snapshot) is not dict or set(snapshot) != _FIELDS:
        raise ValueError("Unexpected sync-health snapshot fields")
    if type(snapshot["version"]) is not int or snapshot["version"] != 1:
        raise ValueError("Unknown sync-health snapshot version")
    for name in ("database_ok", "timer_active", "vpn_healthy", "service_ok",
                 "source_enabled"):
        value = snapshot[name]
        if value is not None and type(value) is not bool:
            raise ValueError("Invalid mirror service boolean")
    for name in ("records", "revisions", "pages", "disk_free_bytes"):
        value = snapshot[name]
        if value is not None and (type(value) is not int or value < 0
                                  or value > 10**15):
            raise ValueError("Invalid mirror aggregate counter")
    now = now or datetime.now(timezone.utc)
    generated = _timestamp(snapshot["generated_at"])
    if generated is None or generated > now + timedelta(seconds=30):
        raise ValueError("Invalid health generation time")
    _timestamp(snapshot["last_commit"])
    completed = _timestamp(snapshot["completed_through"])
    processed = _timestamp(snapshot["last_processed"])
    upper = _timestamp(snapshot["window_upper"])
    if (processed is None) != (upper is None):
        raise ValueError("Incomplete recovery window")
    if processed is not None and processed > upper:
        raise ValueError("Recovery window timestamps out of order")
    age = (now - generated).total_seconds()
    lag = max(0, int((now - completed).total_seconds())) if completed else None
    if age > MAX_AGE_SECONDS:
        state = "unavailable"
    elif snapshot["database_ok"] is not True:
        state = "unavailable"
    elif snapshot["timer_active"] is False:
        state = "paused"
    elif snapshot["vpn_healthy"] is False:
        state = "vpn_down"
    elif snapshot["disk_free_bytes"] is not None and snapshot["disk_free_bytes"] < 6*1024**3:
        state = "disk_low"
    elif snapshot["service_ok"] is False:
        state = "service_failed"
    elif upper is not None:
        state = "catching_up"
    elif lag is None or lag > FRESH_THRESHOLD_SECONDS:
        state = "behind"
    else:
        state = "caught_up"
    return {
        "state": state,
        "records": snapshot["records"],
        "revisions": snapshot["revisions"],
        "pages": snapshot["pages"],
        "lag_seconds": lag,
        "completed_through": snapshot["completed_through"],
        "last_processed": snapshot["last_processed"],
        "window_upper": snapshot["window_upper"],
        "last_commit": snapshot["last_commit"],
        "generated_at": snapshot["generated_at"],
        "vpn_healthy": snapshot["vpn_healthy"],
        "timer_active": snapshot["timer_active"],
        "disk_free_bytes": snapshot["disk_free_bytes"],
        "source_enabled": snapshot["source_enabled"],
        "detail": "telemetry_only",
    }


def load_admin_mirror_health():
    """Fail to unavailable rather than reveal filesystem/parse errors."""
    try:
        path = HEALTH_FILE
        mode = path.lstat().st_mode
        if not stat.S_ISREG(mode):
            return unavailable("unavailable")
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            with os.fdopen(fd, "rb") as stream:
                raw = stream.read(MAX_BYTES + 1)
        except BaseException:
            raise
        if len(raw) > MAX_BYTES:
            return unavailable("unavailable")
        return evaluate(json.loads(raw))
    except FileNotFoundError:
        return unavailable("not_configured")
    except (OSError, ValueError, TypeError, KeyError, UnicodeError):
        return unavailable("unavailable")
