"""Studio browser writes use scoped, limited PostgreSQL roles."""

import os
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.templating import Jinja2Templates
from psycopg import errors
from psycopg.conninfo import conninfo_to_dict
import pytest

from server.knowledge_scope import OBJECTIVE_AUTHOR, PIPELINE_AUTHOR
from server.knowledge_web import PreviewConfig, build_router
from test_knowledge_configuration import configuration
from test_knowledge_durable_work import work
from test_knowledge_foundation import _reject, db
from test_knowledge_resource_web import resource_web, runtime
from test_knowledge_run_admission import admission
from test_knowledge_studio_web import studio_web
from test_knowledge_web import ROOT, _login, _url


M014 = ROOT / "database/migrations/014_knowledge_objective_authoring.sql"
M015 = ROOT / "database/migrations/015_knowledge_pipeline_authoring.sql"
ORIGIN = "http://127.0.0.1:8765"


@pytest.fixture
def objective_web(studio_web):
    s, _ = studio_web
    db=s["db"]
    with db.transaction():
        _reject(db,errors.RaiseException,M014.read_text(encoding="utf-8"))
        db.execute("SELECT set_config('panadan.knowledge_migration_target','panadan_ci',true)")
        for _ in range(2):
            db.execute(M014.read_text(encoding="utf-8"))
        db.execute(f"GRANT {OBJECTIVE_AUTHOR} TO panadan_knowledge_test_login WITH INHERIT FALSE, SET TRUE")
    namespace = s["bridge"].resolve_session(s["admin"]).namespace.removeprefix("sqlite:")
    port = int(conninfo_to_dict(os.environ["PANADAN_PLATFORM_TEST_DSN"])["port"])
    config = PreviewConfig(port,UUID(namespace),(s["a"],s["b"]),resources=True,studio=True,objective_authoring=True)
    app = FastAPI()
    app.include_router(build_router(s["store"],Jinja2Templates(directory=str(ROOT/"templates")),config))
    try:
        with TestClient(app,base_url=ORIGIN) as client:
            yield s,client
    finally:
        with db.transaction():
            db.execute(f"REVOKE {OBJECTIVE_AUTHOR} FROM panadan_knowledge_test_login")
            db.execute(f"DROP OWNED BY {OBJECTIVE_AUTHOR}")
            db.execute(f"DROP ROLE {OBJECTIVE_AUTHOR}")


def _policy(db,workspace):
    return str(db.execute("""SELECT id FROM panadan_knowledge.policy_versions
        WHERE workspace_id=%s AND kind='validation' AND state='approved'""",(workspace,)).fetchone()[0])


def test_objective_authoring_creates_template_and_custom_then_versions_metadata(objective_web):
    s,client = objective_web
    db=s["db"]
    csrf=_login(s,client,"admin")
    listing=client.get(_url(s,"a","objectives"))
    assert listing.status_code==200 and "تعریف هدف دانش" in listing.text
    path=_url(s,"a","objective")
    fields=dict(csrf=csrf,key="browser_objective",label="هدف آزمایشی <tag>",purpose="ثبت نوع تغییر",
                expected_revision=0,template="customer_questions",policy=_policy(db,s["a"]))
    response=client.post(path,data=fields,headers={"Origin":ORIGIN},follow_redirects=False)
    assert response.status_code==303 and response.headers["location"]==_url(s,"a","objectives")
    assert "&lt;tag&gt;" in client.get(_url(s,"a","objectives")).text
    revision=fields | {"expected_revision":1,"label":"هدف بازبینی‌شده"}
    assert client.post(path,data=revision,headers={"Origin":ORIGIN},follow_redirects=False).status_code==303
    assert client.post(path,data=revision,headers={"Origin":ORIGIN}).status_code==409
    assert client.post(path,data=fields | {"key":"custom_track","template":"","field":"requested_change","kind":"integer"},
                       headers={"Origin":ORIGIN},follow_redirects=False).status_code==303
    versions=db.execute("""SELECT v.rev,v.label,v.output_schema_id FROM panadan_knowledge.objectives o
        JOIN panadan_knowledge.objective_versions v ON v.workspace_id=o.workspace_id AND v.objective_id=o.id
        WHERE o.workspace_id=%s AND o.objective_key='browser_objective' ORDER BY v.rev""",(s["a"],)).fetchall()
    assert [row[:2] for row in versions]==[(1,"هدف آزمایشی <tag>"),(2,"هدف بازبینی‌شده")]
    assert versions[0][2]==versions[1][2]
    assert db.execute("""SELECT action,count(*) FROM panadan_knowledge.audit_events
        WHERE workspace_id=%s AND target_kind='objective_version' GROUP BY action ORDER BY action""",(s["a"],)).fetchall()==[
        ("objective.publish",2),("objective.revise",1),
    ]


