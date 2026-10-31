"""Opt-in PostgreSQL integration tests against a disposable CI database.

To prevent destructive test cleanup on real systems, this test module *only*
resets schema panadan_ingest when DB name is exactly panadan_ci, host is
loopback and explicit PANADAN_PLATFORM_TEST_ALLOW_RESET=YES is set.
"""
import os
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
import pytest

from server.platform_ingest import (
    BatchResult, SourceEvent, StaleCheckpointError, _validate_events,
    checkpoint, ingest_batch, register_source,
)


def test_json_validation_is_bounded_and_does_not_need_a_database():
    first = _validate_events([SourceEvent("42", "upsert", {"name": "آزمایش", "n": 1})])
    second = _validate_events([SourceEvent("42", "upsert", {"n": 1, "name": "آزمایش"})])
    assert first[0][1] == second[0][1]
    with pytest.raises(ValueError):
        _validate_events([SourceEvent("42", "upsert", {"bad": float("nan")})])
    with pytest.raises(ValueError):
        _validate_events([SourceEvent("42", "delete", {"wrong": True})])
    with pytest.raises(ValueError):
        _validate_events([SourceEvent("42", "upsert", {"big": "x" * 2_000_000})])
    with pytest.raises(ValueError):
        _validate_events([SourceEvent("42", "upsert", {"name": "ok"})] * 501)


@pytest.fixture(scope="module")
def pg():
    dsn = os.environ.get("PANADAN_PLATFORM_TEST_DSN")
    if not dsn:
        pytest.skip("PostgreSQL integration disabled; no CI test DSN")
    config = conninfo_to_dict(dsn)
    if (config.get("dbname") != "panadan_ci"
        or config.get("host") not in ("127.0.0.1", "localhost")
        or os.environ.get("PANADAN_PLATFORM_TEST_ALLOW_RESET") != "YES"):
        pytest.fail("Refusing integration test: requires dedicated loopback panadan_ci DB")
    with psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as conn:
        conn.execute("DROP SCHEMA IF EXISTS panadan_ingest CASCADE")
        schema = Path("database/migrations/001_multisource_foundation.sql").read_text()
        conn.execute(schema)
        yield conn
        conn.execute("DROP SCHEMA IF EXISTS panadan_ingest CASCADE")


def _enable(pg, key, kind="api"):
    register_source(pg, source_key=key, kind=kind, label="Synthetic test source")
    pg.execute("UPDATE panadan_ingest.sources SET enabled = TRUE WHERE source_key = %s", (key,))


def _rows(pg, table):
    # Table name is only an internal literal supplied by these tests.
    assert table in ("source_records", "raw_revisions", "processing_jobs",
                     "sync_checkpoints", "sync_runs")
    return pg.execute("SELECT * FROM panadan_ingest." + table).fetchall()


def test_source_off_by_default_and_namespaced_ids(pg):
    register_source(pg, source_key="alpha", kind="api", label="Example A")
    registered = pg.execute(
        "SELECT enabled FROM panadan_ingest.sources WHERE source_key = 'alpha'"
    ).fetchone()
    assert registered["enabled"] is False
    with pytest.raises(ValueError, match="not enabled"):
        ingest_batch(pg, source_key="alpha", stream="history",
                     events=[SourceEvent("1", "upsert", {"x": 1})],
                     expected_cursor=None, next_cursor={"seq": 1})
    assert checkpoint(pg, source_key="alpha", stream="history") is None
    _enable(pg, "alpha")
    _enable(pg, "beta", kind="file")
    for source in ("alpha", "beta"):
        result = ingest_batch(pg, source_key=source, stream="history",
                              events=[SourceEvent("1", "upsert", {"source": source})],
                              expected_cursor=None, next_cursor={"seq": 1})
        assert result == BatchResult(1, 1, 0, 0)
    items = pg.execute(
        "SELECT source_key, external_id FROM panadan_ingest.source_records WHERE external_id = '1'"
    ).fetchall()
    assert {row["source_key"] for row in items} == {"alpha", "beta"}


