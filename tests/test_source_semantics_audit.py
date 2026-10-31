"""Synthetic, offline checks for safe source-field correlation diagnostics."""
from contextlib import contextmanager

import pytest

from server import source_semantics_audit as semantic
from server.data_dictionary_audit import parse_offsets


class Connection:
    def __init__(self, queries):
        self.queries = queries

    def execute(self, sql, params):
        self.queries.append((sql, params))
        return self

    def fetchone(self):
        return {
            "sampled_rows": 4,
            "call_time_present": 3,
            "comparable_clock_rows": 3,
            "naive_clock_within_five_minutes": 0,
            "tehran_clock_within_five_minutes": 2,
            "tellnum_present": 4,
            "tellnum_matches_customer_last_ten_digits": 0,
        }


def test_semantics_uses_fixed_bounded_aggregate_sql(monkeypatch):
    queries = []

    @contextmanager
    def connect():
        yield Connection(queries)

    monkeypatch.setattr(semantic.database, "connect", connect)
    result = semantic.audit(limit=4, offsets=(0, 5000))
    assert [params for _, params in queries] == [(4, 0), (4, 5000)]
    assert all(sql == semantic.SEMANTICS_SQL for sql, _ in queries)
    assert result["source"] == "public.vw_danix_call_info_report"
    assert result["samples"][1]["tehran_clock_within_five_minutes"] == 2
    assert result["samples"][0]["offset"] == 0
    assert "customertell" not in result["samples"][0]
    sql = semantic.SEMANTICS_SQL
    assert "LIMIT %s OFFSET %s" in sql
    assert "ORDER BY id DESC" in sql
    assert "PERCENTILE_CONT(0.5)" in sql
    assert "::double precision" in sql
    assert "FROM public.vw_danix_call_info_report" in sql
    assert "REGEXP_REPLACE(customertell" in sql
    assert "RIGHT(customer_phone_digits, 10)" in sql
    assert sql.strip().endswith("FROM classified")
    assert not any(k in sql.upper() for k in
                   ("INSERT INTO", "UPDATE PUBLIC.", "DELETE FROM", "DROP TABLE"))


@pytest.mark.parametrize("limit, offsets", [
    (0, (0,)), (1001, (0,)), (True, (0,)), (300, ()),
    (300, (0, 1000, 5000, 7000)), (300, (-1,)), (300, (50001,)),
    (300, ["0"]), (300, (0.0,)),
])
def test_semantics_rejects_invalid_selection_without_db(monkeypatch, limit, offsets):
    monkeypatch.setattr(semantic.database, "connect",
                        lambda: pytest.fail("must not connect"))
    with pytest.raises(ValueError):
        semantic.audit(limit=limit, offsets=offsets)


@pytest.mark.parametrize("raw, expected", [
    ("0", (0,)), ("0,1000,5000", (0, 1000, 5000)),
    ("050000", None), ("50001", None), ("0,1,2,3", None),
    ("0;DROP TABLE x", None), ("-1", None), ("", None),
    ("０", None), ("1,,2", None), ("1 " , None),
])
def test_shared_offsets_parser(raw, expected):
    if expected is None:
        with pytest.raises(ValueError):
            parse_offsets(raw)
    else:
        assert parse_offsets(raw) == expected


def test_semantics_error_messages_hide_sensitive_details(monkeypatch, capsys):
    def bad_audit(**_):
        raise RuntimeError("private customer phone 09120000000 and secret password")
    monkeypatch.setattr(semantic, "audit", bad_audit)
    assert semantic.main(["--offsets", "0"]) == 2
    printed = capsys.readouterr().err
    assert "RuntimeError" in printed
    assert "09120000000" not in printed
    assert "secret password" not in printed


def test_default_semantics_audit_uses_small_bounded_slices(monkeypatch):
    queries = []
    @contextmanager
    def connect():
        yield Connection(queries)
    monkeypatch.setattr(semantic.database, "connect", connect)
    out = semantic.audit()
    assert out["limit_per_offset"] == 100
    assert [params for _, params in queries] == [
        (100, 0), (100, 1000), (100, 5000)
    ]
