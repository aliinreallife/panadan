"""M01.1: transaction-rolled-back synthetic PG18 knowledge foundation tests.

Never connect to a source database, persistent platform instance or live identity.
Offline runs exercise the DSN validator; PG checks require the disposable CI DSN.
"""
import os
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg import errors
import pytest

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "database/migrations/004_knowledge_foundation.sql"
TABLES = {"workspaces", "principals", "memberships", "policy_versions", "audit_events"}


def _validate_dsn(dsn, reset):
    try:
        cfg = conninfo_to_dict(dsn)
        valid = (
            set(cfg) == {"host", "port", "dbname", "user", "password"}
            and cfg["host"] == "127.0.0.1"
            and cfg["dbname"] == cfg["user"] == "panadan_ci"
            and cfg["password"] == "synthetic_ci_password_only"
            and 1 <= int(cfg["port"]) <= 65535
            and reset == "YES"
        )
    except (ValueError, TypeError, psycopg.Error):
        valid = False
    if not valid:
        raise ValueError("Requires explicit disposable loopback panadan_ci credentials")
    return cfg


GOOD_DSN = "postgresql://panadan_ci:synthetic_ci_password_only@127.0.0.1:5432/panadan_ci"


@pytest.mark.parametrize("dsn, reset", [
    (GOOD_DSN, ""),
    (GOOD_DSN.replace("127.0.0.1", "localhost"), "YES"),
    (GOOD_DSN.replace("127.0.0.1", "192.0.2.1"), "YES"),
    (GOOD_DSN.replace("/panadan_ci", "/panadan"), "YES"),
    (GOOD_DSN + "?hostaddr=192.0.2.1", "YES"),
    (GOOD_DSN + "?service=production", "YES"),
    (GOOD_DSN + "?options=-c%20search_path%3Dpublic", "YES"),
    (GOOD_DSN.replace("synthetic_ci_password_only", "other"), "YES"),
])
def test_dsn_guard_rejects_unsafe_targets(dsn, reset):
    with pytest.raises(ValueError, match="disposable"):
        _validate_dsn(dsn, reset)


def test_dsn_guard_accepts_only_synthetic_loopback():
    assert _validate_dsn(GOOD_DSN, "YES")["dbname"] == "panadan_ci"


@pytest.fixture
def db(monkeypatch):
    dsn = os.environ.get("PANADAN_PLATFORM_TEST_DSN")
    if not dsn:
        pytest.skip("No disposable panadan_ci PostgreSQL DSN")
    try:
        cfg = _validate_dsn(dsn, os.environ.get("PANADAN_PLATFORM_TEST_ALLOW_RESET"))
    except ValueError:
        pytest.fail("Refusing unsafe knowledge foundation test target")
    # Prevent libpq inherited service/hostaddr/options from redirecting a connection.
    for name in tuple(os.environ):
        if name.startswith("PG"):
            monkeypatch.delenv(name, raising=False)
    conn = psycopg.connect(**cfg, connect_timeout=5)
    try:
        assert conn.execute(
            "SELECT current_database(), session_user, current_setting('server_version_num')::int / 10000"
        ).fetchone() == ("panadan_ci", "panadan_ci", 18)
        assert conn.execute("SELECT to_regnamespace('panadan_knowledge') IS NULL").fetchone()[0], (
            "Use a fresh disposable database; never reset an existing knowledge schema"
        )
        yield conn
    finally:
        # All DDL, roles and fixture rows in this module are transactional.
        conn.rollback()
        conn.close()


def _apply(conn):
    conn.execute("SELECT set_config('panadan.knowledge_migration_target','panadan_ci',true)")
    conn.execute(MIGRATION.read_text())


@pytest.fixture
def migrated(db):
    _apply(db)
    return db


def _reject(conn, error, sql, params=()):
    # The enclosing fixture transaction stays usable after expected errors.
    with pytest.raises(error), conn.transaction():
        if params:
            conn.execute(sql, params)
        else:
            conn.execute(sql)


def _workspace(conn, slug):
    return conn.execute(
        "INSERT INTO panadan_knowledge.workspaces(slug,name) VALUES (%s,'Synthetic workspace') RETURNING id",
        (slug,),
    ).fetchone()[0]


def _principal(conn, subject):
    return conn.execute(
        "INSERT INTO panadan_knowledge.principals(authority_namespace,authority_subject,kind) "
        "VALUES ('synthetic-installation',%s,'human') RETURNING id", (subject,),
    ).fetchone()[0]


def _membership(conn, w, p, member=None):
    return conn.execute(
        "INSERT INTO panadan_knowledge.memberships(workspace_id,id,principal_id,state) "
        "VALUES (%s,%s,%s,'active') RETURNING id", (w, member or uuid4(), p),
    ).fetchone()[0]