def test_insert_replay_update_delete_resurrection_and_checkpoint(pg):
    _enable(pg, "calls")
    first = ingest_batch(
        pg, source_key="calls", stream="changes",
        events=[SourceEvent("call-1", "upsert", {"direction": "IntoOut", "score": 50})],
        expected_cursor=None, next_cursor={"sequence": 10},
    )
    assert first == BatchResult(1, 1, 0, 0)
    assert checkpoint(pg, source_key="calls", stream="changes") == {"sequence": 10}
    assert ingest_batch(
        pg, source_key="calls", stream="changes",
        events=[SourceEvent("call-1", "upsert", {"score": 50, "direction": "IntoOut"})],
        expected_cursor={"sequence": 10}, next_cursor={"sequence": 11},
    ) == BatchResult(1, 0, 0, 1)

    assert ingest_batch(
        pg, source_key="calls", stream="changes",
        events=[SourceEvent("call-1", "upsert", {"direction": "OutToIn", "score": 70})],
        expected_cursor={"sequence": 11}, next_cursor={"sequence": 12},
    ) == BatchResult(1, 1, 0, 0)

    assert ingest_batch(
        pg, source_key="calls", stream="changes",
        events=[SourceEvent("call-1", "delete")],
        expected_cursor={"sequence": 12}, next_cursor={"sequence": 13},
    ) == BatchResult(1, 0, 1, 0)
    assert ingest_batch(
        pg, source_key="calls", stream="changes",
        events=[SourceEvent("call-1", "delete")],
        expected_cursor={"sequence": 13}, next_cursor={"sequence": 14},
    ) == BatchResult(1, 0, 0, 1)

    assert ingest_batch(
        pg, source_key="calls", stream="changes",
        events=[SourceEvent("call-1", "upsert", {"direction": "IntoOut"})],
        expected_cursor={"sequence": 14}, next_cursor={"sequence": 15},
    ) == BatchResult(1, 1, 0, 0)

    revs = pg.execute(
        """SELECT revision_no, operation, payload, digest
           FROM panadan_ingest.raw_revisions
           WHERE source_key = 'calls' AND external_id = 'call-1'
           ORDER BY revision_no"""
    ).fetchall()
    assert [r["revision_no"] for r in revs] == [1, 2, 3, 4]
    assert [r["operation"] for r in revs] == ["upsert", "upsert", "delete", "upsert"]
    assert revs[0]["payload"]["score"] == 50
    assert revs[1]["payload"]["score"] == 70
    assert revs[2]["payload"] is None
    assert revs[2]["digest"] is None
    current = pg.execute(
        """SELECT revision_no, current_digest, is_deleted
           FROM panadan_ingest.source_records
           WHERE source_key = 'calls' AND external_id = 'call-1'"""
    ).fetchone()
    assert current["revision_no"] == 4 and current["is_deleted"] is False
    jobs = pg.execute(
        """SELECT job_id FROM panadan_ingest.processing_jobs
           WHERE revision_id IN (SELECT revision_id FROM panadan_ingest.raw_revisions
                                 WHERE source_key = 'calls' AND external_id = 'call-1')"""
    ).fetchall()
    assert len(jobs) == 4
    assert checkpoint(pg, source_key="calls", stream="changes") == {"sequence": 15}


def test_old_checkpoint_cannot_overwrite_new_data(pg):
    start_count = len(_rows(pg, "raw_revisions"))
    with pytest.raises(StaleCheckpointError):
        ingest_batch(
            pg, source_key="calls", stream="changes",
            events=[SourceEvent("call-99", "upsert", {"x": 99})],
            expected_cursor={"sequence": 8}, next_cursor={"sequence": 16},
        )
    assert len(_rows(pg, "raw_revisions")) == start_count
    assert checkpoint(pg, source_key="calls", stream="changes") == {"sequence": 15}


def test_failed_job_enqueue_rolls_back_payload_and_cursor(pg):
    class FailingConnection:
        def transaction(self):
            return pg.transaction()
        def execute(self, sql, params=None):
            if "INTO panadan_ingest.processing_jobs" in sql:
                raise RuntimeError("synthetic queue failure")
            return pg.execute(sql, params)

    before = len(_rows(pg, "raw_revisions"))
    with pytest.raises(RuntimeError, match="synthetic queue"):
        ingest_batch(
            FailingConnection(), source_key="calls", stream="changes",
            events=[SourceEvent("call-atomic", "upsert", {"x": 12})],
            expected_cursor={"sequence": 15}, next_cursor={"sequence": 16},
        )
    assert checkpoint(pg, source_key="calls", stream="changes") == {"sequence": 15}
    assert len(_rows(pg, "raw_revisions")) == before
    assert pg.execute(
        "SELECT COUNT(*) AS n FROM panadan_ingest.source_records WHERE external_id = 'call-atomic'"
    ).fetchone()["n"] == 0


def test_bad_source_event_does_not_create_any_rows(pg):
    before = len(_rows(pg, "sync_runs"))
    with pytest.raises(ValueError):
        ingest_batch(
            pg, source_key="calls", stream="changes",
            events=[SourceEvent("call-abc", "upsert", {"score": 1}),
                    SourceEvent("call-xyz", "upsert", {"nan": float('nan')})],
            expected_cursor={"sequence": 15}, next_cursor={"sequence": 16},
        )
    assert len(_rows(pg, "sync_runs")) == before
    assert checkpoint(pg, source_key="calls", stream="changes") == {"sequence": 15}
