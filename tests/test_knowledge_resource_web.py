"""Resource Explorer web authorization and scope projection on PostgreSQL 18."""

from hashlib import sha256
from datetime import timedelta
import os
import re
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.templating import Jinja2Templates
from psycopg.conninfo import conninfo_to_dict
from psycopg.types.json import Jsonb
import pytest

from server.knowledge_resource_views import PAGE_SIZE
from server.knowledge_web import PreviewConfig, build_router
from test_knowledge_call_collection import M008
from test_knowledge_call_resources import M007
from test_knowledge_scope import db, runtime
from test_knowledge_web import ROOT, _login, _url, _env
from tools.knowledge_preview_resources import START, seed_preview_resource_scope


M009 = ROOT / "database/migrations/009_knowledge_resource_explorer.sql"
CONTENT = "متن آزمایشی <tag> [PHONE]"


def _seed_resource(db, scope, external_id, *, operator=None, transcript=CONTENT):
    workspace, source = scope.workspace, scope.source
    resource, = db.execute("""INSERT INTO panadan_knowledge.resources(workspace_id,source_id,external_id)
        VALUES (%s,%s,%s) RETURNING id""", (workspace, source, str(external_id))).fetchone()
    revision, = db.execute("""INSERT INTO panadan_knowledge.resource_revisions
        (workspace_id,source_id,resource_id,operator_scope_id,rev,source_order,event_at,source_changed_at,operation,
          normalized_metadata,contract_id,attribute_schema_id,retention_policy_id,availability,transcript_outcome)
        SELECT c.workspace_id,c.source_id,%s,%s,1,1,%s,%s,'upsert',%s,c.contract_id,c.attribute_schema_id,
          c.retention_policy_id,'active',%s FROM panadan_knowledge.sync_checkpoints c
        WHERE c.workspace_id=%s AND c.id=%s RETURNING id""",
        (resource, operator or scope.operator, START + timedelta(days=1), START, Jsonb({"duration_seconds": 75}),
         "filtered" if transcript else "transcript_missing", workspace, scope.checkpoint)).fetchone()
    db.execute("""UPDATE panadan_knowledge.resources SET availability='active',current_revision_id=%s
        WHERE workspace_id=%s AND id=%s""", (revision, workspace, resource))
    if transcript:
        db.execute("""INSERT INTO panadan_knowledge.representations(workspace_id,resource_revision_id,redaction_policy_id,
            representation_rev,availability,expires_at,text_payload,filtered_digest)
            SELECT c.workspace_id,%s,c.redaction_policy_id,1,'active',now()+interval '1 day',%s,%s
            FROM panadan_knowledge.sync_checkpoints c WHERE c.workspace_id=%s AND c.id=%s""",
            (revision, transcript, sha256(transcript.encode()).hexdigest(), workspace, scope.checkpoint))
    return resource


@pytest.fixture
def resource_web(runtime):
    s = runtime
    db = s["db"]
    with db.transaction():
        db.execute("SELECT set_config('panadan.knowledge_migration_target','panadan_ci',true)")
        for migration in (M007, M008, M009, M009):
            db.execute(migration.read_text(encoding="utf-8"))
        left = seed_preview_resource_scope(db,s["a"],"operator-a",s["owner"],s["overlap"],reader_transcript=False)
        right = seed_preview_resource_scope(db,s["b"],"operator-b",s["overlap"],None,reader_transcript=False)
        visible = _seed_resource(db,left,101)
        remote = _seed_resource(db,right,201,transcript="workspace-b-private")
        hidden_operator, = db.execute("""INSERT INTO panadan_knowledge.operator_scopes
            (workspace_id,source_id,external_operator_key,label,state)
            VALUES (%s,%s,'other-operator','operator-hidden','active') RETURNING id""",
            (left.workspace,left.source)).fetchone()
        db.execute("""INSERT INTO panadan_knowledge.contract_operator_scopes
            SELECT workspace_id,source_id,contract_id,%s FROM panadan_knowledge.sync_checkpoints WHERE workspace_id=%s AND id=%s""",
            (hidden_operator,left.workspace,left.checkpoint))
        hidden = _seed_resource(db,left,991,operator=hidden_operator,transcript="operator-private")
        db.execute("""INSERT INTO panadan_knowledge.sync_runs
            (workspace_id,checkpoint_id,cursor_version,state,examined,accepted,unchanged,excluded)
            VALUES (%s,%s,1,'succeeded',1,1,0,0)""", (left.workspace,left.checkpoint))
    db.autocommit = True
    port = int(conninfo_to_dict(os.environ["PANADAN_PLATFORM_TEST_DSN"])["port"])
    namespace = s["bridge"].resolve_session(s["admin"]).namespace.removeprefix("sqlite:")
    config = PreviewConfig(port, UUID(namespace), (s["a"],s["b"]), resources=True)
    app = FastAPI()
    app.include_router(build_router(s["store"], Jinja2Templates(directory=str(ROOT/"templates")), config))
    try:
        with TestClient(app,base_url="http://127.0.0.1:8765") as client:
            yield s, client, left, right, visible, remote, hidden
    finally:
        with db.transaction():
            db.execute("DROP OWNED BY panadan_knowledge_collector")
            db.execute("DROP ROLE panadan_knowledge_collector")


