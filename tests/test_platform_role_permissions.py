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
SENSITIVE_PASSWORD = "synthetic_sensitive_test_password_only"


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
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='panadan_mirror_sensitive_reader') THEN
            CREATE ROLE panadan_mirror_sensitive_reader LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
          END IF;
        END
        $roles$;
        ALTER ROLE panadan_ingest_writer PASSWORD 'synthetic_writer_test_password_only';
        ALTER ROLE panadan_report_reader PASSWORD 'synthetic_reader_test_password_only';
        ALTER ROLE panadan_mirror_sensitive_reader PASSWORD 'synthetic_sensitive_test_password_only';
        """)
        perms = Path("database/permissions/002_platform_runtime_roles.sql").read_text()
        owner.execute(perms)
        # Grant/VIEW migration must be safely re-applicable.
        owner.execute(perms)
        mirror_perms = Path("database/permissions/003_full_mirror_safe_reporting.sql").read_text()
        owner.execute(mirror_perms)
        owner.execute(mirror_perms)
        sensitive_perms = Path("database/permissions/004_full_mirror_sensitive_detail.sql").read_text()
        owner.execute(sensitive_perms)
        owner.execute(sensitive_perms)
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
        # The writer can lock a registered source only through the owner
        # function; PostgreSQL's direct FOR SHARE requires UPDATE privilege.
        with pytest.raises(InsufficientPrivilege):
            writer.execute("SELECT enabled FROM panadan_ingest.sources WHERE source_key = 'roles_synthetic' FOR SHARE")
        assert writer.execute(
            "SELECT panadan_ingest.lock_source_for_ingest('roles_synthetic') AS ok"
        ).fetchone()["ok"] is True
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
        with pytest.raises(InsufficientPrivilege):
            reader.execute("SELECT panadan_ingest.lock_source_for_ingest('roles_synthetic')")
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


def test_source_deactivation_waits_for_ingest_lock(protected_db):
    """The locked enablement row prevents an admin disable racing an ingest."""
    cfg, owner = protected_db
    with _as_role(cfg, "panadan_ingest_writer", WRITER_PASSWORD) as writer:
        with writer.transaction():
            assert writer.execute(
                "SELECT panadan_ingest.lock_source_for_ingest('roles_synthetic') AS enabled"
            ).fetchone()["enabled"] is True
            with pytest.raises(psycopg.errors.LockNotAvailable):
                with owner.transaction():
                    owner.execute("SET LOCAL lock_timeout = '150ms'")
                    owner.execute(
                        "UPDATE panadan_ingest.sources SET enabled = FALSE WHERE source_key = 'roles_synthetic'"
                    )
        # Once the writer's transaction ends, owner can disable the source.
        owner.execute(
            "UPDATE panadan_ingest.sources SET enabled = FALSE WHERE source_key = 'roles_synthetic'"
        )
        try:
            with pytest.raises(ValueError, match="not enabled"):
                ingest_batch(writer, source_key="roles_synthetic", stream="history",
                             events=[SourceEvent("synthetic-disabled","upsert",{"tellside":"IntoOut"})],
                             expected_cursor={"last_id":7}, next_cursor={"last_id":8})
        finally:
            owner.execute(
                "UPDATE panadan_ingest.sources SET enabled = TRUE WHERE source_key = 'roles_synthetic'"
            )



def test_full_mirror_conflicting_variants_are_not_exposed_to_reporting_role(protected_db):
    """Synthetic duplicate view rows: restricted reader sees only safe facts."""
    cfg, owner = protected_db
    key = "roles_full_mirror"
    register_source(owner, source_key=key, kind="database",
                    label="Synthetic duplicate-source RBAC fixture")
    owner.execute(
        "UPDATE panadan_ingest.sources SET enabled=TRUE WHERE source_key=%s",
        (key,))

    common = {
        "id": 71, "tellside": "IntoOut", "voice_length": 45.0,
        "customername": "PRIVATE-NAME-TEST",
        "transcription": "PRIVATE-TRANSCRIPT-TEST",
    }
    event = SourceEvent("71", "upsert", {
        "id": 71, "source_schema": "odoo_view_37_v1",
        "source_rows": [
            {**common, "possibility_of_sale_ai": 25},
            {**common, "possibility_of_sale_ai": 80},
        ],
    })
    with _as_role(cfg, "panadan_ingest_writer", WRITER_PASSWORD) as writer:
        batch = ingest_batch(
            writer, source_key=key, stream="view_reconciliation_v1",
            events=[event], expected_cursor=None,
            next_cursor={"pass": 2, "last_id": 0},
        )
        assert batch.upserted == 1
        # Process all synthetic pending jobs, including this source.
        for _ in range(100):
            if not process_next(writer):
                break
        else:
            pytest.fail("Synthetic job queue did not drain")

    with _as_role(cfg, "panadan_report_reader", READER_PASSWORD) as reader:
        facts = reader.execute(
            "SELECT fact_key, fact_value FROM panadan_ingest.safe_call_facts_v1 "
            "WHERE source_key=%s ORDER BY fact_key", (key,)
        ).fetchall()
        names = {r["fact_key"] for r in facts}
        assert names == {"call_direction", "recording_duration"}
        assert "ai_sales_estimate" not in names
        assert all("PRIVATE-NAME-TEST" not in str(row) for row in facts)
        assert all("PRIVATE-TRANSCRIPT-TEST" not in str(row) for row in facts)
        with pytest.raises(InsufficientPrivilege):
            reader.execute(
                "SELECT payload FROM panadan_ingest.raw_revisions "
                "WHERE source_key=%s", (key,)
            )



def test_local_mirror_listing_enforces_scopes_and_excludes_ambiguous_operator(protected_db):
    """One combined staging test: PG SQL projection + role + Python scope."""
    from server import odoo_local_reporting as local

    cfg, owner = protected_db
    register_source(owner, source_key=local.SOURCE_KEY, kind="database",
                    label="Synthetic scoped mirror")
    owner.execute(
        "UPDATE panadan_ingest.sources SET enabled=TRUE WHERE source_key=%s",
        (local.SOURCE_KEY,))

    def variant(identity, operator_id, *, score=50, state="SoldOut"):
        return {
            "id": identity, "CALLDATE": "2026-11-04",
            "vw_danix_base_info_users": operator_id,
            "tellside": "IntoOut", "tellstate": "FirstToch",
            "aicallinfostate": state, "voice_length": 45.0,
            "possibility_of_sale_ai": score,
            "customername": "PRIVATE CUSTOMER NAME",
            "customertell": "PRIVATE CUSTOMER PHONE",
            "transcription": "PRIVATE CUSTOMER TRANSCRIPT",
        }

    def event(identity, variants):
        return SourceEvent(str(identity), "upsert", {
            "id": identity, "source_schema": "odoo_view_37_v1",
            "source_rows": variants,
        })

    records = [
        event(101, [variant(101, 11, score=20), variant(101, 11, score=90)]),
        event(102, [variant(102, 22, score=45)]),
        # One source call with divergent operator identity: fail closed
        # instead of exposing it to either operator.
        event(103, [variant(103, 11), variant(103, 22)]),
        # No verified operator: not available through a scoped read.
        event(104, [variant(104, None)]),
    ]
    with _as_role(cfg, "panadan_ingest_writer", WRITER_PASSWORD) as writer:
        ingested = ingest_batch(
            writer, source_key=local.SOURCE_KEY,
            stream="view_reconciliation_v1", events=records,
            expected_cursor=None, next_cursor={"pass": 2, "last_id": 0})
        assert ingested.upserted == 4
        with pytest.raises(InsufficientPrivilege):
            writer.execute("SELECT * FROM panadan_ingest.safe_mirror_call_listing_v1")

    with _as_role(cfg, "panadan_report_reader", READER_PASSWORD) as reader:
        eleven = local.list_calls(reader, operator_ids=[11])
        assert [r["call_id"] for r in eleven] == [101]
        assert eleven[0]["source_row_count"] == 2
        assert eleven[0]["ai_sales_score"] is None
        assert eleven[0]["tellside"] == "IntoOut"
        twenty_two = local.list_calls(reader, operator_ids=[22])
        assert [r["call_id"] for r in twenty_two] == [102]
        assert twenty_two[0]["ai_sales_score"] == 45
        assert local.count_calls(reader, operator_ids=[11]) == 1
        assert local.count_calls(reader, operator_ids=[22]) == 1
        assert local.count_calls(reader, operator_ids=[11, 22]) == 2
        assert local.count_calls(reader, operator_ids=[]) == 0
        assert local.list_calls(reader, operator_ids=[]) == []
        assert local.get_call(reader, operator_ids=[11], call_id=101)["call_id"] == 101
        assert local.get_call(reader, operator_ids=[22], call_id=101) is None
        assert local.get_call(reader, operator_ids=[11, 22], call_id=103) is None
        assert local.get_call(reader, operator_ids=[11, 22], call_id=104) is None
        assert [r["call_id"] for r in
                local.list_calls(reader, operator_ids=[11, 22], after_id=101)] == [102]
        assert all(
            "PRIVATE CUSTOMER" not in str(row)
            for row in eleven + twenty_two
        )
        with pytest.raises(InsufficientPrivilege):
            reader.execute("SELECT * FROM panadan_ingest.raw_revisions LIMIT 1")
        with pytest.raises(ValueError, match="scope"):
            local.list_calls(reader, operator_ids=None)
        with pytest.raises(ValueError, match="scope"):
            local.list_calls(reader, operator_ids=[True])
        with pytest.raises(ValueError, match="page size"):
            local.list_calls(reader, operator_ids=[11], limit=500)
        with pytest.raises(ValueError, match="identity"):
            local.get_call(reader, operator_ids=[11], call_id=-2)

    with pytest.raises(ValueError, match="Restricted"):
        local.list_calls(owner, operator_ids=[11])



def test_authenticated_local_reporting_uses_verified_scopes_only(protected_db, tmp_path):
    """Both browser and API token are bound to approved local user IDs."""
    from server import odoo_local_reporting as local
    from server.security import Store

    cfg, owner = protected_db
    register_source(owner, source_key=local.SOURCE_KEY, kind="database",
                    label="Synthetic session-scoped mirror")
    owner.execute(
        "UPDATE panadan_ingest.sources SET enabled=TRUE WHERE source_key=%s",
        (local.SOURCE_KEY,),
    )
    with _as_role(cfg, "panadan_ingest_writer", WRITER_PASSWORD) as writer:
        events = [
            SourceEvent(str(cid), "upsert", {
                "id": cid, "source_schema": "odoo_view_37_v1",
                "source_rows": [{
                    "id": cid, "CALLDATE": "2026-11-04",
                    "vw_danix_base_info_users": operator,
                    "tellside": "IntoOut",
                    "voice_length": 30.0,
                    "customername": "HIDDEN PERSONAL DATA",
                    "transcription": "HIDDEN PERSONAL TRANSCRIPT",
                }],
            })
            for cid, operator in ((301, 111), (302, 222))
        ]
        result = ingest_batch(
            writer, source_key=local.SOURCE_KEY,
            stream="user_scope_fixture", events=events,
            expected_cursor=None, next_cursor={"pass": 1, "last_id": 302},
        )
        assert result.upserted == 2

    store = Store(str(tmp_path / "isolated-authority.sqlite"))
    store.bootstrap("scope_admin", "example-very-long-bootstrap-password")
    admin_id = store.verify_login("scope_admin", "example-very-long-bootstrap-password")
    alice_id = store.create_user("reader_alice", "alice-secret-password-long", "reader")
    bob_id = store.create_user("reader_bob", "bobby-secret-password-long", "reader")
    alice_session, _ = store.create_session(alice_id)
    bob_session, _ = store.create_session(bob_id)
    _, alice_token = store.create_token("alice", "api:read", 7, owner_id=alice_id)

    with _as_role(cfg, "panadan_report_reader", READER_PASSWORD) as reader:
        assert local.list_calls_for_session(
            reader, store, session_token=alice_session) == []
        assert local.count_calls_for_session(
            reader, store, session_token=alice_session) == 0

        # Role alone, including admin role, does not grant a wildcard.
        with pytest.raises(ValueError, match="identity"):
            store.authorize_operator_scope(
                admin_id=admin_id, user_id=alice_id, operator_id=111)

        store.authorize_operator_scope(
            admin_id=admin_id, user_id=alice_id, operator_id=111,
            source_identity_verified=True)
        store.authorize_operator_scope(
            admin_id=admin_id, user_id=bob_id, operator_id=222,
            source_identity_verified=True)

        a_rows = local.list_calls_for_session(
            reader, store, session_token=alice_session)
        b_rows = local.list_calls_for_session(
            reader, store, session_token=bob_session)
        assert [r["call_id"] for r in a_rows] == [301]
        assert [r["call_id"] for r in b_rows] == [302]
        assert local.get_call_for_session(
            reader, store, session_token=alice_session, call_id=302) is None
        assert local.get_call_for_session(
            reader, store, session_token=bob_session, call_id=301) is None
        assert local.count_calls_for_session(
            reader, store, session_token=alice_session) == 1
        assert [r["call_id"] for r in local.list_calls_for_token(
            reader, store, token=alice_token)] == [301]
        assert local.get_call_for_token(
            reader, store, token=alice_token, call_id=302) is None
        assert local.count_calls_for_token(reader, store, token=alice_token) == 1
        assert all("HIDDEN PERSONAL" not in str(r) for r in a_rows + b_rows)

        for raw_session in ("fake-session", "", None):
            with pytest.raises(PermissionError):
                local.list_calls_for_session(
                    reader, store, session_token=raw_session)
        with pytest.raises(PermissionError):
            local.list_calls_for_token(
                reader, store, token="wrong-token")
        with pytest.raises(ValueError, match="Unsupported"):
            local.list_calls_for_token(
                reader, store, token=alice_token, service_scope="api:sensitive")

        # Immediate revocation of an already-issued browser session/API token.
        store.revoke_operator_scope(
            admin_id=admin_id, user_id=alice_id, operator_id=111)
        assert local.list_calls_for_session(
            reader, store, session_token=alice_session) == []
        assert local.list_calls_for_token(
            reader, store, token=alice_token) == []

        store.update_user(bob_id, "reader", None, False, admin_id)
        with pytest.raises(PermissionError):
            local.list_calls_for_session(
                reader, store, session_token=bob_session)
