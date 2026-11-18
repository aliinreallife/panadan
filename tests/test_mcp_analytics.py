"""Synthetic-only tests for bounded, consent-aware Panadan MCP analytics.

No Stytch, customer PostgreSQL, network or real calls are needed.
"""
from datetime import date
from unittest.mock import Mock

import pytest

from server import database, mcp_tools
from server.mcp_inputs import MCPInputError, compare_values, date_window, page


def test_mcp_input_rejects_ambiguous_dates_and_clamped_paging():
    assert date_window("2026-11-01", "2026-11-30", required=True, max_days=31) == (
        date(2026, 11, 1), date(2026, 11, 30))
    assert page(100, 10000) == (100, 10000)
    for after, before in [
        ("11/01/2026", "2026-11-30"),
        ("2026-02-30", "2026-03-01"),
        ("2026-11-02", "2026-11-01"),
    ]:
        with pytest.raises(MCPInputError):
            date_window(after, before)
    with pytest.raises(MCPInputError):
        date_window("2026-01-01", "2026-02-01", required=True, max_days=31)
    for limit, offset in [(0, 0), (101, 0), (10, -1), (10, 10001), (True, 0)]:
        with pytest.raises(MCPInputError):
            page(limit, offset)


def test_numeric_change_only_for_metrics_that_survived_projection():
    previous = {"total": 10, "sold_out": 0, "secret": "hidden"}
    current = {"total": 15, "sold_out": 3, "secret": "different"}
    result = compare_values(previous, current)
    assert result == {
        "total": {"absolute": 5, "percent": 50.0},
        "sold_out": {"absolute": 3, "percent": None},
    }


@pytest.fixture
def metrics_access(monkeypatch):
    import server.main as main
    allowed = {
        "capabilities": frozenset({"mcp:use", "metrics:read"}),
        "fields": frozenset({"id", "CALLDATE", "aicallinfostate"}),
    }
    monkeypatch.setattr(mcp_tools, "_allowed", lambda _ctx, cap, field=None:
                        allowed if cap == "metrics:read" else None)
    monkeypatch.setattr(main, "directory_operator_names",
                        lambda destination, team: None)
    return allowed


def test_compare_periods_projects_metrics_and_zero_baseline(monkeypatch, metrics_access):
    called = []
    def stats(after, before, **kwargs):
        called.append((after, before, kwargs))
        # A value may exist upstream but is not approved for this MCP app.
        if after == date(2026, 11, 1):
            return {"total": 10, "sold_out": 0, "avg_voice_length": 500}
        return {"total": 15, "sold_out": 2, "avg_voice_length": 700}
    monkeypatch.setattr(database, "stats", stats)
    result = mcp_tools.compare_call_metrics(
        "2026-11-01", "2026-11-07", "2026-11-08", "2026-11-14", ctx=object())
    assert result["previous"] == {"total": 10, "sold_out": 0}
    assert result["current"] == {"total": 15, "sold_out": 2}
    assert result["change"]["total"] == {"absolute": 5, "percent": 50.0}
    assert result["change"]["sold_out"]["percent"] is None
    assert "avg_voice_length" not in str(result)
    assert len(called) == 2


def test_compare_invalid_ranges_and_permissions_never_read_database(monkeypatch, metrics_access):
    fetch = Mock(side_effect=AssertionError("must not access reporting DB"))
    monkeypatch.setattr(database, "stats", fetch)
    assert mcp_tools.compare_call_metrics(
        "2026-11-01", "2026-11-07", "2026-11-08", "2026-11-15", ctx=object()
    )["error"] == "invalid_argument"
    assert mcp_tools.compare_call_metrics(
        "2026-11-01", "2026-11-07", "2026-11-08", "2026-11-14",
        ctx=object(), operator="Alice"
    )["error"] == "permission_denied"
    monkeypatch.setattr(mcp_tools, "_allowed", lambda *_args, **_kwargs: None)
    assert mcp_tools.compare_call_metrics(
        "2026-11-01", "2026-11-07", "2026-11-08", "2026-11-14",
        ctx=object()
    )["error"] == "permission_denied"
    fetch.assert_not_called()


def test_daily_31_day_trend_with_zero_filled_days(monkeypatch, metrics_access):
    args = []
    def daily(first, last, **kw):
        args.append((first, last, kw))
        return [{"day": "2026-11-01", "total": 2},
                {"day": "2026-11-03", "total": 3}]
    monkeypatch.setattr(database, "daily_call_counts", daily)
    out = mcp_tools.get_daily_call_counts(
        "2026-11-01", "2026-11-03", ctx=object())
    assert out["total"] == 5
    assert out["days"] == [
        {"date": "2026-11-01", "total": 2},
        {"date": "2026-11-02", "total": 0},
        {"date": "2026-11-03", "total": 3},
    ]
    assert len(args) == 1
    assert args[0][2]["operator_names"] is None


def test_daily_trend_rejects_missing_fields_and_oversized_request(monkeypatch, metrics_access):
    query = Mock(side_effect=AssertionError("no unauthorized SQL"))
    monkeypatch.setattr(database, "daily_call_counts", query)
    metrics_access["fields"] = frozenset({"id"})
    result = mcp_tools.get_daily_call_counts(
        "2026-11-01", "2026-11-03", ctx=object())
    assert result["error"] == "permission_denied"
    metrics_access["fields"] = frozenset({"id", "CALLDATE"})
    result = mcp_tools.get_daily_call_counts(
        "2026-01-01", "2026-12-31", ctx=object())
    assert result["error"] == "invalid_argument"
    query.assert_not_called()


def test_recent_calls_invalid_arguments_do_not_hit_db(monkeypatch):
    access = {"capabilities": frozenset({"calls:read", "mcp:use"}),
              "fields": frozenset({"id", "CALLDATE"})}
    monkeypatch.setattr(mcp_tools, "_allowed", lambda *_args, **_kwargs: access)
    query = Mock(side_effect=AssertionError("invalid arguments must not query"))
    monkeypatch.setattr(database, "list_calls", query)
    for opts in ({"limit": 1000}, {"offset": -1},
                 {"after": "tomorrow"}, {"after": "2026-12-01",
                                        "before": "2026-11-01"}):
        assert mcp_tools.list_recent_calls(ctx=object(), **opts)["error"] == "invalid_argument"
    query.assert_not_called()


def test_daily_sql_is_parameterized_and_read_only(monkeypatch):
    class FakeConnection:
        def __init__(self): self.commands = []
        def execute(self, query, args=None):
            self.commands.append((query, args))
            return self
        def fetchall(self):
            return [{"day": date(2026, 11, 1), "total": 2}]
    conn = FakeConnection()
    from contextlib import contextmanager
    @contextmanager
    def connected():
        conn.execute("SET TRANSACTION READ ONLY")
        yield conn
    monkeypatch.setattr(database, "connect", connected)
    result = database.daily_call_counts(date(2026, 11, 1), date(2026, 11, 3),
                                        operator="A' OR 1=1")
    assert result == [{"day": "2026-11-01", "total": 2}]
    assert conn.commands[0][0] == "SET TRANSACTION READ ONLY"
    sql, params = conn.commands[1]
    assert sql.startswith('SELECT "CALLDATE" AS day, COUNT(*) AS total')
    assert 'GROUP BY "CALLDATE"' in sql
    assert "A' OR 1=1" not in sql
    assert "A' OR 1=1" in params
    assert "customername" not in sql
    with pytest.raises(ValueError):
        database.daily_call_counts(date(2026, 1, 1), date(2026, 12, 1))