def test_resources_require_explicit_isolated_preview_flag():
    assert not PreviewConfig.from_env(_env()).resources
    config = PreviewConfig.from_env(_env() | {"PANADAN_KNOWLEDGE_PREVIEW_RESOURCES": "YES"})
    assert config.resources


def test_resource_views_are_scoped_by_workspace_operator_and_direct_id(resource_web):
    s, client, left, right, resource, remote, hidden = resource_web
    _login(s,client,"admin")
    resources = _url(s,"a","resources")
    listing = client.get(resources)
    assert listing.status_code == 200 and str(resource) in listing.text
    assert str(hidden) not in listing.text and str(remote) not in listing.text
    assert "operator-private" not in listing.text and "workspace-b-private" not in listing.text
    detail = client.get(f"{resources}/{resource}?call=101")
    assert detail.status_code == 200 and "&lt;tag&gt; [PHONE]" in detail.text
    assert '<tag>' not in detail.text
    assert detail.headers["cache-control"] == "no-store, private"
    assert f'{resources}?call=101' in detail.text
    unknown = client.get(f"{resources}/{uuid4()}")
    for path in (f"{resources}/{hidden}",f"{resources}/{remote}",_url(s,"b","resources")):
        denied = client.get(path)
        assert denied.status_code == 404 and denied.text == unknown.text
    assert client.get(f"{resources}?source={right.source}").status_code == 404
    localized_query = client.get(resources, params={"call":"۱۰١"})
    assert localized_query.status_code == 200 and str(resource) in localized_query.text
    assert client.get(f"{resources}?source={left.source}&call=9999").status_code == 200
    integrations = client.get(_url(s,"a","integrations"))
    assert integrations.status_code == 200 and "گروه رزرو" in integrations.text and "گروه پشتیبانی" not in integrations.text
    login_page = _url(s,"a","overview")
    _login(s,client,"new")
    assert client.get(login_page).status_code == 404


def test_resource_transcript_requires_both_role_and_grant_and_is_suppressed_on_expiry(resource_web):
    s, client, left, _, resource, _, _ = resource_web
    db = s["db"]
    path = f'{_url(s,"a","resources")}/{resource}'
    _login(s,client,"user")
    view = client.get(path)
    assert view.status_code == 200 and "75" in view.text and "[PHONE]" not in view.text
    grant, = db.execute("""INSERT INTO panadan_knowledge.source_scope_grants
        (workspace_id,membership_id,grantor,scope_kind,source_id,operator_scope_id,capability,valid_from)
        VALUES (%s,%s,%s,'operator',%s,%s,'representation.read',clock_timestamp()-interval '1 day') RETURNING id""",
        (left.workspace,s["overlap"],s["owner"],left.source,left.operator)).fetchone()
    assert "[PHONE]" not in client.get(path).text
    db.execute("""INSERT INTO panadan_knowledge.membership_roles(workspace_id,membership_id,role_version_id,granted_by)
        SELECT workspace_id,%s,id,%s FROM panadan_knowledge.role_versions
        WHERE workspace_id=%s AND role_key='resource-reader'""", (s["overlap"],s["owner"],left.workspace))
    assert "[PHONE]" in client.get(path).text
    db.execute("UPDATE panadan_knowledge.source_scope_grants SET valid_until=clock_timestamp()-interval '1 second' WHERE id=%s", (grant,))
    assert "[PHONE]" not in client.get(path).text
    _login(s,client,"admin")
    db.execute("UPDATE panadan_knowledge.representations SET expires_at=clock_timestamp()-interval '1 second'")
    assert "[PHONE]" not in client.get(path).text
    db.execute("UPDATE panadan_knowledge.representations SET expires_at=clock_timestamp()+interval '1 day'")
    assert "[PHONE]" in client.get(path).text
    db.execute("UPDATE panadan_knowledge.resources SET availability='restricted' WHERE workspace_id=%s AND id=%s",
               (left.workspace,resource))
    assert "[PHONE]" not in client.get(path).text
    db.execute("""UPDATE panadan_knowledge.source_scope_grants SET revoked_at=clock_timestamp()
        WHERE workspace_id=%s AND membership_id=%s AND capability='resource.read'""", (left.workspace,s["owner"]))
    assert client.get(path).status_code == 404


def test_resource_pagination_is_keyset_bounded_and_filters_preserve_scope(resource_web):
    s, client, left, _, _, _, _ = resource_web
    for i in range(PAGE_SIZE):
        _seed_resource(s["db"],left,300+i,transcript=None)
    _login(s,client,"admin")
    base = _url(s,"a","resources")
    listing = client.get(f"{base}?source={left.source}")
    assert listing.status_code == 200 and listing.text.count('class="resource-row"') == PAGE_SIZE
    cursor = re.search(r"after=([0-9a-f-]+)", listing.text).group(1)
    next_page = client.get(f"{base}?source={left.source}&after={cursor}")
    assert next_page.status_code == 200 and next_page.text.count('class="resource-row"') == 1
    assert "ابتدای فهرست" in next_page.text
    assert client.get(f"{base}?source={left.source}&after={uuid4()}").status_code == 404
