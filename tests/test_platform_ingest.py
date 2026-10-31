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


def test_platform_pg_version_is_18(pg):
    """The Panadan-owned integration server is PG18, independent of Odoo."""
    version = pg.execute("SHOW server_version_num").fetchone()["server_version_num"]
    assert 180000 <= int(version) < 190000


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


def test_versioned_processing_extracts_safe_facts_only(pg):
    from server.platform_processing import public_call_facts, process_next
    payload = {
        "tellside": "IntoOut", "tellstate": "FirstToch",
        "aicallinfostate": "SoldOut", "voice_length": 178,
        "possibility_of_sale_ai": 50, "transcription": "SENSITIVE-TRANSCRIPT",
        "customertell": "09120000000", "customername": "PRIVATE-NAME",
    }
    facts = public_call_facts(payload)
    assert facts["call_direction"] == {"code":"IntoOut","meaning":"outgoing"}
    assert facts["ai_sales_estimate"]["is_confirmed_sale"] is False
    assert facts["recording_duration"] == {"seconds":178}
    assert "customername" not in facts and "transcription" not in facts
    assert "customertell" not in facts

    _enable(pg, "extract")
    assert ingest_batch(
        pg, source_key="extract", stream="feed",
        events=[SourceEvent("42","upsert",payload)],
        expected_cursor=None, next_cursor={"s":1}
    ) == BatchResult(1,1,0,0)
    for _ in range(50):
        if not process_next(pg):
            break
    else:
        pytest.fail("Unexpected unbounded pending processing jobs")

    rows = pg.execute(
        """SELECT fact_key, value FROM panadan_ingest.derived_facts
           WHERE revision_id IN (
             SELECT revision_id FROM panadan_ingest.raw_revisions
             WHERE source_key = 'extract')"""
    ).fetchall()
    stored = {row["fact_key"]:row["value"] for row in rows}
    assert stored["call_direction"]["meaning"] == "outgoing"
    assert stored["ai_sales_estimate"]["score_0_100"] == 50
    assert set(stored) == {
        "call_direction", "call_type", "ai_call_status",
        "recording_duration", "ai_sales_estimate",
    }
    assert "PRIVATE" not in str(stored)
    assert "09120000000" not in str(stored)
    assert "SENSITIVE-TRANSCRIPT" not in str(stored)
    assert not process_next(pg)
    # Re-running the worker is idempotent; facts belong to immutable revision.
    assert len(pg.execute(
        """SELECT fact_id FROM panadan_ingest.derived_facts
           WHERE revision_id IN (
             SELECT revision_id FROM panadan_ingest.raw_revisions
             WHERE source_key = 'extract')"""
    ).fetchall()) == 5


def test_processing_versions_keep_history_and_tombstones_out_of_current_view(pg):
    from server.platform_processing import process_next
    assert ingest_batch(
        pg, source_key="extract", stream="feed",
        events=[SourceEvent("42","upsert",{"tellside":"OutToIn"})],
        expected_cursor={"s":1}, next_cursor={"s":2}
    ) == BatchResult(1,1,0,0)
    assert process_next(pg)
    current = pg.execute(
        """SELECT r.revision_no, d.value FROM panadan_ingest.source_records s
           JOIN panadan_ingest.raw_revisions r
             ON r.source_key=s.source_key AND r.external_id=s.external_id
            AND r.revision_no=s.revision_no
           JOIN panadan_ingest.derived_facts d ON d.revision_id=r.revision_id
           WHERE s.source_key = 'extract' AND s.external_id = '42'
             AND d.fact_key='call_direction'"""
    ).fetchone()
    assert current["revision_no"] == 2
    assert current["value"]["meaning"] == "incoming"

    assert ingest_batch(
        pg, source_key="extract", stream="feed",
        events=[SourceEvent("42","delete")],
        expected_cursor={"s":2}, next_cursor={"s":3}
    ) == BatchResult(1,0,1,0)
    assert process_next(pg)
    deleted = pg.execute(
        """SELECT is_deleted FROM panadan_ingest.source_records
           WHERE source_key = 'extract' AND external_id='42'"""
    ).fetchone()
    assert deleted["is_deleted"] is True
    current_facts = pg.execute(
        """SELECT d.fact_id FROM panadan_ingest.source_records s
           JOIN panadan_ingest.raw_revisions r
             ON r.source_key=s.source_key AND r.external_id=s.external_id
            AND r.revision_no=s.revision_no
           JOIN panadan_ingest.derived_facts d ON d.revision_id=r.revision_id
           WHERE s.source_key = 'extract' AND s.external_id = '42'
             AND s.is_deleted = FALSE"""
    ).fetchall()
    assert current_facts == []