def test_objective_writer_rejects_unauthorized_members_and_privilege_expansion(objective_web):
    s,client = objective_web
    db=s["db"]
    csrf=_login(s,client,"admin")
    path=_url(s,"a","objective")
    fields=dict(csrf=csrf,key="denied_objective",label="نمونه",purpose="مقصود ساختگی",
                expected_revision=0,template="customer_questions",policy=_policy(db,s["a"]))
    assert client.post(path,data=fields,headers={"Origin":"null"}).status_code==404
    assert client.post(path,data=fields | {"csrf":"wrong"},headers={"Origin":ORIGIN}).status_code==404
    assert client.post(_url(s,"b","objective"),data=fields,headers={"Origin":ORIGIN}).status_code==404
    user_csrf=_login(s,client,"user")
    assert client.post(path,data=fields | {"csrf":user_csrf},headers={"Origin":ORIGIN}).status_code==404
    assert db.execute("SELECT count(*) FROM panadan_knowledge.objectives WHERE objective_key='denied_objective'").fetchone()==(0,)
    with db.transaction():
        db.execute(f"SET LOCAL ROLE {OBJECTIVE_AUTHOR}")
        assert db.execute("SELECT count(id) FROM panadan_knowledge.objectives").fetchone()==(0,)
        _reject(db,errors.InsufficientPrivilege,"SELECT text_payload FROM panadan_knowledge.representations")
        _reject(db,errors.InsufficientPrivilege,"UPDATE panadan_knowledge.pipelines SET enabled=true")


@pytest.fixture
def pipeline_web(objective_web):
    s,_ = objective_web
    db = s["db"]
    migration = M015.read_text(encoding="utf-8")
    with db.transaction():
        _reject(db,errors.RaiseException,migration)
        db.execute("SELECT set_config('panadan.knowledge_migration_target','panadan_ci',true)")
        for _ in range(2):
            db.execute(migration)
        db.execute(f"GRANT {PIPELINE_AUTHOR} TO panadan_knowledge_test_login WITH INHERIT FALSE, SET TRUE")
    namespace = s["bridge"].resolve_session(s["admin"]).namespace.removeprefix("sqlite:")
    port = int(conninfo_to_dict(os.environ["PANADAN_PLATFORM_TEST_DSN"])["port"])
    config = PreviewConfig(port,UUID(namespace),(s["a"],s["b"]),resources=True,studio=True,
                           objective_authoring=True,pipeline_authoring=True)
    app = FastAPI()
    app.include_router(build_router(s["store"],Jinja2Templates(directory=str(ROOT/"templates")),config))
    try:
        with TestClient(app,base_url=ORIGIN) as client:
            yield s,client
    finally:
        with db.transaction():
            db.execute(f"REVOKE {PIPELINE_AUTHOR} FROM panadan_knowledge_test_login")
            db.execute(f"DROP OWNED BY {PIPELINE_AUTHOR}")
            db.execute(f"DROP ROLE {PIPELINE_AUTHOR}")


def _pipeline_fields(s,csrf):
    db = s["db"]
    checkpoint, = db.execute("SELECT id FROM panadan_knowledge.sync_checkpoints WHERE workspace_id=%s",(s["a"],)).fetchone()
    objective, = db.execute("SELECT current_version_id FROM panadan_knowledge.objectives WHERE workspace_id=%s",(s["a"],)).fetchone()
    return dict(csrf=csrf,key="browser_pipeline",label="خط پردازش ساختگی",expected_revision=0,
                checkpoint=str(checkpoint),objectives=[str(objective)],max_resources=5)


