"""Explicit synthetic setup for versioned objectives and pipeline bindings."""

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from psycopg import sql
from psycopg.rows import dict_row, tuple_row
from psycopg.types.json import Jsonb

from .knowledge_authorization import AccessDenied
from .knowledge_call_contract import require_synthetic_call_contract
from .knowledge_call_privacy import REDACTION_VERSION
from .knowledge_call_source import MAX_SCOPE_WINDOW, _utc
from .knowledge_objectives import (
    CATALOG_REVISION, FILTERED_CALL, TEMPLATES, checked_key, checked_text, resolve_objective, template_definition,
)


PROCESSOR = "synthetic-deterministic-v1"


class ConfigurationChanged(RuntimeError):
    """The caller needs to reload the current revision before editing again."""


@dataclass(frozen=True, slots=True)
class DefinitionVersion:
    definition_id: UUID
    version_id: UUID
    revision: int


def _require_setup(conn, enabled):
    if (enabled is not True or conn.info.host != "127.0.0.1" or conn.info.dbname != "panadan_ci"
            or conn.info.user != "panadan_ci" or conn.info.server_version // 10000 != 18):
        raise AccessDenied("Synthetic configuration setup unavailable")
    with conn.cursor(row_factory=tuple_row) as db:
        if db.execute("SELECT current_user=session_user").fetchone() != (True,):
            raise AccessDenied("Synthetic configuration setup unavailable")


def _identifier(value):
    if type(value) is not UUID or not value.int:
        raise ValueError("Missing configuration identifier")
    return value


def _require_member(db, workspace, member, *, exclusive=False):
    _identifier(workspace)
    _identifier(member)
    lock = " FOR UPDATE OF w FOR SHARE OF m,p" if exclusive else " FOR SHARE OF w,m,p"
    present = db.execute("""SELECT w.policy_epoch FROM panadan_knowledge.workspaces w
        JOIN panadan_knowledge.memberships m ON m.workspace_id=w.id
        JOIN panadan_knowledge.principals p ON p.id=m.principal_id
        WHERE w.id=%s AND w.state='active' AND m.id=%s AND m.state='active' AND m.revoked_at IS NULL
          AND p.kind='human' AND p.state='active'""" + lock, (workspace,member)).fetchone()
    if present is None:
        raise AccessDenied("Synthetic configuration scope unavailable")
    return present["policy_epoch"]


def install_objective_catalog(conn, *, enabled=False):
    with conn.transaction(), conn.cursor(row_factory=dict_row) as db:
        _require_setup(conn, enabled)
        for template in TEMPLATES:
            definition = template_definition(template)
            db.execute("""INSERT INTO panadan_knowledge.objective_templates
                (template_key,rev,label,input_kind,definition) VALUES (%s,%s,%s,%s,%s)
                ON CONFLICT (template_key,rev) DO NOTHING""",
                (template.key,CATALOG_REVISION,template.name,template.input_kind,Jsonb(definition)))
            published = db.execute("""SELECT label,input_kind,definition FROM panadan_knowledge.objective_templates
                WHERE template_key=%s AND rev=%s""", (template.key,CATALOG_REVISION)).fetchone()
            if published != {"label": template.name, "input_kind": template.input_kind, "definition": definition}:
                raise ConfigurationChanged("Published template differs from the reviewed catalog")


def _parent(db, workspace, key, expected_revision, *, pipeline, pipeline_member=None):
    table, version_table, key_column = (
        ("pipelines","pipeline_versions","pipeline_key") if pipeline
        else ("objectives","objective_versions","objective_key")
    )
    current_table = sql.Identifier("panadan_knowledge", table)
    version_table = sql.Identifier("panadan_knowledge", version_table)
    key_column = sql.Identifier(key_column)
    db.execute(sql.SQL("""INSERT INTO {} (workspace_id,{}) VALUES (%s,%s)
        ON CONFLICT (workspace_id,{}) DO NOTHING""").format(current_table,key_column,key_column), (workspace,key))
    parent = db.execute(sql.SQL("""SELECT p.id,v.rev FROM {} p LEFT JOIN {} v
        ON v.workspace_id=p.workspace_id AND v.id=p.current_version_id
        WHERE p.workspace_id=%s AND p.{}=%s FOR UPDATE OF p""").format(current_table,version_table,key_column),
        (workspace,key)).fetchone()
    current = parent["rev"] or 0
    previous_deadline = None
    if current and pipeline_member is not None:
        previous = db.execute("""SELECT b.source_id,b.operator_scope_id
            FROM panadan_knowledge.pipelines p JOIN panadan_knowledge.pipeline_sources b
              ON b.workspace_id=p.workspace_id AND b.pipeline_version_id=p.current_version_id
            WHERE p.workspace_id=%s AND p.id=%s""",(workspace,parent["id"])).fetchone()
        if previous is None:
            raise AccessDenied("Pipeline source scope unavailable")
        previous_deadline = _pipeline_authority(db,workspace,pipeline_member,previous["source_id"],previous["operator_scope_id"])
    if type(expected_revision) is not int or expected_revision != current:
        raise ConfigurationChanged("Configuration revision changed")
    return parent["id"], current + 1, previous_deadline


def _pipeline_authority(db, workspace, member, source, operator):
    grant = db.execute("""SELECT valid_until FROM panadan_knowledge.source_scope_grants
        WHERE workspace_id=%s AND source_id=%s AND membership_id=%s
          AND (scope_kind='source' OR operator_scope_id=%s) AND capability='representation.read'
          AND revoked_at IS NULL AND valid_from<=clock_timestamp()
          AND (valid_until IS NULL OR valid_until>clock_timestamp())
        ORDER BY valid_until DESC NULLS FIRST,id LIMIT 1 FOR SHARE""",
        (workspace, source, member, operator)).fetchone()
    role = db.execute("""SELECT m.valid_until FROM panadan_knowledge.membership_roles m
        JOIN panadan_knowledge.role_versions r ON r.workspace_id=m.workspace_id AND r.id=m.role_version_id
        WHERE m.workspace_id=%s AND m.membership_id=%s AND m.revoked_at IS NULL
          AND (m.valid_until IS NULL OR m.valid_until>clock_timestamp())
          AND r.state='active' AND r.capability_set ? 'representation.read'
        ORDER BY m.valid_until DESC NULLS FIRST,m.id LIMIT 1 FOR SHARE OF m,r""",
        (workspace,member)).fetchone()
    if grant is None or role is None:
        raise AccessDenied("Pipeline source scope unavailable")
    return min((row["valid_until"] for row in (grant,role) if row["valid_until"] is not None), default=None)


def save_objective(conn, *, workspace, member, key, label, purpose, validation_policy, expected_revision,
                   template_key=None, fields=None, context=None, enabled=False):
    with conn.transaction(), conn.cursor(row_factory=dict_row) as db:
        _require_setup(conn, enabled)
        _require_member(db, workspace, member)
        return _publish_objective(db,workspace,key,label,purpose,validation_policy,expected_revision,
                                  template_key=template_key,fields=fields,context=context)


def _approved_validation(db, workspace, policy):
    _identifier(policy)
    allowed = db.execute("""SELECT 1 FROM panadan_knowledge.policy_versions
        WHERE workspace_id=%s AND id=%s AND kind='validation' AND state='approved' FOR SHARE""",
        (workspace,policy)).fetchone()
    if allowed is None:
        raise AccessDenied("Synthetic validation policy unavailable")


def _write_objective(db, workspace, objective, rev, label, purpose, input_kind, template, schemas, validation):
    version = db.execute("""INSERT INTO panadan_knowledge.objective_versions
        (workspace_id,objective_id,template_id,rev,label,purpose,input_kind,output_schema_id,context_schema_id,validation_policy_id)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (workspace,objective,template,rev,label,purpose,input_kind,*schemas,validation)).fetchone()["id"]
    db.execute("UPDATE panadan_knowledge.objectives SET current_version_id=%s WHERE workspace_id=%s AND id=%s",
               (version,workspace,objective))
    return DefinitionVersion(objective,version,rev)


def _publish_objective(db, workspace, key, label, purpose, validation_policy, expected_revision,
                       *, template_key=None, fields=None, context=None):
    key = checked_key(key)
    label = checked_text(label,limit=160)
    purpose = checked_text(purpose,limit=1200)
    input_kind, output, context_schema = resolve_objective(template_key=template_key,fields=fields,context=context)
    _approved_validation(db,workspace,validation_policy)
    template_id = None
    if template_key:
        template = db.execute("""SELECT id FROM panadan_knowledge.objective_templates
            WHERE template_key=%s AND rev=%s AND input_kind=%s AND state='active' FOR SHARE""",
            (template_key,CATALOG_REVISION,input_kind)).fetchone()
        if template is None:
            raise AccessDenied("Objective template unavailable")
        template_id = template["id"]
    objective, rev, _ = _parent(db,workspace,key,expected_revision,pipeline=False)
    schema_ids = []
    for prefix, schema in (("output",output),("context",context_schema)):
        row = db.execute("""INSERT INTO panadan_knowledge.attribute_schema_versions
            (workspace_id,schema_key,rev,json_schema,state) VALUES (%s,%s,%s,%s,'approved') RETURNING id""",
            (workspace,f"{prefix}.{key}",rev,Jsonb(schema))).fetchone()
        schema_ids.append(row["id"])
    return _write_objective(db,workspace,objective,rev,label,purpose,input_kind,template_id,schema_ids,validation_policy)


def _revise_objective(db, workspace, key, label, purpose, expected_revision):
    key = checked_key(key)
    label = checked_text(label,limit=160)
    purpose = checked_text(purpose,limit=1200)
    if type(expected_revision) is not int or expected_revision<1:
        raise ValueError("Objective revision required")
    objective, rev, _ = _parent(db,workspace,key,expected_revision,pipeline=False)
    previous = db.execute("""SELECT template_id,input_kind,output_schema_id,context_schema_id,validation_policy_id
        FROM panadan_knowledge.objective_versions WHERE workspace_id=%s AND objective_id=%s AND rev=%s AND state='active'""",
        (workspace,objective,expected_revision)).fetchone()
    if previous is None:
        raise AccessDenied("Objective version unavailable")
    validation = previous["validation_policy_id"]
    _approved_validation(db,workspace,validation)
    schemas = (previous["output_schema_id"],previous["context_schema_id"])
    return _write_objective(db,workspace,objective,rev,label,purpose,previous["input_kind"],
                            previous["template_id"],schemas,validation)


def save_pipeline(conn, *, workspace, member, key, label, objectives, source, contract, operator,
                  event_start, event_end, max_resources, expected_revision, enabled=False):
    with conn.transaction(), conn.cursor(row_factory=dict_row) as db:
        _require_setup(conn,enabled)
        _require_member(db,workspace,member)
        return _write_pipeline(db,workspace,member,key,label,objectives,source,contract,operator,
                               event_start,event_end,max_resources,expected_revision)


def _publish_checkpoint_pipeline(db, workspace, member, *, checkpoint, key, label, objectives,
                                 max_resources, expected_revision):
    selected = db.execute("""SELECT source_id,contract_id,operator_scope_id,event_start,event_end
        FROM panadan_knowledge.sync_checkpoints WHERE workspace_id=%s AND id=%s FOR SHARE""",
        (workspace,_identifier(checkpoint))).fetchone()
    if selected is None:
        raise AccessDenied("Pipeline source scope unavailable")
    return _write_pipeline(db,workspace,member,key,label,objectives,selected["source_id"],
                           selected["contract_id"],selected["operator_scope_id"],selected["event_start"],
                           selected["event_end"],max_resources,expected_revision,verify_previous=True)


def _write_pipeline(db, workspace, member, key, label, objectives, source, contract, operator,
                    event_start, event_end, max_resources, expected_revision, *, verify_previous=False):
    key = checked_key(key)
    label = checked_text(label,limit=160)
    start, end = map(_utc,(event_start,event_end))
    if not timedelta(0) < end - start <= MAX_SCOPE_WINDOW:
        raise ValueError("Pipeline scope must be positive and at most 30 days")
    if type(max_resources) is not int or not 1 <= max_resources <= 500:
        raise ValueError("Invalid pipeline resource limit")
    if type(objectives) is not tuple or not 1 <= len(objectives) <= 6:
        raise ValueError("Choose 1–6 compatible objective versions")
    for item in (source,contract,operator,*objectives):
        _identifier(item)
    if len(set(objectives)) != len(objectives):
        raise ValueError("Duplicate objective version")
    selected = db.execute("""SELECT s.kind,c.adapter_version,c.state,c.contract
        FROM panadan_knowledge.sources s JOIN panadan_knowledge.source_contract_versions c
          ON c.workspace_id=s.workspace_id AND c.source_id=s.id AND c.id=s.current_contract_id
        JOIN panadan_knowledge.contract_operator_scopes b ON b.workspace_id=s.workspace_id AND b.source_id=s.id
          AND b.contract_id=c.id
        JOIN panadan_knowledge.operator_scopes o ON o.workspace_id=s.workspace_id AND o.id=b.operator_scope_id
          AND o.state='active'
        WHERE s.workspace_id=%s AND s.id=%s AND s.state='active' AND c.id=%s AND o.id=%s
          AND EXISTS (SELECT 1 FROM panadan_knowledge.sync_checkpoints p WHERE p.workspace_id=s.workspace_id
            AND p.source_id=s.id AND p.contract_id=c.id AND p.operator_scope_id=o.id
            AND p.event_start<=%s AND p.event_end>=%s)
        FOR SHARE OF s,c,b,o""", (workspace,source,contract,operator,start,end)).fetchone()
    if selected is None:
        raise AccessDenied("Pipeline source scope unavailable")
    authority_deadline = _pipeline_authority(db,workspace,member,source,operator)
    require_synthetic_call_contract(kind=selected["kind"],adapter=selected["adapter_version"],
                                    state=selected["state"],contract=selected["contract"])
    available = db.execute("""SELECT v.id FROM panadan_knowledge.objective_versions v
        JOIN panadan_knowledge.objectives o ON o.workspace_id=v.workspace_id AND o.current_version_id=v.id
        JOIN panadan_knowledge.policy_versions p ON p.workspace_id=v.workspace_id AND p.id=v.validation_policy_id
        WHERE v.workspace_id=%s AND v.id=ANY(%s) AND v.input_kind=%s AND v.state='active' AND p.state='approved'
        FOR SHARE OF v,o,p""", (workspace,list(objectives),FILTERED_CALL)).fetchall()
    if {row["id"] for row in available} != set(objectives):
        raise AccessDenied("Pipeline objective versions unavailable")
    pipeline, rev, previous_deadline = _parent(db,workspace,key,expected_revision,pipeline=True,
                                               pipeline_member=member if verify_previous else None)
    authority_deadline = min((x for x in (previous_deadline,authority_deadline) if x is not None),default=None)
    version = db.execute("""INSERT INTO panadan_knowledge.pipeline_versions
        (workspace_id,pipeline_id,rev,label,preprocessing_version,processor,max_resources,event_start,event_end)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (workspace,pipeline,rev,label,REDACTION_VERSION,PROCESSOR,max_resources,start,end)).fetchone()["id"]
    for order, objective in enumerate(objectives,1):
        db.execute("""INSERT INTO panadan_knowledge.pipeline_objectives
            (workspace_id,pipeline_version_id,objective_version_id,stage_order) VALUES (%s,%s,%s,%s)""",
            (workspace,version,objective,order))
    db.execute("""INSERT INTO panadan_knowledge.pipeline_sources
        (workspace_id,pipeline_version_id,source_id,contract_id,operator_scope_id) VALUES (%s,%s,%s,%s,%s)""",
        (workspace,version,source,contract,operator))
    db.execute("UPDATE panadan_knowledge.pipeline_versions SET state='active' WHERE workspace_id=%s AND id=%s",(workspace,version))
    db.execute("UPDATE panadan_knowledge.pipelines SET current_version_id=%s,enabled=false WHERE workspace_id=%s AND id=%s",
               (version,workspace,pipeline))
    if authority_deadline is not None and db.execute("SELECT clock_timestamp() AS instant").fetchone()["instant"] >= authority_deadline:
        raise AccessDenied("Pipeline source scope unavailable")
    return DefinitionVersion(pipeline,version,rev)
