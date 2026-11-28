"""M02.1 contract and additive schema checks on disposable PostgreSQL 18."""

from hashlib import sha256
from uuid import uuid4

from psycopg import errors
from psycopg.types.json import Jsonb
import pytest

from server.knowledge_call_contract import (
    SOURCE_FIELDS,
    SYNTHETIC_ADAPTER,
    UnsupportedCallContract,
    call_metadata_schema,
    require_synthetic_call_contract,
    synthetic_call_contract,
    validate_call_metadata,
)
from test_knowledge_foundation import ROOT, _apply, _principal, _reject, _workspace, db
from test_knowledge_scope import M005, M006


M007 = ROOT / "database/migrations/007_knowledge_call_resources.sql"
TABLES = {
    "sources", "source_contract_versions", "operator_scopes", "contract_operator_scopes",
    "source_scope_grants", "attribute_schema_versions", "resources", "resource_revisions", "representations",
}


def test_call_contract_requires_exact_reviewed_fields_and_synthetic_state():
    contract = synthetic_call_contract()
    assert tuple(contract["field_allowlist"]) == SOURCE_FIELDS
    params = dict(kind="database", adapter=SYNTHETIC_ADAPTER, state="synthetic", contract=contract)
    require_synthetic_call_contract(**params)
    for invalid in (
        {"kind": "web"},
        {"adapter": "live-odoo"},
        {"state": "draft"},
        {"state": "retired"},
        {"contract": contract | {"field_allowlist": [*SOURCE_FIELDS, "phone"]}},
        {"contract": contract | {"revision_order": "unknown"}},
    ):
        with pytest.raises(UnsupportedCallContract, match="Unsupported synthetic call contract"):
            require_synthetic_call_contract(**(params | invalid))


def test_call_metadata_accepts_only_optional_bounded_integer_duration():
    for metadata in ({}, {"duration_seconds": None}, {"duration_seconds": 0}, {"duration_seconds": 86400}):
        validate_call_metadata(metadata)
    for bad in ([], None, {"transcript": "synthetic"}, *(
        {"duration_seconds": value} for value in (True, -1, 86401, 1.5, "10")
    )):
        with pytest.raises(ValueError):
            validate_call_metadata(bad)


def _previous(db):
    _apply(db)
    for migration in (M005, M006):
        db.execute(migration.read_text(encoding="utf-8"))


@pytest.fixture
def migrated(db):
    _previous(db)
    db.execute(M007.read_text(encoding="utf-8"))
    return db


def _source(db, workspace, key, version=1, source=None):
    if source is None:
        source, state = db.execute("""INSERT INTO panadan_knowledge.sources
            (workspace_id,source_key,label,connection_ref)
            VALUES (%s,%s,'Synthetic calls','synthetic-calls') RETURNING id,state""", (workspace, key)).fetchone()
        assert state == "disabled"
    contract, state = db.execute("""INSERT INTO panadan_knowledge.source_contract_versions
        (workspace_id,source_id,rev,adapter_version,contract)
        VALUES (%s,%s,%s,%s,%s) RETURNING id,state""",
        (workspace, source, version, SYNTHETIC_ADAPTER, Jsonb(synthetic_call_contract()))).fetchone()
    assert state == "draft"
    return source, contract


def _operator(db, workspace, source, key="operator-a"):
    return db.execute("""INSERT INTO panadan_knowledge.operator_scopes
        (workspace_id,source_id,external_operator_key) VALUES (%s,%s,%s) RETURNING id""",
        (workspace, source, key)).fetchone()[0]


def _bind(db, workspace, source, contract, operator):
    db.execute("""INSERT INTO panadan_knowledge.contract_operator_scopes VALUES (%s,%s,%s,%s)""",
               (workspace, source, contract, operator))