def test_cleaning_rejects_unknown_fields_and_invalid_scores():
    from server.platform_processing import public_call_facts
    assert public_call_facts({"tellside":"Unknown", "customertell":"100",
                              "voice_length":-4, "possibility_of_sale_ai":101}) == {}
    assert public_call_facts({"voice_length":True, "possibility_of_sale_ai":False}) == {}
    with pytest.raises(ValueError):
        public_call_facts("not an object")


def test_odoo_adapter_backfill_new_rows_and_old_updates_both_work(pg):
    """Synthetic source only; Panadan owns the writable CI target PostgreSQL."""
    from datetime import datetime, date, timedelta, timezone
    from server import odoo_sync_adapter as adapter
    from server import odoo_sync_coordinator as sync

    clock = datetime(2026,10,31,12,0,0,tzinfo=timezone.utc)
    def row(i, ts, status):
        return dict(
            id=i, CALLDATE=date(2026,10,31), tellstate='FollowUp',
            tellside='IntoOut', aicallinfostate=status, voice_length=180,
            possibility_of_sale_ai=50, deal_value=0,
            sync_updated_at=ts.replace(tzinfo=None),
        )

    class Result:
        def __init__(self, *, rows=None, row=None):
            self.rows = rows or []
            self.row = row
        def fetchall(self):return self.rows
        def fetchone(self):return self.row

    class OdooFixture:
        def __init__(self):
            self.clock = clock
            self.data = {i:row(i,clock-timedelta(hours=1),'Unchecked') for i in [1,2,3]}
            self.queries=[]
        def execute(self, sql, args=None):
            self.queries.append((sql,args))
            if sql==adapter.SCHEMA_SQL:
                return Result(rows=[
                    {'column_name':column,'data_type':
                     ('integer' if column=='id'
                      else 'timestamp without time zone' if column==adapter.UPDATE_COLUMN
                      else 'text')}
                    for column in adapter.COLUMNS
                ])
            if sql==adapter.SOURCE_CLOCK_SQL:
                return Result(row={'source_now':self.clock})
            if sql==adapter.ID_SQL:
                after, limit=args
                return Result(rows=sorted(
                    (r for i,r in self.data.items() if i>after),
                    key=lambda r:r['id'])[:limit])
            if sql==adapter.CHANGE_SQL:
                lo,hi,at,after_id,limit=args
                return Result(rows=sorted(
                    (r for r in self.data.values()
                     if lo<=r['sync_updated_at']<=hi
                     and (r['sync_updated_at'],r['id'])>(at,after_id)),
                    key=lambda r:(r['sync_updated_at'],r['id']))[:limit])
            raise AssertionError('Source SQL must be fixed, parameterized SELECT')
    source=OdooFixture()
    key='odoo_synthetic'
    _enable(pg,key,kind='database')

    with pytest.raises(ValueError,match='Seed update stream'):
        sync.poll_id_page(source,pg,mode='utc_naive',source_key=key,limit=2)
    seed=sync.seed_update_stream(source,pg,mode='utc_naive',source_key=key)
    assert 'completed_through' in seed
    with pytest.raises(ValueError,match='already seeded'):
        sync.seed_update_stream(source,pg,mode='utc_naive',source_key=key)
    pages=[]
    for _ in range(5):
        p=sync.poll_id_page(source,pg,mode='utc_naive',source_key=key,limit=2)
        pages.append(p)
        if not p.has_more:break
    assert [p.examined for p in pages]==[2,1]
    assert checkpoint(pg,source_key=key,stream=sync.BACKFILL_STREAM)=={'last_id':3}
    assert pg.execute(
        'SELECT COUNT(*) AS n FROM panadan_ingest.source_records WHERE source_key=%s',
        (key,)).fetchone()['n']==3

    # Two historical calls change, and two NEW calls appear. All four receive
    # the same source timestamp, so cursor ID tie-breaking is essential.
    source.clock=clock+timedelta(minutes=6)
    updated=clock+timedelta(minutes=2)
    source.data[1]=row(1,updated,'SoldOut')
    source.data[2]=row(2,updated,'FollowUp')
    source.data[4]=row(4,updated,'Unchecked')
    source.data[5]=row(5,updated,'Unchecked')
    a=sync.poll_update_page(source,pg,mode='utc_naive',source_key=key,limit=2)
    b=sync.poll_update_page(source,pg,mode='utc_naive',source_key=key,limit=2)
    c=sync.poll_update_page(source,pg,mode='utc_naive',source_key=key,limit=2)
    assert [a.examined,b.examined,c.examined]==[2,2,0]
    assert a.has_more and b.has_more and not c.has_more
    assert a.changed==2 and b.changed==2
    assert 'window' not in checkpoint(pg,source_key=key,stream=sync.UPDATES_STREAM)

    # A new call may have an old (backdated) update timestamp; ID polling
    # must still discover it independently of the change cursor.
    source.data[6]=row(6,clock-timedelta(hours=3),'Unchecked')
    next_ids=sync.poll_id_page(source,pg,mode='utc_naive',source_key=key,limit=2)
    assert next_ids.examined==2
    assert next_ids.skipped==2  # IDs 4 and 5 were already ingested by changes
    later=sync.poll_id_page(source,pg,mode='utc_naive',source_key=key,limit=2)
    assert later.changed==1 and later.cursor=={'last_id':6}
    assert pg.execute(
        'SELECT COUNT(*) AS n FROM panadan_ingest.source_records WHERE source_key=%s',
        (key,)).fetchone()['n']==6
    assert pg.execute(
        'SELECT COUNT(*) AS n FROM panadan_ingest.raw_revisions WHERE source_key=%s',
        (key,)).fetchone()['n']==8  # 3 initial + 2 edits + 2 new + backdated 6

    # Next window replays timestamp overlap; hashes avoid extra revisions.
    source.clock+=timedelta(minutes=2)
    replay=sync.poll_update_page(source,pg,mode='utc_naive',source_key=key,limit=20)
    assert replay.examined==4 and replay.changed==0 and replay.skipped==4

    assert all(sql.lstrip().upper().startswith('SELECT') for sql,_ in source.queries)
    assert all(' OFFSET ' not in sql.upper() for sql,_ in source.queries)


