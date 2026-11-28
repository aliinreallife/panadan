"""M01.3: real PostgreSQL RLS, scope reset and concurrency probes.

All connections target the existing strict disposable PG18 fixture. The
committed fixture is necessary for multi-connection tests. Only the new
schema and four roles created by this fixture are removed on teardown.
No production roles, source connections or external data are used.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import monotonic, sleep
from uuid import uuid4
import os

import psycopg
from psycopg import errors
from psycopg.types.json import Jsonb
import pytest

from server.security import Store
from server.knowledge_identity import SQLiteIdentityBridge, install_profile_identity
from server.knowledge_authorization import AccessDenied, CAPABILITIES, WorkspaceAuthorization
from server.knowledge_scope import ScopedWorkspace, _SETTINGS
from test_knowledge_foundation import db, _apply, _reject, _validate_dsn

ROOT = Path(__file__).resolve().parents[1]
M005 = ROOT / "database/migrations/005_knowledge_authorization.sql"
M006 = ROOT / "database/migrations/006_knowledge_rls.sql"
ROLE_NAMES = (
    "panadan_knowledge_owner", "panadan_knowledge_authorizer",
    "panadan_knowledge_reader", "panadan_knowledge_test_login",
)


def test_rls_requires_prior_migrations_and_target(db):
    db.execute("SELECT set_config('panadan.knowledge_migration_target','panadan_ci',true)")
    _reject(db, errors.RaiseException, M006.read_text())
    _apply(db)
    _reject(db, errors.RaiseException, M006.read_text())
    db.execute(M005.read_text())
    db.execute("SELECT set_config('panadan.knowledge_migration_target','wrong',true)")
    _reject(db, errors.RaiseException, M006.read_text())
    db.execute("SELECT set_config('panadan.knowledge_migration_target','panadan_ci',true)")
    db.execute("CREATE ROLE panadan_knowledge_reader LOGIN")
    _reject(db, errors.RaiseException, M006.read_text())


@pytest.fixture
def runtime(db, tmp_path):
    # Refuse preexisting role names as well as the existing fixture's schema
    # guard. Only commit and later drop our own synthetic objects.
    assert db.execute("SELECT count(*) FROM pg_roles WHERE rolname=ANY(%s::text[])",
                      (list(ROLE_NAMES),)).fetchone()==(0,)
    _apply(db)
    db.execute(M005.read_text())
    db.execute(M006.read_text())
    db.execute(M006.read_text())  # idempotence before runtime login provisioning
    # Actual restricted TCP login, with public synthetic-only credentials.
    db.execute("CREATE ROLE panadan_knowledge_test_login LOGIN NOINHERIT PASSWORD 'synthetic_knowledge_test_only'")
    db.execute("GRANT CONNECT ON DATABASE panadan_ci TO panadan_knowledge_test_login")
    db.execute("GRANT panadan_knowledge_authorizer,panadan_knowledge_reader TO panadan_knowledge_test_login WITH INHERIT FALSE, SET TRUE")
    store = Store(str(tmp_path / "auth.sqlite"))
    store.bootstrap("admin","synthetic-password-only")
    uid_admin = store.verify_login("admin","synthetic-password-only")
    uid_reader = store.create_user("reader","synthetic-password-only","reader")
    uid_other = store.create_user("other","synthetic-password-only","reader")
    uid_new = store.create_user("newmember","synthetic-password-only","reader")
    ns = uuid4()
    install_profile_identity(store,ns,confirmed=True)
    bridge=SQLiteIdentityBridge(store,ns)
    admin,user,other,new= [store.create_session(uid)[0] for uid in (uid_admin,uid_reader,uid_other,uid_new)]
    def principal(raw):
        ident=bridge.resolve_session(raw)
        return db.execute("""INSERT INTO panadan_knowledge.principals
            (authority_namespace,authority_subject,kind,state) VALUES (%s,%s,'human','active') RETURNING id""",
            (ident.namespace,ident.subject)).fetchone()[0]
    p,q,r,n = [principal(raw) for raw in (admin,user,other,new)]
    a,b = [db.execute("""INSERT INTO panadan_knowledge.workspaces(slug,name,state)
            VALUES (%s,%s,'active') RETURNING id""",(slug,slug)).fetchone()[0] for slug in ("synthetic-a","synthetic-b")]
    overlap=uuid4()
    def seed(w,principal_id,member,capabilities):
        db.execute("""INSERT INTO panadan_knowledge.memberships(workspace_id,id,principal_id,state)
            VALUES (%s,%s,%s,'active')""",(w,member,principal_id))
        role=db.execute("""INSERT INTO panadan_knowledge.role_versions
            (workspace_id,role_key,rev,name,capability_set,state)
            VALUES (%s,'initial',1,'Synthetic',%s,'active') RETURNING id""",(w,Jsonb(sorted(capabilities)))).fetchone()[0]
        db.execute("""INSERT INTO panadan_knowledge.membership_roles
            (workspace_id,membership_id,role_version_id,granted_by)
            VALUES (%s,%s,%s,%s)""",(w,member,role,member))
        for cap in capabilities:
            db.execute("""INSERT INTO panadan_knowledge.scope_grants
                (workspace_id,membership_id,capability,grantor) VALUES (%s,%s,%s,%s)""",(w,member,cap,member))
    owner=uuid4()
    seed(a,p,owner,CAPABILITIES)
    seed(a,q,overlap,{"workspace.read"})
    seed(b,r,overlap,{"workspace.read"})
    db.commit()
    connections=[]
    def connect():
        cfg=_validate_dsn(os.environ["PANADAN_PLATFORM_TEST_DSN"],os.environ.get("PANADAN_PLATFORM_TEST_ALLOW_RESET"))
        cfg.update(user="panadan_knowledge_test_login",password="synthetic_knowledge_test_only")
        c=psycopg.connect(**cfg,autocommit=True,connect_timeout=5)
        connections.append(c)
        assert c.execute("SELECT current_user,session_user").fetchone()==("panadan_knowledge_test_login",)*2
        return c
    try:
        yield dict(db=db,connect=connect,bridge=bridge,store=store,a=a,b=b,
                   admin=admin,user=user,other=other,new=new,p=p,q=q,r=r,n=n,
                   overlap=overlap,owner=owner)
    finally:
        for c in connections:
            c.close()
        db.rollback()
        with db.transaction():
            db.execute("DROP SCHEMA panadan_knowledge CASCADE")
            db.execute("REVOKE CONNECT ON DATABASE panadan_ci FROM panadan_knowledge_test_login")
            db.execute("DROP ROLE panadan_knowledge_test_login")
            db.execute("DROP ROLE panadan_knowledge_authorizer,panadan_knowledge_reader,panadan_knowledge_owner")


def _scope(c,s,workspace,raw):
    identity=s["bridge"].resolve_session(raw)
    c.execute("SET LOCAL ROLE panadan_knowledge_authorizer")
    for key,value in zip(_SETTINGS,(str(workspace),identity.namespace,identity.subject,"","",""),strict=True):
        c.execute("SELECT set_config(%s,%s,true)",(key,value))


def _assert_clean(c):
    assert c.execute("SELECT current_user=session_user").fetchone()==(True,)
    for key in _SETTINGS:
        assert c.execute("SELECT current_setting(%s,true)",(key,)).fetchone()[0] in (None,"")


def test_runtime_roles_and_missing_or_invalid_scope(runtime):
    s=runtime
    c=s["connect"]()
    assert c.execute("""SELECT count(*) FROM pg_roles WHERE rolname IN
        ('panadan_knowledge_authorizer','panadan_knowledge_reader')
        AND NOT (rolcanlogin OR rolinherit OR rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)""").fetchone()==(2,)
    assert c.execute("SELECT has_schema_privilege(current_user,'panadan_knowledge','USAGE')").fetchone()==(False,)
    with c.transaction():
        _reject(c,errors.InsufficientPrivilege,"SET ROLE panadan_knowledge_owner")
        _reject(c,errors.InsufficientPrivilege,"SET SESSION AUTHORIZATION panadan_ci")
    with c.transaction():
        c.execute("SET LOCAL ROLE panadan_knowledge_authorizer")
        for table in ("memberships","role_versions","membership_roles","scope_grants"):
            assert c.execute("SELECT count(*) FROM panadan_knowledge."+table).fetchone()==(0,)
        assert c.execute("SELECT count(id) FROM panadan_knowledge.workspaces").fetchone()==(0,)
        assert c.execute("SELECT count(id) FROM panadan_knowledge.principals").fetchone()==(0,)
        c.execute("SELECT set_config('panadan.workspace_id','not-a-uuid',true)")
        c.execute("SELECT set_config('panadan.authority_namespace','synthetic',true)")
        c.execute("SELECT set_config('panadan.authority_subject','synthetic',true)")
        assert c.execute("SELECT count(*) FROM panadan_knowledge.memberships").fetchone()==(0,)
        assert c.execute("SELECT has_schema_privilege(current_user,'panadan_knowledge','CREATE')").fetchone()==(False,)
        assert c.execute("SELECT has_table_privilege(current_user,'panadan_knowledge.audit_events','SELECT')").fetchone()==(False,)
        assert c.execute("SELECT has_table_privilege(current_user,'panadan_knowledge.memberships','DELETE')").fetchone()==(False,)
        _reject(c,errors.InsufficientPrivilege,"TRUNCATE panadan_knowledge.memberships")
        _reject(c,errors.InsufficientPrivilege,"SELECT * FROM panadan_knowledge.policy_versions")
        _reject(c,errors.InsufficientPrivilege,"SELECT * FROM panadan_knowledge.audit_events")
    _assert_clean(c)


def test_unfiltered_queries_and_overlapping_ids_are_tenant_scoped(runtime):
    s=runtime
    c=s["connect"]()
    with c.transaction():
        _scope(c,s,s["a"],s["admin"])
        for table in ("memberships","role_versions","membership_roles","scope_grants"):
            assert c.execute("SELECT DISTINCT workspace_id FROM panadan_knowledge."+table).fetchall()==[(s["a"],)]
        assert c.execute("SELECT workspace_id,principal_id FROM panadan_knowledge.memberships WHERE id=%s",
                         (s["overlap"],)).fetchall()==[(s["a"],s["q"])]
        assert set(c.execute("SELECT id FROM panadan_knowledge.principals").fetchall())=={(s["p"],),(s["q"],)}
        assert c.execute("SELECT id FROM panadan_knowledge.workspaces").fetchall()==[(s["a"],)]
        assert c.execute("UPDATE panadan_knowledge.memberships SET state='revoked',revoked_at=clock_timestamp() WHERE workspace_id=%s",
                         (s["b"],)).rowcount==0
        _reject(c,errors.InsufficientPrivilege,"""INSERT INTO panadan_knowledge.memberships
            (workspace_id,principal_id,state) VALUES (%s,%s,'active')""",(s["b"],s["n"]))
        _reject(c,errors.InsufficientPrivilege,"UPDATE panadan_knowledge.principals SET state='disabled'")
    _assert_clean(c)
    with c.transaction():
        _scope(c,s,s["b"],s["other"])
        assert c.execute("SELECT workspace_id,principal_id FROM panadan_knowledge.memberships WHERE id=%s",
                         (s["overlap"],)).fetchall()==[(s["b"],s["r"])]
    _assert_clean(c)


def test_fixed_service_operations_use_nonsuperuser_and_reset_scope(runtime):
    s=runtime
    c=s["connect"]()
    with pytest.raises(AccessDenied):
        ScopedWorkspace(c,s["bridge"])
    svc=ScopedWorkspace(c,s["bridge"],enabled=True)
    assert svc.read_workspace(s["user"],s["a"])["slug"]=="synthetic-a"
    _assert_clean(c)
    with pytest.raises(AccessDenied,match="Access denied"):
        svc.read_workspace(s["user"],s["b"])
    _assert_clean(c)
    assert svc.read_workspace(s["other"],s["b"])["id"]==s["b"]
    with pytest.raises(AccessDenied):
        svc.command(s["user"],s["a"],"create_role","nope","Nope",["workspace.read"])
    with pytest.raises(AccessDenied):
        svc.command(s["admin"],s["a"],"_change")
    member=svc.command(s["admin"],s["a"],"add_member",s["n"])
    role=svc.command(s["admin"],s["a"],"create_role","reader","Reader",["workspace.read"])
    svc.command(s["admin"],s["a"],"assign_role",member,role)
    grant=svc.command(s["admin"],s["a"],"grant_scope",member,"workspace.read")
    assert svc.read_workspace(s["new"],s["a"])["id"]==s["a"]
    svc.command(s["admin"],s["a"],"revoke_scope",grant)
    with pytest.raises(AccessDenied):
        svc.read_workspace(s["new"],s["a"])
    _assert_clean(c)
    assert svc.read_workspace(s["other"],s["b"])["id"]==s["b"]
    db=s["db"]
    assert db.execute("SELECT count(*) FROM panadan_knowledge.audit_events WHERE workspace_id=%s",(s["a"],)).fetchone()==(5,)
    assert db.execute("SELECT count(*) FROM panadan_knowledge.audit_events WHERE workspace_id=%s",(s["b"],)).fetchone()==(0,)
    db.rollback()


def test_projection_role_requires_authorized_epoch_and_cannot_write(runtime):
    s=runtime
    c=s["connect"]()
    with c.transaction():
        _scope(c,s,s["a"],s["admin"])
        c.execute("SET LOCAL ROLE panadan_knowledge_reader")
        assert c.execute("SELECT id FROM panadan_knowledge.workspaces").fetchall()==[]
        c.execute("SELECT set_config('panadan.read_authorized','yes',true)")
        c.execute("SELECT set_config('panadan.policy_epoch','999',true)")
        assert c.execute("SELECT id FROM panadan_knowledge.workspaces").fetchall()==[]
        c.execute("SELECT set_config('panadan.policy_epoch','0',true)")
        assert c.execute("SELECT id FROM panadan_knowledge.workspaces").fetchall()==[(s["a"],)]
        _reject(c,errors.InsufficientPrivilege,"UPDATE panadan_knowledge.workspaces SET name='bad'")
        _reject(c,errors.InsufficientPrivilege,"SELECT * FROM panadan_knowledge.memberships")
        _reject(c,errors.InsufficientPrivilege,"SELECT * FROM panadan_knowledge.principals")
    _assert_clean(c)


def test_dirty_connection_rejected_and_closed(runtime):
    s=runtime
    c=s["connect"]()
    c.execute("SELECT set_config('panadan.workspace_id',%s,false)",(str(s["a"]),))
    with pytest.raises(AccessDenied):
        ScopedWorkspace(c,s["bridge"],enabled=True).read_workspace(s["user"],s["a"])
    assert c.closed
    c=s["connect"]()
    with c.transaction():
        with pytest.raises(AccessDenied):
            ScopedWorkspace(c,s["bridge"],enabled=True).read_workspace(s["user"],s["a"])
    _assert_clean(c)


def test_runtime_audit_failure_rolls_back_and_connection_reusable(runtime):
    s=runtime
    db=s["db"]
    with db.transaction():
        db.execute("""CREATE FUNCTION panadan_knowledge.synthetic_audit_failure() RETURNS trigger
            LANGUAGE plpgsql AS $audit_failure$
            BEGIN RAISE EXCEPTION 'Synthetic audit failure'; END;
            $audit_failure$""")
        db.execute("""CREATE TRIGGER synthetic_audit_failure BEFORE INSERT ON panadan_knowledge.audit_events
            FOR EACH ROW EXECUTE FUNCTION panadan_knowledge.synthetic_audit_failure()""")
    c=s["connect"]()
    svc=ScopedWorkspace(c,s["bridge"],enabled=True)
    with pytest.raises(errors.RaiseException,match="Synthetic audit failure"):
        svc.command(s["admin"],s["a"],"create_role","rollback","Rollback",["workspace.read"])
    _assert_clean(c)
    assert svc.read_workspace(s["other"],s["b"])["id"]==s["b"]
    assert db.execute("SELECT policy_epoch FROM panadan_knowledge.workspaces WHERE id=%s",(s["a"],)).fetchone()==(0,)
    assert db.execute("SELECT count(*) FROM panadan_knowledge.role_versions WHERE workspace_id=%s AND role_key='rollback'",(s["a"],)).fetchone()==(0,)
    db.rollback()


def _wait_blocked(observer, blocked_pid, blocker_pid):
    end=monotonic()+3
    while monotonic()<end:
        if blocker_pid in observer.execute("SELECT pg_blocking_pids(%s)",(blocked_pid,)).fetchone()[0]:
            return
        sleep(0.02)
    pytest.fail("Expected workspace lock contention was not observed")


def test_concurrent_revocation_waiter_rechecks_current_grants(runtime):
    s=runtime
    writer=s["connect"]()
    reader=s["connect"]()
    observer=s["db"]
    with ThreadPoolExecutor(max_workers=1) as pool:
        with writer.transaction():
            _scope(writer,s,s["a"],s["admin"])
            # Actual service command, held uncommitted until waiter blocks.
            WorkspaceAuthorization(writer,s["bridge"]).revoke_membership(s["admin"],s["a"],s["overlap"])
            pending=pool.submit(ScopedWorkspace(reader,s["bridge"],enabled=True).read_workspace,s["user"],s["a"])
            _wait_blocked(observer,reader.info.backend_pid,writer.info.backend_pid)
        with pytest.raises(AccessDenied):
            pending.result(timeout=8)
    observer.rollback()
    _assert_clean(writer)
    _assert_clean(reader)
    assert ScopedWorkspace(reader,s["bridge"],enabled=True).read_workspace(s["other"],s["b"])["id"]==s["b"]


def test_concurrent_role_publication_serializes_revision_numbers(runtime):
    s=runtime
    writer=s["connect"]()
    waiter=s["connect"]()
    observer=s["db"]
    with ThreadPoolExecutor(max_workers=1) as pool:
        with writer.transaction():
            _scope(writer,s,s["a"],s["admin"])
            first=WorkspaceAuthorization(writer,s["bridge"]).create_role(s["admin"],s["a"],"race","Race",["workspace.read"])
            pending=pool.submit(ScopedWorkspace(waiter,s["bridge"],enabled=True).command,
                                s["admin"],s["a"],"create_role","race","Race",["workspace.read"])
            _wait_blocked(observer,waiter.info.backend_pid,writer.info.backend_pid)
        second=pending.result(timeout=8)
    observer.rollback()
    assert first!=second
    assert observer.execute("SELECT rev FROM panadan_knowledge.role_versions WHERE workspace_id=%s AND role_key='race' ORDER BY rev",(s["a"],)).fetchall()==[(1,),(2,)]
    observer.rollback()
    _assert_clean(writer)
    _assert_clean(waiter)


def test_session_revoked_after_projection_never_returns_data(runtime,monkeypatch):
    s=runtime
    c=s["connect"]()
    svc=ScopedWorkspace(c,s["bridge"],enabled=True)
    original=s["bridge"].resolve_session
    calls=0
    def resolve(raw):
        nonlocal calls
        calls+=1
        # Last external identity check after both authorization checks.
        if calls==6:
            s["store"].logout(raw)
        return original(raw)
    monkeypatch.setattr(s["bridge"],"resolve_session",resolve)
    with pytest.raises(AccessDenied):
        svc.read_workspace(s["user"],s["a"])
    _assert_clean(c)
    assert svc.read_workspace(s["other"],s["b"])["id"]==s["b"]


def test_legacy_schemas_remain_inaccessible_to_new_roles(db):
    db.execute((ROOT/"database/migrations/001_multisource_foundation.sql").read_text())
    db.execute((ROOT/"database/migrations/003_auth_foundation.sql").read_text())
    _apply(db)
    db.execute(M005.read_text())
    db.execute(M006.read_text())
    # Resolve relation OIDs as the fixture administrator so the privilege
    # checks do not themselves need USAGE on the legacy schemas.
    oids=[db.execute("SELECT %s::regclass::oid",(table,)).fetchone()[0]
          for table in ("panadan_ingest.sources","panadan_auth.users")]
    for role in ("panadan_knowledge_authorizer","panadan_knowledge_reader"):
        # Fixed internal role names, never request input.
        db.execute("SET LOCAL ROLE "+role)
        for oid in oids:
            assert db.execute("SELECT has_table_privilege(current_user,%s::oid,'SELECT')",(oid,)).fetchone()==(False,)
            assert db.execute("SELECT has_table_privilege(current_user,%s::oid,'INSERT')",(oid,)).fetchone()==(False,)
        db.execute("RESET ROLE")


def test_privileged_or_misconfigured_connection_is_rejected(runtime):
    s=runtime
    with psycopg.connect(os.environ["PANADAN_PLATFORM_TEST_DSN"],autocommit=True,connect_timeout=5) as admin:
        with pytest.raises(AccessDenied):
            ScopedWorkspace(admin,s["bridge"],enabled=True).read_workspace(s["admin"],s["a"])
        assert admin.closed
    db=s["db"]
    with db.transaction():
        db.execute("GRANT USAGE ON SCHEMA panadan_knowledge TO panadan_knowledge_test_login")
    c=s["connect"]()
    with pytest.raises(AccessDenied):
        ScopedWorkspace(c,s["bridge"],enabled=True).read_workspace(s["admin"],s["a"])
    assert c.closed
