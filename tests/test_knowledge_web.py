"""M01.4 route and template regressions against actual restricted PG logins."""
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.templating import Jinja2Templates
import pytest
from psycopg.conninfo import conninfo_to_dict
import os

from server.knowledge_web import PreviewConfig, build_router
from test_knowledge_scope import runtime, db

ROOT=Path(__file__).resolve().parents[1]


def _env():
    return {"PANADAN_KNOWLEDGE_PREVIEW":"YES",
            "PANADAN_KNOWLEDGE_PREVIEW_ISOLATED":"YES",
            "PANADAN_COOKIE_SECURE":"false",
            "PANADAN_KNOWLEDGE_PREVIEW_PORT":"54329",
            "PANADAN_KNOWLEDGE_PREVIEW_INSTALLATION":str(uuid4()),
            "PANADAN_KNOWLEDGE_PREVIEW_WORKSPACES":str(uuid4())}


def test_preview_is_disabled_by_default():
    assert PreviewConfig.from_env({}) is None
    assert PreviewConfig.from_env({"PANADAN_KNOWLEDGE_PREVIEW":"no"}) is None


def test_preview_configuration_requires_explicit_isolation():
    env=_env()
    config=PreviewConfig.from_env(env)
    assert config.port==54329 and len(config.candidates)==1
    for bad in ({"PANADAN_KNOWLEDGE_PREVIEW_ISOLATED":"no"},
                {"PANADAN_PUBLIC_ORIGIN":"https://example.invalid"},
                {"PANADAN_COOKIE_SECURE":"true"},
                {"PANADAN_AUTH_BACKEND":"postgres-staging"},
                {"PGHOST":"127.0.0.1"},
                {"PANADAN_KNOWLEDGE_PREVIEW_PORT":"0"},
                {"PANADAN_KNOWLEDGE_PREVIEW_WORKSPACES":"invalid"}):
        with pytest.raises(ValueError):
            PreviewConfig.from_env(env|bad)


def test_template_unavailable_state_has_no_workspace_metadata():
    from starlette.requests import Request
    from server.knowledge_web import HEADERS, PAGES, LABELS
    request=Request({"type":"http","method":"GET","path":"/workspace","headers":[]})
    template=Jinja2Templates(directory=str(ROOT/"templates"))
    response=template.TemplateResponse(request,"knowledge_workspace.html",
        {"pages":PAGES,"labels":LABELS,"choices":[],"data":None,"page":"overview",
         "csrf":"","legacy":False,"message":"محدود","error":True},headers=HEADERS)
    assert b'dir="rtl"' in response.body and b'role="alert"' in response.body
    assert b'name="csrf"' not in response.body
    assert response.headers["cache-control"]=="no-store, private"


@pytest.fixture
def web(runtime):
    s=runtime
    port=int(conninfo_to_dict(os.environ["PANADAN_PLATFORM_TEST_DSN"])["port"])
    ns=s["bridge"].resolve_session(s["admin"]).namespace.removeprefix("sqlite:")
    from uuid import UUID
    config=PreviewConfig(port,UUID(ns),(s["a"],s["b"]))
    app=FastAPI()
    app.include_router(build_router(s["store"],Jinja2Templates(directory=str(ROOT/"templates")),config))
    with TestClient(app,base_url="http://127.0.0.1:8765") as client:
        yield s,client


def _login(s,client,who):
    raw=s[who]
    client.cookies.set("panadan_session",raw)
    return s["store"].session(raw)["csrf"]


def _url(s,workspace,page="overview"):
    return f"/workspace/{s[workspace]}/{page}"


def test_workspace_route_guards_and_no_access_state(web):
    s,c=web
    assert c.get("/workspace").status_code==404
    _login(s,c,"new")
    empty=c.get("/workspace")
    assert empty.status_code==200 and "synthetic-a" not in empty.text and "synthetic-b" not in empty.text
    _login(s,c,"user")
    a=c.get(_url(s,"a"))
    assert a.status_code==200 and "synthetic-a" in a.text and "synthetic-b" not in a.text
    assert 'aria-current="page"' in a.text
    assert a.headers["cache-control"]=="no-store, private"
    for path in (_url(s,"b"),_url(s,"a","members"),_url(s,"a","roles"),f"/workspace/{uuid4()}/overview"):
        denied=c.get(path)
        assert denied.status_code==404 and "synthetic-a" not in denied.text and "synthetic-b" not in denied.text
    _login(s,c,"other")
    b=c.get(_url(s,"b"))
    assert b.status_code==200 and "synthetic-b" in b.text and "synthetic-a" not in b.text
    assert c.get(_url(s,"a")).status_code==404


