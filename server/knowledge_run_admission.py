"""Explicit synthetic admission of scheduled and manual knowledge runs."""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .knowledge_authorization import AccessDenied
from .knowledge_call_contract import require_synthetic_call_contract
from .knowledge_call_source import _utc
from .knowledge_configuration import ConfigurationChanged, _identifier, _pipeline_authority, _require_member, _require_setup
from .knowledge_objectives import checked_key


@dataclass(frozen=True, slots=True)
class AdmittedRun:
    run_id: UUID
    measured: int
    ready: int
    excluded: int
    bounded: bool
    replayed: bool = False


@contextmanager
def _admission(conn, workspace, member, enabled):
    with conn.transaction(), conn.cursor(row_factory=dict_row) as db:
        _require_setup(conn, enabled)
        db.execute("SET LOCAL TIME ZONE 'UTC'")
        epoch = _require_member(db,workspace,member,exclusive=True)
        yield db, epoch


def _scope(db, workspace, pipeline_version, member, *, active, current=True):
    _identifier(pipeline_version)
    pipeline = db.execute("""SELECT p.id AS pipeline_id,p.enabled,p.current_version_id,v.max_resources,v.event_start,v.event_end,
        v.preprocessing_version,v.processor,ps.source_id,ps.contract_id,ps.operator_scope_id,c.adapter_version,
        c.state AS contract_state,c.contract,s.kind
      FROM panadan_knowledge.pipeline_versions v JOIN panadan_knowledge.pipelines p
        ON p.workspace_id=v.workspace_id AND p.id=v.pipeline_id
      JOIN panadan_knowledge.pipeline_sources ps ON ps.workspace_id=v.workspace_id AND ps.pipeline_version_id=v.id
      JOIN panadan_knowledge.sources s ON s.workspace_id=v.workspace_id AND s.id=ps.source_id
        AND s.current_contract_id=ps.contract_id AND s.state='active'
      JOIN panadan_knowledge.source_contract_versions c ON c.workspace_id=v.workspace_id AND c.id=ps.contract_id
      JOIN panadan_knowledge.operator_scopes o ON o.workspace_id=v.workspace_id AND o.id=ps.operator_scope_id
        AND o.state='active'
      WHERE v.workspace_id=%s AND v.id=%s AND v.state='active' FOR SHARE OF v,s,c,o""",
      (workspace,pipeline_version)).fetchone()
    if (pipeline is None or (active and not pipeline["enabled"])
            or (current and pipeline["current_version_id"] != pipeline_version)):
        raise AccessDenied("Pipeline run scope unavailable")
    require_synthetic_call_contract(kind=pipeline["kind"],adapter=pipeline["adapter_version"],
                                    state=pipeline["contract_state"],contract=pipeline["contract"])
    pipeline["authority_until"] = _pipeline_authority(db,workspace,member,pipeline["source_id"],pipeline["operator_scope_id"])
    versions = db.execute("""SELECT b.objective_version_id,v.state,p.state AS policy_state
        FROM panadan_knowledge.pipeline_objectives b
        JOIN panadan_knowledge.objective_versions v ON v.workspace_id=b.workspace_id AND v.id=b.objective_version_id
        JOIN panadan_knowledge.policy_versions p ON p.workspace_id=v.workspace_id AND p.id=v.validation_policy_id
        WHERE b.workspace_id=%s AND b.pipeline_version_id=%s ORDER BY b.stage_order FOR SHARE OF v,p""",
        (workspace,pipeline_version)).fetchall()
    if not versions or any(v["state"] != "active" or v["policy_state"] != "approved" for v in versions):
        raise AccessDenied("Pipeline objective versions unavailable")
    pipeline["objectives"] = [row["objective_version_id"] for row in versions]
    return pipeline


def _check_timeout(db, scope):
    expiry = scope["authority_until"]
    if expiry is not None and db.execute("SELECT clock_timestamp() AS instant").fetchone()["instant"] >= expiry:
        raise AccessDenied("Pipeline run scope unavailable")