def _policies(db, workspace):
    principal = _principal(db, "source-test")
    member = db.execute("""INSERT INTO panadan_knowledge.memberships
        (workspace_id,principal_id,state) VALUES (%s,%s,'active') RETURNING id""",
        (workspace, principal)).fetchone()[0]
    policy_ids = []
    for kind in ("retention", "redaction"):
        policy_ids.append(db.execute("""INSERT INTO panadan_knowledge.policy_versions
            (workspace_id,kind,policy_key,rev,definition,state,approved_by,approved_at)
            VALUES (%s,%s,'synthetic',1,'{}','approved',%s,now()) RETURNING id""",
            (workspace, kind, member)).fetchone()[0])
    return member, *policy_ids


def _resource(db, workspace, source, external_id):
    return db.execute("""INSERT INTO panadan_knowledge.resources
        (workspace_id,source_id,external_id) VALUES (%s,%s,%s) RETURNING id""",
        (workspace, source, external_id)).fetchone()[0]


REVISION_INSERT = """INSERT INTO panadan_knowledge.resource_revisions
    (workspace_id,source_id,resource_id,contract_id,operator_scope_id,attribute_schema_id,retention_policy_id,
     normalized_metadata,rev,source_order,event_at,source_changed_at,operation,availability)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,1,1,now(),now(),'upsert','active') RETURNING id"""

REPRESENTATION_INSERT = """INSERT INTO panadan_knowledge.representations
    (workspace_id,resource_revision_id,redaction_policy_id,text_payload,filtered_digest,representation_rev,availability)
    VALUES (%s,%s,%s,%s,%s,1,'active') RETURNING id"""


def test_migration_guards_previous_boundary_and_explicit_target(db):
    _apply(db)
    _reject(db, errors.RaiseException, M007.read_text(encoding="utf-8"))
    for migration in (M005, M006):
        db.execute(migration.read_text(encoding="utf-8"))
    db.execute("SELECT set_config('panadan.knowledge_migration_target','wrong',true)")
    _reject(db, errors.RaiseException, M007.read_text(encoding="utf-8"))


def test_additive_migration_reapplies_and_leaves_resource_tables_closed(db):
    db.execute((ROOT / "database/migrations/001_multisource_foundation.sql").read_text(encoding="utf-8"))
    _previous(db)
    workspace = _workspace(db, "existing-tenant")
    for _ in range(2):
        db.execute(M007.read_text(encoding="utf-8"))
    assert db.execute("SELECT slug FROM panadan_knowledge.workspaces WHERE id=%s", (workspace,)).fetchone() == (
        "existing-tenant",
    )
    names = db.execute("""SELECT relname FROM pg_class
        WHERE relnamespace='panadan_knowledge'::regnamespace AND relrowsecurity AND relforcerowsecurity
        AND relname=ANY(%s)""", (sorted(TABLES),)).fetchall()
    assert {name for name, in names} == TABLES
    assert db.execute("SELECT to_regclass('panadan_ingest.sources') IS NOT NULL").fetchone() == (True,)
    _source(db, workspace, "one")
    with db.transaction():
        db.execute("SET LOCAL ROLE panadan_knowledge_owner")
        assert db.execute("SELECT count(*) FROM panadan_knowledge.sources").fetchone() == (0,)
        db.execute("RESET ROLE")
        db.execute("SET LOCAL ROLE panadan_knowledge_reader")
        assert db.execute("""SELECT has_table_privilege(
            current_user,'panadan_knowledge.sources','SELECT,INSERT')""").fetchone() == (False,)
        _reject(db, errors.InsufficientPrivilege, "SELECT * FROM panadan_knowledge.sources")