def test_odoo_update_poll_requires_seed_and_known_source_contract(pg):
    from datetime import datetime, timezone
    from server import odoo_sync_coordinator as sync
    from server import odoo_sync_adapter as src
    class Result:
        def __init__(self, rows=None):
            self.rows=rows or []
        def fetchall(self):return self.rows
    class MissingTimestamp:
        def execute(self, sql, params=None):
            if sql==src.SCHEMA_SQL:
                return Result([
                    {'column_name':n,'data_type':'integer' if n=='id' else 'text'}
                    for n in src.COLUMNS if n!='sync_updated_at'
                ])
            raise AssertionError('Missing schema should block before any source reads')
    _enable(pg,'odoo_unready',kind='database')
    before=pg.execute(
        'SELECT COUNT(*) AS n FROM panadan_ingest.raw_revisions WHERE source_key=%s',
        ('odoo_unready',)).fetchone()['n']
    with pytest.raises(RuntimeError,match='lacks required'):
        sync.seed_update_stream(MissingTimestamp(),pg,mode='utc_naive',
                                source_key='odoo_unready')
    assert checkpoint(pg,source_key='odoo_unready',
                      stream=sync.UPDATES_STREAM) is None
    after=pg.execute(
        'SELECT COUNT(*) AS n FROM panadan_ingest.raw_revisions WHERE source_key=%s',
        ('odoo_unready',)).fetchone()['n']
    assert before==after