def test_migration_requires_explicit_target(db):
    _reject(db, errors.RaiseException, MIGRATION.read_text())
    db.execute("SELECT set_config('panadan.knowledge_migration_target','odoo',true)")
    _reject(db, errors.RaiseException, MIGRATION.read_text())
    assert db.execute("SELECT to_regnamespace('panadan_knowledge') IS NULL").fetchone()[0]


def test_migration_refuses_conflicting_owner(db):
    db.execute("CREATE ROLE panadan_knowledge_owner LOGIN")
    _reject(db, errors.RaiseException,
            "SELECT set_config('panadan.knowledge_migration_target','panadan_ci',true);\n"
            + MIGRATION.read_text())
    assert db.execute("SELECT to_regnamespace('panadan_knowledge') IS NULL").fetchone()[0]


def test_migration_refuses_existing_schema_owned_by_other_role(db):
    db.execute("CREATE SCHEMA panadan_knowledge")
    _reject(db, errors.RaiseException,
            "SELECT set_config('panadan.knowledge_migration_target','panadan_ci',true);\n"
            + MIGRATION.read_text())
    assert db.execute(
        "SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='panadan_knowledge'"
    ).fetchone()[0] == "panadan_ci"


def test_clean_install_replay_preserves_rows_and_defaults(migrated):
    conn = migrated
    w = _workspace(conn, "synthetic-a")
    p = _principal(conn, "account-a")
    _membership(conn, w, p)
    _apply(conn)
    assert {r[0] for r in conn.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname='panadan_knowledge'"
    )} == TABLES
    assert conn.execute(
        "SELECT state,policy_epoch,lock_version FROM panadan_knowledge.workspaces WHERE id=%s", (w,)
    ).fetchone() == ("disabled", 0, 0)
    assert conn.execute("SELECT state FROM panadan_knowledge.principals WHERE id=%s", (p,)).fetchone() == ("disabled",)
    assert conn.execute("SELECT count(*) FROM panadan_knowledge.memberships").fetchone() == (1,)


def test_existing_legacy_schemas_and_rows_preserved(db):
    db.execute((ROOT / "database/migrations/001_multisource_foundation.sql").read_text())
    db.execute((ROOT / "database/migrations/003_auth_foundation.sql").read_text())
    db.execute("INSERT INTO panadan_ingest.sources(source_key,kind,label) VALUES ('m01_fixture','manual','Synthetic')")
    db.execute(
        "INSERT INTO panadan_auth.users(username,password_hash,role,profile_id) VALUES "
        "('m01_fixture','synthetic-not-a-login-hash','reader',%s)",
        ("prf_" + uuid4().hex,),
    )
    before = db.execute(
        "SELECT id,username,role,profile_id FROM panadan_auth.users WHERE username='m01_fixture'"
    ).fetchone()
    _apply(db)
    assert db.execute(
        "SELECT id,username,role,profile_id FROM panadan_auth.users WHERE username='m01_fixture'"
    ).fetchone() == before
    assert db.execute(
        "SELECT kind,label,enabled FROM panadan_ingest.sources WHERE source_key='m01_fixture'"
    ).fetchone() == ("manual", "Synthetic", False)
    for table in TABLES:
        # Internal fixed table names only.
        assert db.execute("SELECT count(*) FROM panadan_knowledge." + table).fetchone() == (0,)


def test_unique_identity_and_membership_constraints(migrated):
    c = migrated
    a, b = _workspace(c, "synthetic-a"), _workspace(c, "synthetic-b")
    p = _principal(c, "account-a")
    m = uuid4()
    _membership(c, a, p, m)
    _membership(c, b, p, m)  # Same local ID in two tenants is valid.
    _reject(c, errors.UniqueViolation,
            "INSERT INTO panadan_knowledge.workspaces(slug,name) VALUES ('synthetic-a','Duplicate')")
    _reject(c, errors.UniqueViolation,
            "INSERT INTO panadan_knowledge.principals(authority_namespace,authority_subject,kind) "
            "VALUES ('synthetic-installation','account-a','human')")
    _reject(c, errors.UniqueViolation,
            "INSERT INTO panadan_knowledge.memberships(workspace_id,principal_id,state) VALUES (%s,%s,'active')", (a,p))
    _reject(c, errors.ForeignKeyViolation,
            "INSERT INTO panadan_knowledge.memberships(workspace_id,principal_id,state) VALUES (%s,%s,'active')", (uuid4(),p))
    _reject(c, errors.ForeignKeyViolation,
            "DELETE FROM panadan_knowledge.workspaces WHERE id=%s", (a,))
    _reject(c, errors.CheckViolation,
            "UPDATE panadan_knowledge.memberships SET state='revoked' WHERE workspace_id=%s AND id=%s", (a,m))
    _reject(c, errors.CheckViolation,
            "UPDATE panadan_knowledge.workspaces SET policy_epoch=-1 WHERE id=%s", (a,))