def test_source_and_operator_binding_rejects_mismatched_parents(migrated):
    db = migrated
    a, b = (_workspace(db, key) for key in ("source-a", "source-b"))
    source, contract = _source(db, a, "source-a")
    remote_source, remote_contract = _source(db, b, "source-a")
    second_source, second_contract = _source(db, a, "source-b")
    operator = _operator(db, a, source)
    _operator(db, b, remote_source)
    _bind(db, a, source, contract, operator)
    _, next_contract = _source(db, a, "source-a", version=2, source=source)
    _bind(db, a, source, next_contract, operator)
    bind = "INSERT INTO panadan_knowledge.contract_operator_scopes VALUES (%s,%s,%s,%s)"
    _reject(db, errors.ForeignKeyViolation, bind, (a, source, remote_contract, operator))
    _reject(db, errors.ForeignKeyViolation, bind, (a, second_source, second_contract, operator))
    _reject(db, errors.ForeignKeyViolation, bind, (a, source, contract, uuid4()))
    point = "UPDATE panadan_knowledge.sources SET current_contract_id=%s WHERE workspace_id=%s AND id=%s"
    _reject(db, errors.ForeignKeyViolation, point, (second_contract, a, source))
    db.execute(point, (next_contract, a, source))
    _reject(db, errors.CheckViolation, """INSERT INTO panadan_knowledge.sources
        (workspace_id,source_key,kind,label,connection_ref) VALUES (%s,'unsupported','web','Web','web')""", (a,))


def test_resource_versions_and_filtered_representation_enforce_lineage_and_types(migrated):
    db = migrated
    workspace = _workspace(db, "resource-a")
    member, retention, redaction = _policies(db, workspace)
    source, contract = _source(db, workspace, "calls")
    operator = _operator(db, workspace, source)
    excluded = _operator(db, workspace, source, "operator-b")
    _bind(db, workspace, source, contract, operator)
    schema, = db.execute("""INSERT INTO panadan_knowledge.attribute_schema_versions
        (workspace_id,schema_key,rev,json_schema,state) VALUES (%s,'call_metadata',1,%s,'approved') RETURNING id""",
        (workspace, Jsonb(call_metadata_schema()))).fetchone()
    first, second = (_resource(db, workspace, source, key) for key in ("1", "2"))
    prefix = (workspace, source, first, contract)
    suffix = (schema, retention, Jsonb({"duration_seconds": 25}))
    _reject(db, errors.ForeignKeyViolation, REVISION_INSERT, (*prefix, excluded, *suffix))
    _reject(db, errors.ForeignKeyViolation, REVISION_INSERT, (*prefix, operator, schema, redaction, suffix[-1]))
    for bad in ({"duration_seconds": 10.5}, {"duration_seconds": "25"}, {"transcript": "synthetic"}):
        _reject(db, errors.CheckViolation, REVISION_INSERT, (*prefix, operator, schema, retention, Jsonb(bad)))
    revision, = db.execute(REVISION_INSERT, (*prefix, operator, *suffix)).fetchone()
    point = """UPDATE panadan_knowledge.resources SET current_revision_id=%s,availability='active'
               WHERE workspace_id=%s AND id=%s"""
    _reject(db, errors.ForeignKeyViolation, point, (revision, workspace, second))
    db.execute(point, (revision, workspace, first))
    text = "نمونهٔ پالایش‌شده"
    digest = sha256(text.encode("utf-8")).hexdigest()
    _reject(db, errors.CheckViolation, REPRESENTATION_INSERT, (workspace, revision, redaction, text, "0" * 64))
    _reject(db, errors.ForeignKeyViolation, REPRESENTATION_INSERT, (workspace, revision, retention, text, digest))
    _reject(db, errors.ForeignKeyViolation, REPRESENTATION_INSERT, (workspace, uuid4(), redaction, text, digest))
    assert db.execute(REPRESENTATION_INSERT, (workspace, revision, redaction, text, digest)).fetchone()
    grant = """INSERT INTO panadan_knowledge.source_scope_grants
        (workspace_id,membership_id,grantor,scope_kind,source_id,operator_scope_id,capability)
        VALUES (%s,%s,%s,%s,%s,%s,'representation.read')"""
    _reject(db, errors.CheckViolation, grant, (workspace, member, member, "operator", source, None))
    _reject(db, errors.ForeignKeyViolation, grant, (workspace, member, member, "operator", source, uuid4()))
    db.execute(grant, (workspace, member, member, "source", source, None))
    _reject(db, errors.UniqueViolation, grant, (workspace, member, member, "source", source, None))
    db.execute(grant, (workspace, member, member, "operator", source, operator))
