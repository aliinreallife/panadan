"""No production DB/VPN needed to test the data-dictionary audit."""
from contextlib import contextmanager
import json

import pytest

from server import data_dictionary_audit as audit


class FakeResult:
    def __init__(self, *, columns=None, row=None):
        self.columns = columns
        self.row = row

    def fetchall(self):
        return self.columns

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, queries):
        self.queries = queries

    def execute(self, sql, params):
        self.queries.append((sql, params))
        if sql == audit.COLUMN_SQL:
            return FakeResult(columns=[
                {"column_name": "call_time", "data_type": "integer"},
                {"column_name": "customertell", "data_type": "character varying"},
            ])
        return FakeResult(row={
            "rows_sampled": 5,
            "call_time_present": 4,
            "customer_phone_nonempty": 3,
        })


def test_audit_uses_only_fixed_sql_and_reports_aggregates(monkeypatch):
    queries = []

    @contextmanager
    def connect():
        yield FakeConnection(queries)

    monkeypatch.setattr(audit.database, "connect", connect)
    result = audit.audit(limit=5, offsets=(0, 1000))
    assert len(queries) == 3
    assert queries[0][0] == audit.COLUMN_SQL
    assert queries[0][1] == ("public", "vw_danix_call_info_report")
    assert queries[1][0] == audit.SAMPLE_SQL
    assert queries[1][1] == (5, 0)
    assert queries[2][1] == (5, 1000)
    assert result["samples"][0]["rows_sampled"] == 5
    assert result["samples"][1]["offset"] == 1000
    assert result["columns"][1]["name"] == "customertell"
    assert "customertell" not in result["samples"][0]
    assert "FROM public.vw_danix_call_info_report" in audit.SAMPLE_SQL
    assert "LIMIT %s OFFSET %s" in audit.SAMPLE_SQL
    for sql, _ in queries:
        assert sql.lstrip().upper().startswith(("SELECT ", "WITH "))
        assert all(keyword not in sql.upper() for keyword in
                   ("INSERT INTO", "UPDATE PUBLIC.", "DELETE FROM", "DROP TABLE"))
    assert "customer_phone_nonempty" in json.dumps(result)


@pytest.mark.parametrize("limit,offsets", [
    (0, (0,)), (1001, (0,)), (True, (0,)),
    (300, ()), (300, (-1,)), (300, (0, 1000, 5000, 7000)),
    (300, (50001,)), (300, ("0",)),
])
def test_invalid_limits_rejected_before_connect(monkeypatch, limit, offsets):
    monkeypatch.setattr(audit.database, "connect",
                        lambda: pytest.fail("should never connect"))
    with pytest.raises(ValueError):
        audit.audit(limit=limit, offsets=offsets)


def test_error_output_does_not_leak_db_messages(monkeypatch, capsys):
    def fail(**_):
        raise RuntimeError("database customer phone 09120000000 / leaked secret")

    monkeypatch.setattr(audit, "audit", fail)
    assert audit.main(["--limit", "5"]) == 2
    output = capsys.readouterr()
    assert "09120000000" not in output.err
    assert "leaked secret" not in output.err


def test_query_has_bounded_sample_and_only_privacy_safe_aggregates():
    sql = audit.SAMPLE_SQL
    # Read raw phone in the source DB only to aggregate it, never return a row.
    assert "REGEXP_REPLACE(customertell" in sql
    assert "AS phone_values_match_after_losing_leading_zero" in sql
    assert "AS dates_match_if_utc_to_tehran" in sql
    assert "AS operator_names_shared_by_multiple_ids" in sql
    assert "AS call_time_matches_audio_seconds" in sql
    assert sql.rstrip().endswith("FROM sampled")