def set_pipeline_enabled(conn, *, workspace, member, pipeline_version, activate, enabled=False):
    if type(activate) is not bool:
        raise ValueError("Pipeline activation requires a boolean")
    with _admission(conn,workspace,member,enabled) as (db,_):
        scope = _scope(db,workspace,pipeline_version,member,active=False)
        db.execute("UPDATE panadan_knowledge.pipelines SET enabled=%s WHERE workspace_id=%s AND id=%s",
                   (activate,workspace,scope["pipeline_id"]))
        _check_timeout(db,scope)


def create_schedule(conn, *, workspace, member, pipeline_version, key, first_due_at, cadence_seconds, enabled=False):
    checked_key(key)
    due = _utc(first_due_at)
    if type(cadence_seconds) is not int or not 900 <= cadence_seconds <= 604800:
        raise ValueError("Schedule cadence must be between fifteen minutes and one week")
    with _admission(conn,workspace,member,enabled) as (db,_):
        scope = _scope(db,workspace,pipeline_version,member,active=False)
        row = db.execute("""INSERT INTO panadan_knowledge.schedules
            (workspace_id,schedule_key,pipeline_version_id,requested_by,cadence_seconds,first_due_at,next_due_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (workspace_id,pipeline_version_id,schedule_key) DO NOTHING
            RETURNING id""", (workspace,key,pipeline_version,member,cadence_seconds,due,due)).fetchone()
        if row is None:
            raise ConfigurationChanged("Schedule key already exists")
        _check_timeout(db,scope)
        return row["id"]


def _schedule(db, workspace, member, schedule_id):
    _identifier(schedule_id)
    schedule = db.execute("""SELECT pipeline_version_id,cadence_seconds,next_due_at,enabled
        FROM panadan_knowledge.schedules WHERE workspace_id=%s AND id=%s AND requested_by=%s FOR UPDATE""",
        (workspace,schedule_id,member)).fetchone()
    if schedule is None:
        raise AccessDenied("Schedule unavailable")
    return schedule


def set_schedule_enabled(conn, *, workspace, member, schedule_id, activate, enabled=False):
    if type(activate) is not bool:
        raise ValueError("Schedule activation requires a boolean")
    with _admission(conn,workspace,member,enabled) as (db,_):
        schedule = _schedule(db,workspace,member,schedule_id)
        scope = _scope(db,workspace,schedule["pipeline_version_id"],member,active=activate)
        db.execute("UPDATE panadan_knowledge.schedules SET enabled=%s WHERE workspace_id=%s AND id=%s",
                   (activate,workspace,schedule_id))
        _check_timeout(db,scope)


def _existing(db, workspace, *, request_key, schedule_id, occurrence):
    return db.execute("""SELECT r.id,r.pipeline_version_id,r.requested_by,c.measured_count,c.ready_count,c.excluded_count,c.bounded
        FROM panadan_knowledge.runs r JOIN panadan_knowledge.coverage_snapshots c
          ON c.workspace_id=r.workspace_id AND c.run_id=r.id AND c.stage='admission'
        WHERE r.workspace_id=%s AND (r.request_key=%s OR (r.schedule_id=%s AND r.occurrence_at=%s))""",
        (workspace,request_key,schedule_id,occurrence)).fetchone()