def test_policy_versions_require_same_tenant_approver(migrated):
    c = migrated
    a,b = _workspace(c,"synthetic-a"),_workspace(c,"synthetic-b")
    member = _membership(c,b,_principal(c,"account-b"))
    insert = ("INSERT INTO panadan_knowledge.policy_versions(workspace_id,kind,policy_key,rev,definition,state,approved_by,approved_at) "
              "VALUES (%s,'access','baseline',1,'{}','approved',%s,now())")
    _reject(c, errors.ForeignKeyViolation, insert, (a,member))
    c.execute(insert,(b,member))
    _reject(c, errors.UniqueViolation, insert,(b,member))
    _reject(c, errors.CheckViolation,
            "INSERT INTO panadan_knowledge.policy_versions(workspace_id,kind,policy_key,rev,definition) VALUES (%s,'access','invalid',0,'{}')",(a,))
    _reject(c, errors.CheckViolation,
            "INSERT INTO panadan_knowledge.policy_versions(workspace_id,kind,policy_key,rev,definition) VALUES (%s,'access','invalid',1,'[]')",(a,))
    _reject(c, errors.CheckViolation,
            "INSERT INTO panadan_knowledge.policy_versions(workspace_id,kind,policy_key,rev,definition,state) VALUES (%s,'access','invalid',1,'{}','approved')",(a,))


def test_audit_actor_consistency_and_metadata_shape(migrated):
    c = migrated
    a,b = _workspace(c,"synthetic-a"),_workspace(c,"synthetic-b")
    p,q = _principal(c,"account-a"),_principal(c,"account-b")
    m = _membership(c,b,p)
    insert = ("INSERT INTO panadan_knowledge.audit_events(workspace_id,principal_id,membership_id,channel,action,target_kind,policy_epoch,outcome,correlation_id) "
              "VALUES (%s,%s,%s,'system','synthetic','workspace',0,'succeeded',%s)")
    _reject(c, errors.ForeignKeyViolation, insert,(a,p,m,uuid4()))
    _reject(c, errors.ForeignKeyViolation, insert,(b,q,m,uuid4()))
    _reject(c, errors.CheckViolation, insert,(b,None,m,uuid4()))
    c.execute(insert,(b,p,m,uuid4()))
    _reject(c, errors.CheckViolation,
            "UPDATE panadan_knowledge.audit_events SET safe_metadata='[]' WHERE workspace_id=%s",(b,))
    _reject(c, errors.CheckViolation,
            "UPDATE panadan_knowledge.audit_events SET safe_metadata=jsonb_build_object('reason',repeat('x',5000)) WHERE workspace_id=%s",(b,))
    _reject(c, errors.ForeignKeyViolation,
            "DELETE FROM panadan_knowledge.memberships WHERE workspace_id=%s AND id=%s",(b,m))


def test_owner_and_deny_by_default_acl(migrated):
    c = migrated
    w = _workspace(c,"synthetic-a")
    p = _principal(c,"account-a")
    _membership(c,w,p)
    assert c.execute(
        "SELECT rolcanlogin,rolinherit,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls "
        "FROM pg_roles WHERE rolname='panadan_knowledge_owner'"
    ).fetchone() == (False,)*7
    assert c.execute(
        "SELECT count(*) FROM pg_tables WHERE schemaname='panadan_knowledge' AND tableowner='panadan_knowledge_owner'"
    ).fetchone() == (5,)
    assert {r[0] for r in c.execute(
        "SELECT relname FROM pg_class WHERE relnamespace='panadan_knowledge'::regnamespace AND relrowsecurity AND relforcerowsecurity"
    )} == {"memberships","policy_versions","audit_events"}
    assert c.execute("SELECT count(*) FROM pg_policies WHERE schemaname='panadan_knowledge'").fetchone() == (0,)
    c.execute("CREATE ROLE panadan_knowledge_test_probe NOLOGIN NOINHERIT")
    assert not c.execute(
        "SELECT has_schema_privilege('panadan_knowledge_test_probe','panadan_knowledge','USAGE')"
    ).fetchone()[0]
    for table in TABLES:
        for privilege in ("SELECT","INSERT","UPDATE","DELETE","TRUNCATE"):
            assert not c.execute("SELECT has_table_privilege('panadan_knowledge_test_probe',%s,%s)",
                                 ("panadan_knowledge."+table,privilege)).fetchone()[0]
    c.execute("SET LOCAL ROLE panadan_knowledge_test_probe")
    _reject(c, errors.InsufficientPrivilege, "SELECT * FROM panadan_knowledge.workspaces")
    c.execute("RESET ROLE")
    c.execute("SET LOCAL ROLE panadan_knowledge_owner")
    assert c.execute("SELECT count(*) FROM panadan_knowledge.memberships").fetchone() == (0,)
    _reject(c, errors.InsufficientPrivilege,
            "INSERT INTO panadan_knowledge.memberships(workspace_id,principal_id,state) VALUES (%s,%s,'active')",
            (w, p))
    c.execute("RESET ROLE")