def test_pipeline_form_publishes_disabled_versions_and_audits(pipeline_web):
    s,client = pipeline_web
    db = s["db"]
    csrf = _login(s,client,"admin")
    listing = _url(s,"a","pipelines")
    path = _url(s,"a","pipeline")
    fields = _pipeline_fields(s,csrf)
    page = client.get(listing)
    assert page.status_code == 200 and "تعریف خط پردازش" in page.text and fields["checkpoint"] in page.text
    response = client.post(path,data=fields,headers={"Origin":ORIGIN},follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == listing
    assert fields["label"] in client.get(listing).text
    revised = fields | {"expected_revision":1,"label":"خط پردازش بازبینی‌شده","max_resources":8}
    assert client.post(path,data=revised,headers={"Origin":ORIGIN},follow_redirects=False).status_code == 303
    assert client.post(path,data=revised,headers={"Origin":ORIGIN}).status_code == 409
    versions = db.execute("""SELECT v.rev,v.max_resources,p.enabled,o.objective_version_id
        FROM panadan_knowledge.pipelines p JOIN panadan_knowledge.pipeline_versions v
          ON v.workspace_id=p.workspace_id AND v.pipeline_id=p.id
        JOIN panadan_knowledge.pipeline_objectives o ON o.workspace_id=v.workspace_id AND o.pipeline_version_id=v.id
        WHERE p.workspace_id=%s AND p.pipeline_key='browser_pipeline' ORDER BY v.rev""",(s["a"],)).fetchall()
    objective = UUID(fields["objectives"][0])
    assert versions == [(1,5,False,objective),(2,8,False,objective)]
    assert db.execute("""SELECT action,count(*) FROM panadan_knowledge.audit_events
        WHERE workspace_id=%s AND target_kind='pipeline_version' GROUP BY action ORDER BY action""",(s["a"],)).fetchall()==[
        ("pipeline.publish",1),("pipeline.revise",1),
    ]


def test_pipeline_form_enforces_source_grant_tenant_and_limited_role(pipeline_web):
    s,client = pipeline_web
    db = s["db"]
    csrf = _login(s,client,"admin")
    fields = _pipeline_fields(s,csrf)
    path = _url(s,"a","pipeline")
    assert client.post(path,data=fields,headers={"Origin":"null"}).status_code == 404
    assert client.post(path,data=fields | {"csrf":"wrong"},headers={"Origin":ORIGIN}).status_code == 404
    assert client.post(_url(s,"b","pipeline"),data=fields,headers={"Origin":ORIGIN}).status_code == 404
    other, = db.execute("SELECT id FROM panadan_knowledge.sync_checkpoints WHERE workspace_id=%s",(s["b"],)).fetchone()
    assert client.post(path,data=fields | {"checkpoint":str(other)},headers={"Origin":ORIGIN}).status_code == 404
    user_csrf = _login(s,client,"user")
    assert client.post(path,data=fields | {"csrf":user_csrf},headers={"Origin":ORIGIN}).status_code == 404
    fields["csrf"] = _login(s,client,"admin")
    db.execute("""UPDATE panadan_knowledge.source_scope_grants SET revoked_at=clock_timestamp()
        WHERE workspace_id=%s AND membership_id=%s AND capability='representation.read'""",(s["a"],s["owner"]))
    assert client.post(path,data=fields,headers={"Origin":ORIGIN}).status_code == 404
    assert "تعریف خط پردازش" not in client.get(_url(s,"a","pipelines")).text
    assert db.execute("SELECT count(*) FROM panadan_knowledge.pipelines WHERE pipeline_key='browser_pipeline'").fetchone() == (0,)
    with db.transaction():
        db.execute(f"SET LOCAL ROLE {PIPELINE_AUTHOR}")
        assert db.execute("SELECT count(id) FROM panadan_knowledge.pipelines").fetchone() == (0,)
        _reject(db,errors.InsufficientPrivilege,"SELECT text_payload FROM panadan_knowledge.representations")
        _reject(db,errors.InsufficientPrivilege,"SELECT state FROM panadan_knowledge.runs")
