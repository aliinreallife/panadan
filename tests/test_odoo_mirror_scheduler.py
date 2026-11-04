"""Synthetic-only policy and fail-closed tests for supervised mirror ticks."""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from server import odoo_mirror_scheduler as scheduler


def _status(**changed):
    data = dict(
        source_registered=True, source_enabled=True,
        processing_failed=0, processing_pending=0,
        snapshot_in_progress=False,
        seconds_since_last_commit=None, completed_passes=None,
    )
    data.update(changed)
    return data


def _args(**changed):
    options = dict(
        command="snapshot-run", mode="utc_naive",
        batch_size=100, max_pages=10,
        max_process_jobs=20, max_tick_seconds=120,
        min_pass_gap_seconds=3600, max_backlog=2000,
        ack_source_contract=True, ack_retention=True,
        ack_copy=True, ack_sensitive_data=True,
    )
    options.update(changed)
    return SimpleNamespace(**options)


@pytest.mark.parametrize(("changed", "expected"), [
    ({}, "initial"),
    ({"source_registered": False}, "disabled"),
    ({"source_enabled": False}, "disabled"),
    ({"processing_failed": 1}, "failed_processing"),
    ({"processing_pending": 2000}, "backpressure"),
    ({"snapshot_in_progress": True, "seconds_since_last_commit": 1}, "resume"),
    ({"seconds_since_last_commit": 3599}, "quiet_period"),
    ({"seconds_since_last_commit": 3600}, "new_pass"),
    ({"seconds_since_last_commit": -1}, "invalid_freshness"),
])
def test_tick_policy_is_bounded_and_safe(changed, expected):
    assert scheduler.decision(
        _status(**changed), min_pass_gap_seconds=3600,
        max_backlog=2000,
    ) == expected


@pytest.mark.parametrize("arg", [
    {"min_pass_gap_seconds": 0, "max_backlog": 2000},
    {"min_pass_gap_seconds": 300, "max_backlog": 99},
    {"min_pass_gap_seconds": 8 * 86400, "max_backlog": 2000},
    {"min_pass_gap_seconds": 300, "max_backlog": 10001},
])
def test_tick_rejects_unbounded_policy(arg):
    with pytest.raises(ValueError):
        scheduler.decision(_status(), **arg)


def test_process_backlog_calls_only_full_mirror_and_limits_work(monkeypatch):
    seen = []
    monkeypatch.setattr(scheduler.time, "monotonic", lambda: 10.0)

    def fake_processor(_target, *, source_key):
        seen.append(source_key)
        return len(seen) <= 2

    monkeypatch.setattr(scheduler, "process_next", fake_processor)
    assert scheduler.process_backlog(
        object(), max_jobs=10, deadline=11.0) == 2
    assert seen == [scheduler.pilot.SOURCE_KEY] * 3
    with pytest.raises(ValueError, match="budget"):
        scheduler.process_backlog(object(), max_jobs=2001, deadline=11.0)
    assert scheduler.process_backlog(
        object(), max_jobs=2, deadline=9.0) == 0


def test_snapshot_budget_stops_without_starting_next_pass(monkeypatch):
    events = []

    def one(_source, _target, *, limit):
        events.append(limit)
        return {
            "pass": 9, "source_rows": 100, "calls": 98,
            "changed": 1, "unchanged": 97,
            "pass_complete": len(events) == 2,
        }

    monkeypatch.setattr(scheduler.pilot, "_snapshot", one)
    monkeypatch.setattr(scheduler.time, "monotonic", lambda: 1.0)
    result = scheduler._run_snapshot_budget(
        object(), object(), pages=10, batch_size=100, deadline=20.0)
    assert events == [100, 100]
    assert result == {
        "pass": 9, "pages": 2, "source_rows": 200,
        "calls": 196, "changed": 2, "unchanged": 194,
        "pass_complete": True,
    }


def test_snapshot_budget_stops_on_page_failure(monkeypatch):
    count = 0

    def failure(_source, _target, *, limit):
        nonlocal count
        count += 1
        if count == 2:
            raise RuntimeError("synthetic page interruption")
        return {
            "pass": 1, "source_rows": 100, "calls": 100,
            "changed": 100, "unchanged": 0,
            "pass_complete": False,
        }

    monkeypatch.setattr(scheduler.pilot, "_snapshot", failure)
    monkeypatch.setattr(scheduler.time, "monotonic", lambda: 1.0)
    with pytest.raises(RuntimeError, match="interruption"):
        scheduler._run_snapshot_budget(
            object(), object(), pages=10, batch_size=100, deadline=20.0)
    assert count == 2


def test_tick_respects_approvals_disabled_source_and_pass_cadence(monkeypatch):
    fake_target = object()
    opened = {"target": 0, "source": 0}

    @contextmanager
    def owned():
        opened["target"] += 1
        yield fake_target

    @contextmanager
    def exclusive(target):
        assert target is fake_target
        yield

    @contextmanager
    def source():
        opened["source"] += 1
        yield object()

    monkeypatch.setattr(scheduler.guarded, "owned_connection", owned)
    monkeypatch.setattr(scheduler.guarded, "exclusive_pilot", exclusive)
    monkeypatch.setattr(scheduler.database, "connect", source)
    monkeypatch.setattr(scheduler, "process_backlog",
                        lambda target, *, max_jobs, deadline: 0)
    monkeypatch.setattr(scheduler.time, "monotonic", lambda: 10.0)
    monkeypatch.setattr(scheduler.pilot, "local_status",
                        lambda target: _status(source_enabled=False))

    with pytest.raises(ValueError, match="approval"):
        scheduler.tick(_args(ack_copy=False))
    assert opened == {"target": 0, "source": 0}

    with pytest.raises(ValueError, match="not explicitly enabled"):
        scheduler.tick(_args())
    assert opened == {"target": 1, "source": 0}

    monkeypatch.setattr(
        scheduler.pilot, "local_status",
        lambda target: _status(seconds_since_last_commit=10),
    )
    result = scheduler.tick(_args())
    assert result["decision"] == "quiet_period"
    assert opened["source"] == 0

    monkeypatch.setattr(
        scheduler.pilot, "local_status",
        lambda target: _status(seconds_since_last_commit=3600),
    )
    monkeypatch.setattr(
        scheduler, "_run_snapshot_budget",
        lambda source, target, *, pages, batch_size, deadline: {
            "pages": 2, "pass": 3, "pass_complete": True, "changed": 1,
        },
    )
    result = scheduler.tick(_args())
    assert result["decision"] == "new_pass"
    assert result["pages"] == 2 and result["pass_complete"]
    assert opened["source"] == 1


def test_health_signals_only_counts_and_freshness():
    assert scheduler.health(_status(source_enabled=False))["signal"] == "disabled"
    assert scheduler.health(_status(processing_failed=1))["signal"] == "processing_failed"
    assert scheduler.health(_status())["signal"] == "not_started"
    assert scheduler.health(_status(seconds_since_last_commit=90000))["signal"] == "stale"
    assert scheduler.health(_status(seconds_since_last_commit=10))["signal"] == "healthy"
    with pytest.raises(ValueError, match="threshold"):
        scheduler.health(_status(), max_stale_seconds=100)


def test_tick_budget_rejects_unbounded_or_invalid_ints(monkeypatch):
    for changes in (
        {"max_pages": 11}, {"batch_size": 101},
        {"max_process_jobs": 2001}, {"max_tick_seconds": 121},
        {"max_tick_seconds": 0},
    ):
        with pytest.raises(ValueError):
            scheduler.tick(_args(**changes))
