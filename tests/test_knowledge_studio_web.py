"""Scoped read-only Studio views over actual deterministic run effects."""

import os
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.templating import Jinja2Templates
from psycopg import errors
from psycopg.conninfo import conninfo_to_dict
from psycopg.types.json import Jsonb
import pytest

from server.knowledge_authorization import STUDIO_CAPABILITIES
from server.knowledge_durable_work import claim_work, finish_work, reconcile_run, start_run
from server.knowledge_web import PreviewConfig, build_router
from test_knowledge_configuration import configuration
from test_knowledge_durable_work import work
from test_knowledge_foundation import _reject, db
from test_knowledge_resource_web import resource_web, runtime
from test_knowledge_run_admission import admission
from test_knowledge_web import ROOT, _env, _login, _url


M013 = ROOT / "database/migrations/013_knowledge_studio_preview.sql"


def test_studio_requires_explicit_resource_preview():
    with pytest.raises(ValueError,match="isolated resource preview"):
        PreviewConfig.from_env(_env() | {"PANADAN_KNOWLEDGE_PREVIEW_STUDIO":"YES"})
    config = PreviewConfig.from_env(_env() | {
        "PANADAN_KNOWLEDGE_PREVIEW_RESOURCES":"YES", "PANADAN_KNOWLEDGE_PREVIEW_STUDIO":"YES",
    })
    assert config.resources and config.studio


@pytest.fixture
def studio_web(work,resource_web):
    db, _, admit = work
    s, _, left, _, _, _, _ = resource_web
    with db.transaction():
        _reject(db,errors.RaiseException,M013.read_text(encoding="utf-8"))
        db.execute("SELECT set_config('panadan.knowledge_migration_target','panadan_ci',true)")
        for _ in range(2):
            db.execute(M013.read_text(encoding="utf-8"))
        role, = db.execute("""INSERT INTO panadan_knowledge.role_versions
            (workspace_id,role_key,rev,name,capability_set,state)
            VALUES (%s,'studio-config',1,'Studio',%s,'active') RETURNING id""",
            (left.workspace,Jsonb(sorted(STUDIO_CAPABILITIES)))).fetchone()
        db.execute("""INSERT INTO panadan_knowledge.membership_roles
            (workspace_id,membership_id,role_version_id,granted_by) VALUES (%s,%s,%s,%s)""",
            (left.workspace,s["owner"],role,s["owner"]))
        for cap in STUDIO_CAPABILITIES:
            db.execute("""INSERT INTO panadan_knowledge.scope_grants
                (workspace_id,membership_id,grantor,capability,valid_from)
                VALUES (%s,%s,%s,%s,clock_timestamp()-interval '1 day')""",
                (left.workspace,s["owner"],s["owner"],cap))
    run = admit()
    start_run(db,**run)
    token = claim_work(db,**run,worker_id=uuid4())
    assert finish_work(db,**run,lease=token) == "succeeded"
    assert reconcile_run(db,**run) == "succeeded"
    port = int(conninfo_to_dict(os.environ["PANADAN_PLATFORM_TEST_DSN"])["port"])
    namespace = s["bridge"].resolve_session(s["admin"]).namespace.removeprefix("sqlite:")
    config = PreviewConfig(port,UUID(namespace),(s["a"],s["b"]),resources=True,studio=True)
    app = FastAPI()
    app.include_router(build_router(s["store"],Jinja2Templates(directory=str(ROOT/"templates")),config))
    with TestClient(app,base_url="http://127.0.0.1:8765") as client:
        yield s,client


def test_studio_reads_authorized_objectives_pipeline_and_measured_execution(studio_web):
    s,c = studio_web
    _login(s,c,"admin")
    objectives = c.get(_url(s,"a","objectives"))
    assert objectives.status_code == 200 and "پرسش‌های جدید" in objectives.text and "فرصت‌های محتوا" in objectives.text
    pipeline = c.get(_url(s,"a","pipelines"))
    assert pipeline.status_code == 200 and "گروه رزرو" in pipeline.text and "اجرای نمونه" in pipeline.text
    runs = c.get(_url(s,"a","runs"))
    assert runs.status_code == 200 and runs.headers["cache-control"] == "no-store, private"
    assert "تکمیل شده" in runs.text and "1 بررسی، 1 آماده" in runs.text and "نامشخص" in runs.text
    assert c.post(_url(s,"a","runs")).status_code == 405
    assert c.get(_url(s,"b","runs")).status_code == 404
    with s["db"].transaction():
        s["db"].execute("SET LOCAL ROLE panadan_knowledge_reader")
        _reject(s["db"],errors.InsufficientPrivilege,"SELECT manifest FROM panadan_knowledge.runs")


def test_studio_denies_direct_links_and_recomputes_resource_and_role_revocation(studio_web):
    s,c = studio_web
    _login(s,c,"user")
    assert _url(s,"a","objectives") not in c.get(_url(s,"a")).text
    for page in ("objectives","pipelines","runs"):
        assert c.get(_url(s,"a",page)).status_code == 404
    _login(s,c,"admin")
    db = s["db"]
    db.execute("""UPDATE panadan_knowledge.source_scope_grants SET revoked_at=clock_timestamp()
        WHERE workspace_id=%s AND membership_id=%s AND capability='representation.read'""",(s["a"],s["owner"]))
    assert "اجرای نمونه" not in c.get(_url(s,"a","runs")).text
    db.execute("""UPDATE panadan_knowledge.scope_grants SET revoked_at=clock_timestamp()
        WHERE workspace_id=%s AND membership_id=%s AND capability='objective.configure'""",(s["a"],s["owner"]))
    assert c.get(_url(s,"a","objectives")).status_code == 404
