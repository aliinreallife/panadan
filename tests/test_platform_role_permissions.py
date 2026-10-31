"""Synthetic-only, opt-in PostgreSQL 18 least-privilege integration tests.

Runs ONLY on dedicated panadan_ci loopback DB with explicit reset opt-in.
Never attempts any Odoo connection or reads personal customer data.
"""
import os
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg.errors import InsufficientPrivilege
import pytest

from server.platform_ingest import SourceEvent, ingest_batch, register_source
from server.platform_processing import process_next


WRITER_PASSWORD = "synthetic_writer_test_password_only"
READER_PASSWORD = "synthetic_reader_test_password_only"


@pytest.fixture(scope="module")
def protected_db():
    dsn = os.environ.get("PANADAN_PLATFORM_TEST_DSN")
    if not dsn:
        pytest.skip("No disposable panadan_ci PostgreSQL DSN")
    cfg = conninfo_to_dict(dsn)
    if (cfg.get("dbname") != "panadan_ci"
            or cfg.get("host") not in ("127.0.0.1", "localhost")
            or os.environ.get("PANADAN_PLATFORM_TEST_ALLOW_RESET") != "YES"):
        pytest.fail("Refusing to modify any non-disposable PostgreSQL database")

    with psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as owner:
        owner.execute(Path("database/migrations/001_multisource_foundation.sql").read_text())
        # No actual credentials are used: these literal passwords are unique
        # to the disposable CI PostgreSQL container and destroyed afterwards.
        owner.execute("""
        DO $roles$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='panadan_ingest_writer') THEN
            CREATE ROLE panadan_ingest_writer LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
          END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='panadan_report_reader') THEN
            CREATE ROLE panadan_report_reader LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
          END IF;
        END
        $roles$;
        ALTER ROLE panadan_ingest_writer PASSWORD 'synthetic_writer_test_password_only';
        ALTER ROLE panadan_report_reader PASSWORD 'synthetic_reader_test_password_only';
        """)
        perms = Path("database/permissions/002_platform_runtime_roles.sql").read_text()
        owner.execute(perms)
        # Grant/VIEW migration must be safely re-applicable.
        owner.execute(perms)
        register_source(owner, source_key="roles_synthetic", kind="manual",
                        label="Disposable permission fixture")
        owner.execute("""
            UPDATE panadan_ingest.sources
            SET enabled = TRUE WHERE source_key = 'roles_synthetic'
        """)
        yield cfg, owner


def _as_role(cfg, role, password):
    return psycopg.connect(
        host=cfg["host"], port=cfg.get("port", "5432"),
        dbname="panadan_ci", user=role, password=password,
        autocommit=True, row_factory=dict_row,
        connect_timeout=5,
    )


def test_ingestion_writer_can_process_but_cannot_enable_sources(protected_db):
    cfg, owner = protected_db
    with _as_role(cfg, "panadan_ingest_writer", WRITER_PASSWORD) as writer:
        assert writer.execute("SELECT enabled FROM panadan_ingest.sources WHERE source_key='roles_synthetic'").fetchone()["enabled"]
        with pytest.raises(InsufficientPrivilege):
            writer.execute("UPDATE panadan_ingest.sources SET enabled=FALSE WHERE source_key='roles_synthetic'")
        with pytest.raises(InsufficientPrivilege):
            writer.execute("INSERT INTO panadan_ingest.sources(source_key,kind,label) VALUES ('forbidden','manual','Never')")
        assert not writer.execute("SELECT has_schema_privilege(current_user,'panadan_ingest','CREATE') AS ok").fetchone()["ok"]
        result = ingest_batch(
            writer, source_key="roles_synthetic", stream="history",
            events=[SourceEvent("synthetic-7", "upsert", {
                "tellside":"IntoOut", "voice_length":42,
                "customer_phone":"PRIVATE_SHOULD_NEVER_APPEAR",
                "transcript":"PRIVATE_SHOULD_NEVER_APPEAR",
            })],
            expected_cursor=None, next_cursor={"last_id":7},
        )
        assert result.upserted == 1
        assert process_next(writer)

    assert owner.execute("SELECT COUNT(*) AS n FROM panadan_ingest.raw_revisions WHERE source_key='roles_synthetic'").fetchone()["n"] == 1


def test_reporting_reader_only_sees_projected_current_safe_facts(protected_db):
    cfg, owner = protected_db
    with _as_role(cfg, "panadan_report_reader", READER_PASSWORD) as reader:
        facts = reader.execute("""
            SELECT revision_id, fact_key, fact_value
            FROM panadan_ingest.safe_call_facts_v1
            WHERE source_key = 'roles_synthetic' ORDER BY fact_key
        """).fetchall()
        assert {row["fact_key"] for row in facts} == {"call_direction", "recording_duration"}
        assert all("PRIVATE_SHOULD_NEVER_APPEAR" not in str(row) for row in facts)
        assert "external_id" not in facts[0]
        assert all(isinstance(row["revision_id"], int) for row in facts)
        for sql in (
            "SELECT * FROM panadan_ingest.raw_revisions LIMIT 1",
            "SELECT * FROM panadan_ingest.source_records LIMIT 1",
            "SELECT * FROM panadan_ingest.sources LIMIT 1",
            "SELECT * FROM panadan_ingest.derived_facts LIMIT 1",
            "INSERT INTO panadan_ingest.sync_runs(source_key,stream) VALUES('roles_synthetic','bad')",
            "CREATE TABLE panadan_ingest.not_allowed(n integer)",
            "CREATE TABLE public.not_allowed(n integer)",
        ):
            with pytest.raises(InsufficientPrivilege):
                reader.execute(sql)
        assert not reader.execute("SELECT has_database_privilege(current_user,current_database(),'CREATE') AS ok").fetchone()["ok"]
        assert not reader.execute("SELECT has_database_privilege(current_user,current_database(),'TEMP') AS ok").fetchone()["ok"]


def test_roles_are_non_superusers_and_grants_are_narrow(protected_db):
    _, owner = protected_db
    rows = owner.execute("""
        SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls
        FROM pg_roles WHERE rolname IN ('panadan_ingest_writer','panadan_report_reader')
        ORDER BY rolname
    """).fetchall()
    assert len(rows) == 2
    assert all(not row[key] for row in rows for key in
               ("rolsuper", "rolcreatedb", "rolcreaterole",
                "rolreplication", "rolbypassrls"))
    assert not owner.execute("""
      SELECT has_table_privilege('panadan_report_reader',
        'panadan_ingest.raw_revisions','SELECT') AS allowed
    """).fetchone()["allowed"]
    assert not owner.execute("""
      SELECT has_table_privilege('panadan_ingest_writer',
        'panadan_ingest.sources','UPDATE') AS allowed
    """).fetchone()["allowed"]