def test_authorized_workspace_switch_recomputes_navigation(web):
    s,c=web
    # One user has administration in A and read-only access in B.
    db=s["db"]
    with db.transaction():
        member=db.execute("""INSERT INTO panadan_knowledge.memberships(workspace_id,principal_id,state)
            VALUES (%s,%s,'active') RETURNING id""",(s["b"],s["p"])).fetchone()[0]
        role=db.execute("SELECT id FROM panadan_knowledge.role_versions WHERE workspace_id=%s AND role_key='initial-reader'",(s["b"],)).fetchone()[0]
        db.execute("""INSERT INTO panadan_knowledge.membership_roles(workspace_id,membership_id,role_version_id,granted_by)
            VALUES (%s,%s,%s,%s)""",(s["b"],member,role,member))
        db.execute("""INSERT INTO panadan_knowledge.scope_grants(workspace_id,membership_id,capability,grantor,valid_from)
            VALUES (%s,%s,'workspace.read',%s,clock_timestamp()-interval '1 day')""",(s["b"],member,member))
    _login(s,c,"admin")
    assert "synthetic-a" in c.get("/workspace").text and "synthetic-b" in c.get("/workspace").text
    a=c.get(_url(s,"a","members"))
    assert a.status_code==200 and str(s["overlap"]) in a.text and "reader" in a.text and "prf_" not in a.text
    b=c.get(_url(s,"b"))
    assert b.status_code==200 and _url(s,"b","roles") not in b.text
    assert c.get(_url(s,"b","members")).status_code==404
    assert c.get(_url(s,"a","roles")).status_code==200


def test_workspace_commands_csrf_delegation_and_revocation(web):
    s,c=web
    path=_url(s,"a","command")
    csrf=_login(s,c,"admin")
    params={"operation":"add_member","target":str(s["n"]),"csrf":csrf}
    page=c.get(_url(s,"a","members"))
    assert page.headers["Referrer-Policy"]=="same-origin"
    assert c.post(path,data=params|{"csrf":"wrong"}).status_code==404
    assert c.post(path,data=params,headers={"Origin":"null"}).status_code==404
    assert c.post(path,data=params,headers={"Origin":"https://foreign.invalid"}).status_code==404
    assert c.post(_url(s,"b","command"),data=params).status_code==404
    assert c.post(path,data=params,headers={"Origin":str(c.base_url).rstrip("/")},
                  follow_redirects=False).status_code==303
    db=s["db"]
    member=db.execute("SELECT id FROM panadan_knowledge.memberships WHERE workspace_id=%s AND principal_id=%s",(s["a"],s["n"])).fetchone()[0]
    assert c.post(path,data={"operation":"create_role","csrf":csrf,"role_key":"web-reader",
                           "name":"<script>unsafe</script>","capabilities":"workspace.read"},follow_redirects=False).status_code==303
    role=db.execute("SELECT id FROM panadan_knowledge.role_versions WHERE workspace_id=%s AND role_key='web-reader'",(s["a"],)).fetchone()[0]
    page=c.get(_url(s,"a","roles"))
    assert page.status_code==200 and "&lt;script&gt;unsafe&lt;/script&gt;" in page.text
    assert "<script>unsafe</script>" not in page.text
    assert c.post(path,data={"operation":"assign_role","csrf":csrf,"target":str(member),"role":str(role)},follow_redirects=False).status_code==303
    assert c.post(path,data={"operation":"grant_scope","csrf":csrf,"target":str(member),"capability":"workspace.read"},follow_redirects=False).status_code==303
    _login(s,c,"new")
    assert c.get(_url(s,"a")).status_code==200
    reader_csrf=s["store"].session(s["new"])["csrf"]
    assert c.post(path,data={"operation":"create_role","csrf":reader_csrf,"role_key":"escalation","name":"No",
                           "capabilities":"roles.manage"}).status_code==404
    csrf=_login(s,c,"admin")
    revoke={"operation":"revoke_membership","target":str(member),"csrf":csrf}
    assert c.post(path,data=revoke).status_code==404
    assert c.post(path,data=revoke|{"confirm":"yes"},follow_redirects=False).status_code==303
    _login(s,c,"new")
    assert c.get(_url(s,"a")).status_code==404
    db.rollback()
