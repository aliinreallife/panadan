"""M01.2 synthetic authorization tests. No live auth, routes or runtime grants."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from psycopg import errors
from psycopg.types.json import Jsonb

from server.security import Store
from server.knowledge_identity import SQLiteIdentityBridge, install_profile_identity
from server.knowledge_authorization import AccessDenied, CAPABILITIES, WorkspaceAuthorization

# Reuse the strict disposable DSN and transactional rollback fixture from M01.1.
from test_knowledge_foundation import db, _apply, _reject

MIGRATION = Path(__file__).resolve().parents[1] / "database/migrations/005_knowledge_authorization.sql"


def test_authorization_migration_requires_foundation(db):
    db.execute("SELECT set_config('panadan.knowledge_migration_target','panadan_ci',true)")
    _reject(db, errors.RaiseException, MIGRATION.read_text())
    assert db.execute("SELECT to_regnamespace('panadan_knowledge') IS NULL").fetchone()[0]


@pytest.fixture
def scenario(db, tmp_path):
    _apply(db)
    db.execute(MIGRATION.read_text())
    db.execute(MIGRATION.read_text())  # additive replay
    store = Store(str(tmp_path / "auth.sqlite"))
    store.bootstrap("admin", "synthetic-password-only")
    admin_id = store.verify_login("admin", "synthetic-password-only")
    user_id = store.create_user("reader", "synthetic-password-only", "reader")
    outsider_id = store.create_user("outsider", "synthetic-password-only", "admin")
    ns = uuid4()
    install_profile_identity(store, ns, confirmed=True)
    admin, _ = store.create_session(admin_id)
    user, _ = store.create_session(user_id)
    outsider, _ = store.create_session(outsider_id)
    bridge = SQLiteIdentityBridge(store, ns)
    a, b = [
        db.execute("INSERT INTO panadan_knowledge.workspaces(slug,name,state) VALUES (%s,'Synthetic','active') RETURNING id",
                   (slug,)).fetchone()[0]
        for slug in ("synthetic-a", "synthetic-b")
    ]
    # Explicit synthetic administrative bootstrap. Not a production enrollment path.
    principals = []
    for raw in (admin,user):
        ident = bridge.resolve_session(raw)
        principals.append(db.execute("""INSERT INTO panadan_knowledge.principals
            (authority_namespace,authority_subject,kind,state) VALUES (%s,%s,'human','active') RETURNING id""",
            (ident.namespace,ident.subject)).fetchone()[0])
    owner, reader = principals
    member = db.execute("""INSERT INTO panadan_knowledge.memberships(workspace_id,principal_id,state)
        VALUES (%s,%s,'active') RETURNING id""",(a,owner)).fetchone()[0]
    role = db.execute("""INSERT INTO panadan_knowledge.role_versions
        (workspace_id,role_key,rev,name,capability_set,state)
        VALUES (%s,'bootstrap',1,'Synthetic owner',%s,'active') RETURNING id""",
        (a,Jsonb(sorted(CAPABILITIES)))).fetchone()[0]
    db.execute("""INSERT INTO panadan_knowledge.membership_roles
        (workspace_id,membership_id,role_version_id,granted_by) VALUES (%s,%s,%s,%s)""",
        (a,member,role,member))
    for cap in CAPABILITIES:
        db.execute("""INSERT INTO panadan_knowledge.scope_grants
            (workspace_id,membership_id,capability,grantor) VALUES (%s,%s,%s,%s)""",(a,member,cap,member))
    svc = WorkspaceAuthorization(db,bridge)
    return dict(db=db,store=store,bridge=bridge,svc=svc,a=a,b=b,admin=admin,user=user,outsider=outsider,
                owner=owner,reader=reader,member=member,bootstrap_role=role)


def _reader(s, *, grant=True, caps=None):
    svc,a,admin = s["svc"],s["a"],s["admin"]
    m=svc.add_member(admin,a,s["reader"])
    role=svc.create_role(admin,a,"reader","Reader",caps if caps is not None else ["workspace.read"])
    assignment=svc.assign_role(admin,a,m,role)
    scope=svc.grant_scope(admin,a,m,"workspace.read") if grant else None
    return m,role,assignment,scope


def test_no_legacy_role_or_membership_implies_grant(scenario):
    s=scenario
    svc,a,b=s["svc"],s["a"],s["b"]
    assert svc.authorize(s["admin"],a,"workspace.read").capabilities == CAPABILITIES
    for raw,w in [(s["admin"],b),(s["user"],a),(s["outsider"],a),("forged",a),(s["admin"],uuid4())]:
        with pytest.raises(AccessDenied,match="Access denied"):
            svc.authorize(raw,w,"workspace.read")
    svc.add_member(s["admin"],a,s["reader"])
    with pytest.raises(AccessDenied):
        svc.authorize(s["user"],a,"workspace.read")


def test_role_and_scope_are_both_required_and_external_denied(scenario):
    s=scenario
    svc,a,admin,user=s["svc"],s["a"],s["admin"],s["user"]
    m,_,_,_= _reader(s,grant=False)
    with pytest.raises(AccessDenied):
        svc.authorize(user,a,"workspace.read")
    g=svc.grant_scope(admin,a,m,"workspace.read")
    assert svc.authorize(user,a,"workspace.read").capabilities == {"workspace.read"}
    for cap,kw in [
        ("members.manage",{}),("knowledge.read",{}),("resource.read",{}),
        ("workspace.read",{"channel":"mcp"}),("workspace.read",{"channel":"api"}),
        ("workspace.read",{"purpose":"external_disclosure"}),
        ("workspace.read",{"data_class":"filtered_sensitive"}),
    ]:
        with pytest.raises(AccessDenied):
            svc.authorize(user,a,cap,**kw)
    svc.revoke_scope(admin,a,g)
    with pytest.raises(AccessDenied):
        svc.authorize(user,a,"workspace.read")


def test_role_versions_pinned_and_immutable(scenario):
    s=scenario
    svc,a,admin,user,c=s["svc"],s["a"],s["admin"],s["user"],s["db"]
    m,r,assignment,_=_reader(s)
    new=svc.create_role(admin,a,"reader","New version",["workspace.read","roles.manage"])
    assert new != r
    assert c.execute("SELECT rev FROM panadan_knowledge.role_versions WHERE workspace_id=%s AND id=%s",(a,new)).fetchone()==(2,)
    assert svc.authorize(user,a,"workspace.read").capabilities=={"workspace.read"}
    _reject(c,errors.RaiseException,"UPDATE panadan_knowledge.role_versions SET capability_set='[]' WHERE workspace_id=%s AND id=%s",(a,r))
    _reject(c,errors.RaiseException,"DELETE FROM panadan_knowledge.role_versions WHERE workspace_id=%s AND id=%s",(a,new))
    svc.retire_role(admin,a,r)
    with pytest.raises(AccessDenied):
        svc.authorize(user,a,"workspace.read")
    _reject(c,errors.RaiseException,"UPDATE panadan_knowledge.role_versions SET state='active' WHERE workspace_id=%s AND id=%s",(a,r))


def test_delegation_cannot_exceed_actor_permissions_or_expiry(scenario):
    s=scenario
    c,svc,a,admin,user=s["db"],s["svc"],s["a"],s["admin"],s["user"]
    m,_,_,_=_reader(s,caps=["workspace.read","roles.manage"])
    svc.grant_scope(admin,a,m,"roles.manage")
    # Member has role administration but cannot grant an unheld permission.
    with pytest.raises(AccessDenied):
        svc.create_role(user,a,"escalate","Escalate",["members.manage"])
    with pytest.raises(AccessDenied):
        svc.grant_scope(user,a,s["member"],"members.manage")
    with pytest.raises(AccessDenied):
        svc.grant_scope(user,a,m,"roles.manage")  # no self grant
    with pytest.raises(AccessDenied):
        svc.assign_role(user,a,s["member"],s["bootstrap_role"])
    ident=s["bridge"].resolve_session(s["outsider"])
    third=c.execute("""INSERT INTO panadan_knowledge.principals
        (authority_namespace,authority_subject,kind,state) VALUES (%s,%s,'human','active') RETURNING id""",
        (ident.namespace,ident.subject)).fetchone()[0]
    target=svc.add_member(admin,a,third)
    expiry=datetime.now(timezone.utc)+timedelta(minutes=5)
    c.execute("UPDATE panadan_knowledge.scope_grants SET valid_until=%s WHERE workspace_id=%s AND membership_id=%s AND capability='roles.manage'",(expiry,a,m))
    with pytest.raises(AccessDenied):
        svc.grant_scope(user,a,target,"workspace.read")
    with pytest.raises(AccessDenied):
        svc.grant_scope(user,a,target,"workspace.read",valid_until=expiry+timedelta(minutes=5))
    assert svc.grant_scope(user,a,target,"workspace.read",valid_until=expiry-timedelta(minutes=1))
    with pytest.raises(AccessDenied):
        svc.authorize(s["outsider"],a,"workspace.read")  # Scope alone does not grant access.


def test_cross_workspace_references_and_default_deny(scenario):
    s=scenario
    c,svc,a,b,admin=s["db"],s["svc"],s["a"],s["b"],s["admin"]
    m,r,_,_=_reader(s)
    foreign=c.execute("""INSERT INTO panadan_knowledge.memberships(workspace_id,principal_id,state)
        VALUES (%s,%s,'active') RETURNING id""",(b,s["reader"])).fetchone()[0]
    with pytest.raises(AccessDenied):
        svc.assign_role(admin,a,foreign,r)
    _reject(c,errors.ForeignKeyViolation,"""INSERT INTO panadan_knowledge.membership_roles
        (workspace_id,membership_id,role_version_id,granted_by) VALUES (%s,%s,%s,%s)""",(a,foreign,r,s["member"]))
    assert c.execute("""SELECT count(*) FROM pg_class WHERE relnamespace='panadan_knowledge'::regnamespace
        AND relname IN ('role_versions','membership_roles','scope_grants') AND relrowsecurity AND relforcerowsecurity""").fetchone()==(3,)
    c.execute("SET LOCAL ROLE panadan_knowledge_owner")
    assert c.execute("SELECT count(*) FROM panadan_knowledge.role_versions").fetchone()==(0,)
    c.execute("RESET ROLE")


def test_revocation_updates_epoch_and_audit_atomically(scenario):
    s=scenario
    svc,a,admin,user,c=s["svc"],s["a"],s["admin"],s["user"],s["db"]
    m,r,assignment,g=_reader(s)
    before=svc.authorize(user,a,"workspace.read").policy_epoch
    svc.revoke_role(admin,a,assignment)
    with pytest.raises(AccessDenied):
        svc.authorize(user,a,"workspace.read")
    svc.assign_role(admin,a,m,r)
    assert svc.authorize(user,a,"workspace.read").policy_epoch==before+2
    svc.revoke_membership(admin,a,m)
    with pytest.raises(AccessDenied):
        svc.authorize(user,a,"workspace.read")
    with pytest.raises(AccessDenied):
        svc.add_member(admin,a,s["reader"])
    assert c.execute("SELECT state FROM panadan_knowledge.memberships WHERE workspace_id=%s AND id=%s",(a,m)).fetchone()==("revoked",)
    assert c.execute("SELECT count(*) FROM panadan_knowledge.scope_grants WHERE workspace_id=%s AND membership_id=%s AND revoked_at IS NULL",(a,m)).fetchone()==(0,)
    assert c.execute("SELECT policy_epoch,action,target_ref FROM panadan_knowledge.audit_events WHERE workspace_id=%s ORDER BY policy_epoch DESC LIMIT 1",(a,)).fetchone()==(before+3,"membership.revoke",str(m))


def test_malformed_role_and_suspended_workspace_fail_closed(scenario):
    s=scenario
    c,svc,a,admin,user=s["db"],s["svc"],s["a"],s["admin"],s["user"]
    m,_,_,_=_reader(s)
    bad=c.execute("""INSERT INTO panadan_knowledge.role_versions
        (workspace_id,role_key,rev,name,capability_set,state)
        VALUES (%s,'bad',1,'Bad','["workspace.read","unknown"]','active') RETURNING id""",(a,)).fetchone()[0]
    c.execute("""INSERT INTO panadan_knowledge.membership_roles
        (workspace_id,membership_id,role_version_id,granted_by) VALUES (%s,%s,%s,%s)""",(a,m,bad,s["member"]))
    with pytest.raises(AccessDenied):
        svc.authorize(user,a,"workspace.read")
    c.execute("UPDATE panadan_knowledge.workspaces SET state='suspended' WHERE id=%s",(a,))
    with pytest.raises(AccessDenied):
        svc.authorize(admin,a,"workspace.read")


def test_expired_role_and_future_grant_deny(scenario):
    s=scenario
    c,svc,a,admin,user=s["db"],s["svc"],s["a"],s["admin"],s["user"]
    m,_,assignment,g=_reader(s)
    c.execute("""UPDATE panadan_knowledge.membership_roles
        SET created_at=now()-interval '2 hours',valid_until=now()-interval '1 hour'
        WHERE workspace_id=%s AND id=%s""",(a,assignment))
    with pytest.raises(AccessDenied):
        svc.authorize(user,a,"workspace.read")
    c.execute("UPDATE panadan_knowledge.membership_roles SET valid_until=NULL WHERE workspace_id=%s AND id=%s",(a,assignment))
    c.execute("UPDATE panadan_knowledge.scope_grants SET valid_from=now()+interval '1 hour' WHERE workspace_id=%s AND id=%s",(a,g))
    with pytest.raises(AccessDenied):
        svc.authorize(user,a,"workspace.read")


def test_session_revocation_rechecked_and_rollback(scenario,monkeypatch):
    s=scenario
    c,svc,a,admin=s["db"],s["svc"],s["a"],s["admin"]
    original=s["bridge"].resolve_session
    count=0
    def revoked_between_checks(raw):
        nonlocal count
        count+=1
        if count==2:
            s["store"].logout(raw)
        return original(raw)
    monkeypatch.setattr(s["bridge"],"resolve_session",revoked_between_checks)
    with pytest.raises(AccessDenied):
        svc.create_role(admin,a,"should_rollback","Rollback",["workspace.read"])
    assert c.execute("SELECT count(*) FROM panadan_knowledge.role_versions WHERE workspace_id=%s AND role_key='should_rollback'",(a,)).fetchone()==(0,)
    assert c.execute("SELECT policy_epoch FROM panadan_knowledge.workspaces WHERE id=%s",(a,)).fetchone()==(0,)
    assert c.execute("SELECT count(*) FROM panadan_knowledge.audit_events WHERE workspace_id=%s",(a,)).fetchone()==(0,)
    with pytest.raises(AccessDenied):
        svc.authorize(admin,a,"workspace.read")


def test_disabled_principal_membership_can_be_revoked(scenario):
    s=scenario
    c,svc,a,admin,user=s["db"],s["svc"],s["a"],s["admin"],s["user"]
    m,_,_,_=_reader(s)
    c.execute("UPDATE panadan_knowledge.principals SET state='disabled' WHERE id=%s",(s["reader"],))
    with pytest.raises(AccessDenied):
        svc.authorize(user,a,"workspace.read")
    svc.revoke_membership(admin,a,m)
    c.execute("UPDATE panadan_knowledge.principals SET state='active' WHERE id=%s",(s["reader"],))
    with pytest.raises(AccessDenied):
        svc.authorize(user,a,"workspace.read")


def test_audit_failure_rolls_back_role_and_epoch(scenario):
    s=scenario
    c,svc,a,admin=s["db"],s["svc"],s["a"],s["admin"]
    c.execute("""CREATE FUNCTION panadan_knowledge.synthetic_audit_failure() RETURNS trigger
        LANGUAGE plpgsql AS $audit_failure$
        BEGIN
            RAISE EXCEPTION 'Synthetic audit failure';
        END;
        $audit_failure$""")
    c.execute("""CREATE TRIGGER synthetic_audit_failure BEFORE INSERT ON panadan_knowledge.audit_events
        FOR EACH ROW EXECUTE FUNCTION panadan_knowledge.synthetic_audit_failure()""")
    with pytest.raises(errors.RaiseException,match="Synthetic audit failure"):
        svc.create_role(admin,a,"audit_rollback","Rollback",["workspace.read"])
    assert c.execute("SELECT count(*) FROM panadan_knowledge.role_versions WHERE workspace_id=%s AND role_key='audit_rollback'",(a,)).fetchone()==(0,)
    assert c.execute("SELECT policy_epoch FROM panadan_knowledge.workspaces WHERE id=%s",(a,)).fetchone()==(0,)