def _freeze(db, workspace, member, pipeline_version, scope, epoch, *, request_key=None, schedule_id=None, occurrence=None):
    manifest = {
        "version": 1, "pipeline_version": str(pipeline_version),
        "objectives": [str(item) for item in scope["objectives"]],
        "source": str(scope["source_id"]), "contract": str(scope["contract_id"]),
        "operator": str(scope["operator_scope_id"]), "start": scope["event_start"].isoformat(),
        "end": scope["event_end"].isoformat(), "preprocessing": scope["preprocessing_version"],
        "processor": scope["processor"], "max_resources": scope["max_resources"], "policy_epoch": epoch,
    }
    run = db.execute("""INSERT INTO panadan_knowledge.runs
        (workspace_id,pipeline_version_id,requested_by,trigger_kind,request_key,schedule_id,occurrence_at,policy_epoch,manifest)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (workspace,pipeline_version,member,"manual" if request_key else "schedule",
         request_key,schedule_id,occurrence,epoch,Jsonb(manifest))).fetchone()["id"]
    limit = scope["max_resources"]
    population = db.execute("""SELECT r.id,v.id AS revision,v.availability AS revision_state,r.availability,
        filtered.id AS representation
        FROM panadan_knowledge.resources r JOIN panadan_knowledge.resource_revisions v
          ON v.workspace_id=r.workspace_id AND v.id=r.current_revision_id
        LEFT JOIN LATERAL (
          SELECT p.id FROM panadan_knowledge.representations p
          WHERE p.workspace_id=v.workspace_id AND p.resource_revision_id=v.id AND p.kind='filtered_transcript'
            AND p.availability='active' AND (p.expires_at IS NULL OR p.expires_at>clock_timestamp())
          ORDER BY p.representation_rev DESC LIMIT 1
        ) filtered ON true
        WHERE r.workspace_id=%s AND r.source_id=%s AND v.contract_id=%s AND v.operator_scope_id=%s
          AND v.event_at>=%s AND v.event_at<%s ORDER BY v.event_at,r.id LIMIT %s""",
        (workspace,scope["source_id"],scope["contract_id"],scope["operator_scope_id"],
         scope["event_start"],scope["event_end"],limit+1)).fetchall()
    measured = min(len(population),limit)
    ready = 0
    for entry in population[:limit]:
        reason = None
        if entry["availability"] != "active" or entry["revision_state"] != "active":
            reason = "resource_unavailable"
        elif entry["representation"] is None:
            reason = "filtered_text_unavailable"
        ready += reason is None
        db.execute("""INSERT INTO panadan_knowledge.run_population_members
            (workspace_id,run_id,resource_id,resource_revision_id,representation_id,eligibility,reason_code)
            VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (workspace,run,entry["id"],entry["revision"],None if reason else entry["representation"],
             "excluded" if reason else "ready",reason))
    bounded = len(population) > limit
    db.execute("""INSERT INTO panadan_knowledge.coverage_snapshots
        (workspace_id,run_id,stage,measured_count,ready_count,excluded_count,bounded)
        VALUES (%s,%s,'admission',%s,%s,%s,%s)""", (workspace,run,measured,ready,measured-ready,bounded))
    _check_timeout(db,scope)
    return AdmittedRun(run,measured,ready,measured-ready,bounded)


def _replay(existing, member, pipeline_version):
    if existing["requested_by"] != member:
        raise AccessDenied("Run scope unavailable")
    if existing["pipeline_version_id"] != pipeline_version:
        raise ConfigurationChanged("Run identity already belongs to a different request")
    return AdmittedRun(existing["id"],existing["measured_count"],existing["ready_count"],
                       existing["excluded_count"],existing["bounded"],replayed=True)


def request_run(conn, *, workspace, member, pipeline_version, request_key, enabled=False):
    _identifier(request_key)
    with _admission(conn,workspace,member,enabled) as (db,epoch):
        existing = _existing(db,workspace,request_key=request_key,schedule_id=None,occurrence=None)
        scope = _scope(db,workspace,pipeline_version,member,active=existing is None,current=existing is None)
        if existing:
            _check_timeout(db,scope)
            return _replay(existing,member,pipeline_version)
        return _freeze(db,workspace,member,pipeline_version,scope,epoch,request_key=request_key)


def request_scheduled_run(conn, *, workspace, member, schedule_id, occurrence_at, enabled=False):
    occurrence = _utc(occurrence_at)
    with _admission(conn,workspace,member,enabled) as (db,epoch):
        schedule = _schedule(db,workspace,member,schedule_id)
        version = schedule["pipeline_version_id"]
        existing = _existing(db,workspace,request_key=None,schedule_id=schedule_id,occurrence=occurrence)
        scope = _scope(db,workspace,version,member,active=existing is None,current=existing is None)
        if existing:
            _check_timeout(db,scope)
            return _replay(existing,member,version)
        now = db.execute("SELECT clock_timestamp() AS instant").fetchone()["instant"]
        if not schedule["enabled"] or occurrence != schedule["next_due_at"] or occurrence > now:
            raise AccessDenied("Schedule occurrence unavailable")
        result = _freeze(db,workspace,member,version,scope,epoch,schedule_id=schedule_id,occurrence=occurrence)
        db.execute("UPDATE panadan_knowledge.schedules SET next_due_at=%s WHERE workspace_id=%s AND id=%s",
                   (occurrence+timedelta(seconds=schedule["cadence_seconds"]),workspace,schedule_id))
        return result
