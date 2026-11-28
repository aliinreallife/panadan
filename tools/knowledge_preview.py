"""Synthetic-only bootstrap for tools/preview-knowledge.sh.

Uses a newly created disposable PG18 database and fresh temporary SQLite
store. No reporting/source connection, real account migration or deployment.
"""
from pathlib import Path
import os
import sys
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb
from server.security import Store
from server.knowledge_identity import SQLiteIdentityBridge, install_profile_identity
from server.knowledge_authorization import CAPABILITIES
from tools.knowledge_preview_resources import collect_preview_resources, seed_preview_resource_scope

PASSWORD = "synthetic-preview-password"
ROOT = Path(__file__).resolve().parents[1]


def main():
    if os.environ.get("PANADAN_KNOWLEDGE_PREVIEW_BOOTSTRAP") != "YES" or len(sys.argv)!=3:
        raise SystemExit("Use bash tools/preview-knowledge.sh")
    if any(k.startswith("PG") for k in os.environ):
        raise SystemExit("Unexpected inherited database environment")
    port=int(sys.argv[1])
    if not 1<=port<=65535:
        raise SystemExit("Invalid disposable port")
    directory=Path(sys.argv[2]).resolve()
    path=directory/"auth.sqlite"
    if not directory.is_dir() or path.exists():
        raise SystemExit("A fresh temporary authentication store is required")

    with psycopg.connect(host="127.0.0.1",port=port,dbname="panadan_ci",user="panadan_ci",
                         password="synthetic_ci_password_only",connect_timeout=5,sslmode="disable") as db:
        if db.execute("""SELECT current_database(),session_user,current_setting('server_version_num')::int/10000,
                to_regnamespace('panadan_knowledge') IS NULL""").fetchone()!=("panadan_ci","panadan_ci",18,True):
            raise SystemExit("Refusing non-disposable or initialized database")
        if db.execute("""SELECT count(*) FROM pg_roles WHERE rolname IN
            ('panadan_knowledge_owner','panadan_knowledge_authorizer','panadan_knowledge_reader',
             'panadan_knowledge_test_login','panadan_knowledge_collector','panadan_knowledge_collector_ci',
             'panadan_call_source_reader_ci')""").fetchone()!=(0,):
            raise SystemExit("Refusing existing role names")
        db.execute("SELECT set_config('panadan.knowledge_migration_target','panadan_ci',true)")
        for migration in ("004_knowledge_foundation.sql","005_knowledge_authorization.sql","006_knowledge_rls.sql",
                          "007_knowledge_call_resources.sql","008_knowledge_call_collection.sql","009_knowledge_resource_explorer.sql"):
            db.execute((ROOT/"database/migrations"/migration).read_text(encoding="utf-8"))
        db.execute("CREATE ROLE panadan_knowledge_test_login LOGIN NOINHERIT PASSWORD 'synthetic_knowledge_test_only'")
        db.execute("GRANT CONNECT ON DATABASE panadan_ci TO panadan_knowledge_test_login")
        db.execute("GRANT panadan_knowledge_authorizer,panadan_knowledge_reader TO panadan_knowledge_test_login WITH INHERIT FALSE, SET TRUE")
        store=Store(str(path))
        store.bootstrap("admin",PASSWORD)
        admin=store.verify_login("admin",PASSWORD)
        reader=store.create_user("reader",PASSWORD,"reader")
        other=store.create_user("other",PASSWORD,"reader")
        new=store.create_user("newmember",PASSWORD,"reader")
        installation=uuid4()
        install_profile_identity(store,installation,confirmed=True)
        bridge=SQLiteIdentityBridge(store,installation)
        def register(uid):
            raw,_=store.create_session(uid)
            identity=bridge.resolve_session(raw)
            store.logout(raw)
            return db.execute("""INSERT INTO panadan_knowledge.principals
                (authority_namespace,authority_subject,kind,state)
                VALUES (%s,%s,'human','active') RETURNING id""",(identity.namespace,identity.subject)).fetchone()[0]
        a,r,o,n=[register(uid) for uid in (admin,reader,other,new)]
        workspaces=[]
        collection_scopes=[]
        for slug,name,person in (("synthetic-a","سازمان نمونه الف",r),("synthetic-b","سازمان نمونه ب",o)):
            w=db.execute("""INSERT INTO panadan_knowledge.workspaces(slug,name,state,timezone)
                VALUES (%s,%s,'active','Asia/Tehran') RETURNING id""",(slug,name)).fetchone()[0]
            workspaces.append(w)
            memberships=[]
            for principal,key,label,caps in ((a,"administrator","مدیر فضای کاری",CAPABILITIES),
                                              (person,"reader","مشاهده‌گر",{"workspace.read"})):
                m=db.execute("""INSERT INTO panadan_knowledge.memberships(workspace_id,principal_id,state)
                    VALUES (%s,%s,'active') RETURNING id""",(w,principal)).fetchone()[0]
                memberships.append(m)
                role=db.execute("""INSERT INTO panadan_knowledge.role_versions
                    (workspace_id,role_key,rev,name,capability_set,state)
                    VALUES (%s,%s,1,%s,%s,'active') RETURNING id""",
                    (w,key,label,Jsonb(sorted(caps)))).fetchone()[0]
                db.execute("""INSERT INTO panadan_knowledge.membership_roles
                    (workspace_id,membership_id,role_version_id,granted_by) VALUES (%s,%s,%s,%s)""",(w,m,role,m))
                for cap in caps:
                    db.execute("""INSERT INTO panadan_knowledge.scope_grants
                        (workspace_id,membership_id,capability,grantor,valid_from)
                        VALUES (%s,%s,%s,%s,clock_timestamp()-interval '1 day')""",(w,m,cap,m))
            collection_scopes.append(seed_preview_resource_scope(
                db, w, "operator-a" if slug == "synthetic-a" else "operator-b", *memberships,
                reader_transcript=slug == "synthetic-b"))
    collect_preview_resources(port, collection_scopes)
    os.environ.update(PANADAN_AUTH_DB=str(path),PANADAN_AUTH_BACKEND="sqlite",
        PANADAN_ADMIN_USER="admin",PANADAN_ADMIN_PASSWORD=PASSWORD,PANADAN_COOKIE_SECURE="false",
        PANADAN_KNOWLEDGE_PREVIEW="YES",PANADAN_KNOWLEDGE_PREVIEW_ISOLATED="YES",PANADAN_KNOWLEDGE_PREVIEW_RESOURCES="YES",
        PANADAN_KNOWLEDGE_PREVIEW_PORT=str(port),PANADAN_KNOWLEDGE_PREVIEW_INSTALLATION=str(installation),
        PANADAN_KNOWLEDGE_PREVIEW_WORKSPACES=",".join(map(str,workspaces)))
    print("Synthetic preview only: http://127.0.0.1:8765/login",flush=True)
    print("Login: admin (both workspaces), reader (A), other (B), newmember (no access)",flush=True)
    print("Synthetic password:",PASSWORD,flush=True)
    print("Open http://127.0.0.1:8765/workspace after login.",flush=True)
    print("Provisioned newmember principal (for testing Add member):",n,flush=True)
    from server.main import app
    import uvicorn
    uvicorn.run(app,host="127.0.0.1",port=8765,access_log=False)


if __name__=="__main__":
    main()
