"""Synthetic manual/scheduled admission and scope-safe population snapshots."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import psycopg
from psycopg import errors
import pytest

from server.knowledge_authorization import AccessDenied
from server.knowledge_configuration import ConfigurationChanged
from server.knowledge_run_admission import (
    create_schedule, request_run, request_scheduled_run, set_pipeline_enabled, set_schedule_enabled,
)
from test_knowledge_configuration import _objective, _pipeline, configuration
from test_knowledge_foundation import ROOT, _reject, db
from test_knowledge_resource_web import _seed_resource, resource_web, runtime
from tools.knowledge_preview_resources import END, START


M011 = ROOT / "database/migrations/011_knowledge_run_admission.sql"


@pytest.fixture
def admission(configuration):
    s, db, left, _, _, _ = configuration
    with db.transaction():
        _reject(db, errors.RaiseException, M011.read_text(encoding="utf-8"))
        db.execute("SELECT set_config('panadan.knowledge_migration_target','panadan_ci',true)")
        for _ in range(2):
            db.execute(M011.read_text(encoding="utf-8"))
    objective = _objective(configuration)
    pipeline = _pipeline(configuration,(objective.version_id,))
    return configuration, dict(workspace=left.workspace, member=s["owner"], enabled=True), pipeline, objective


def test_manual_admission_defaults_off_and_retry_keeps_original_population(admission):
    configuration, scope, pipeline, objective = admission
    _, db, left, _, _, _ = configuration
    definition = scope | {"pipeline_version":pipeline.version_id}
    key = uuid4()
    with pytest.raises(AccessDenied):
        request_run(db,**definition,request_key=key)
    set_pipeline_enabled(db,**definition,activate=True)
    missing = _seed_resource(db,left,102,transcript=None)
    outside = _seed_resource(db,left,501)
    db.execute("""UPDATE panadan_knowledge.resource_revisions SET event_at=%s WHERE resource_id=%s""",
               (END,outside))
    opened = request_run(db,**definition,request_key=key)
    assert (opened.measured,opened.ready,opened.excluded,opened.bounded) == (2,1,1,False)
    members = db.execute("""SELECT resource_id,resource_revision_id,eligibility,reason_code
        FROM panadan_knowledge.run_population_members WHERE run_id=%s ORDER BY eligibility""", (opened.run_id,)).fetchall()
    assert members[0][0] == missing and members[0][2:] == ("excluded","filtered_text_unavailable")
    assert all(row[0] != outside for row in members)
    manifest, denominator = db.execute("""SELECT r.manifest,c.source_eligible_count
        FROM panadan_knowledge.runs r JOIN panadan_knowledge.coverage_snapshots c
          ON c.workspace_id=r.workspace_id AND c.run_id=r.id WHERE r.id=%s""", (opened.run_id,)).fetchone()
    assert denominator is None and manifest["objectives"] == [str(objective.version_id)]
    assert manifest["start"] == START.isoformat() and manifest["end"] == END.isoformat()
    assert "text" not in manifest and manifest["operator"] == str(left.operator)
    _seed_resource(db,left,103)
    assert request_run(db,**definition,request_key=key) == replace(opened,replayed=True)
    next_run = request_run(db,**definition,request_key=uuid4())
    assert next_run.measured == 3 and next_run.ready == 2
    _reject(db,errors.RaiseException,"UPDATE panadan_knowledge.runs SET manifest='{}' WHERE id=%s",(opened.run_id,))
    _reject(db,errors.RaiseException,"DELETE FROM panadan_knowledge.run_population_members WHERE run_id=%s",(opened.run_id,))


def test_pipeline_revision_disables_activation_and_manual_key_cannot_be_reused(admission):
    config, scope, first, objective = admission
    _, db, _, _, _, _ = config
    params = scope | {"pipeline_version":first.version_id}
    set_pipeline_enabled(db,**params,activate=True)
    key = uuid4()
    original = request_run(db,**params,request_key=key)
    new = _pipeline(config,(objective.version_id,),expected_revision=1)
    fresh = scope | {"pipeline_version":new.version_id}
    with pytest.raises(AccessDenied):
        request_run(db,**fresh,request_key=uuid4())
    with pytest.raises(ConfigurationChanged):
        request_run(db,**fresh,request_key=key)
    assert request_run(db,**params,request_key=key) == replace(original,replayed=True)


def test_schedule_occurrence_is_default_off_deduplicated_and_advances_atomically(admission):
    config, scope, pipeline, _ = admission
    _, db, _, _, _, _ = config
    params = scope | {"pipeline_version":pipeline.version_id}
    due = db.execute("SELECT clock_timestamp()-interval '2 hours'").fetchone()[0]
    schedule = create_schedule(db,**params,key="hourly",first_due_at=due,cadence_seconds=3600)
    sched = scope | {"schedule_id":schedule}
    with pytest.raises(AccessDenied):
        set_schedule_enabled(db,**sched,activate=True)
    set_pipeline_enabled(db,**params,activate=True)
    with pytest.raises(AccessDenied):
        request_scheduled_run(db,**sched,occurrence_at=due)
    set_schedule_enabled(db,**sched,activate=True)
    with pytest.raises(AccessDenied):
        request_scheduled_run(db,**sched,occurrence_at=due+timedelta(seconds=1))
    admitted = request_scheduled_run(db,**sched,occurrence_at=due)
    assert request_scheduled_run(db,**sched,occurrence_at=due) == replace(admitted,replayed=True)
    assert db.execute("SELECT next_due_at FROM panadan_knowledge.schedules WHERE id=%s",(schedule,)).fetchone()[0] == due+timedelta(hours=1)
    assert db.execute("SELECT count(*) FROM panadan_knowledge.runs").fetchone() == (1,)
    assert request_scheduled_run(db,**sched,occurrence_at=due+timedelta(hours=1)).run_id != admitted.run_id


def test_bounded_population_and_current_scope_checked_before_manual_retry(admission):
    config, scope, _, objective = admission
    s, db, left, _, _, _ = config
    pipeline = _pipeline(config,(objective.version_id,),key="bounded",max_resources=1)
    _seed_resource(db,left,102,transcript=None)
    params = scope | {"pipeline_version":pipeline.version_id}
    set_pipeline_enabled(db,**params,activate=True)
    key = uuid4()
    admitted = request_run(db,**params,request_key=key)
    assert admitted.measured == 1 and admitted.bounded
    db.execute("""UPDATE panadan_knowledge.source_scope_grants SET revoked_at=clock_timestamp()
        WHERE workspace_id=%s AND membership_id=%s AND capability='representation.read'""",
        (left.workspace,s["owner"]))
    with pytest.raises(AccessDenied):
        request_run(db,**params,request_key=key)
    with pytest.raises(AccessDenied):
        request_run(db,**params,request_key=uuid4())
    assert db.execute("SELECT count(*) FROM panadan_knowledge.runs").fetchone() == (1,)


def test_concurrent_manual_retries_share_one_frozen_result(admission):
    config, scope, pipeline, _ = admission
    _, db, _, _, _, _ = config
    params = scope | {"pipeline_version":pipeline.version_id}
    set_pipeline_enabled(db,**params,activate=True)
    key = uuid4()

    def request():
        with psycopg.connect(db.info.dsn, password="synthetic_ci_password_only", connect_timeout=3) as separate:
            return request_run(separate,**params,request_key=key)

    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(request) for _ in range(2)]
        first, second = [job.result(timeout=20) for job in jobs]
    assert first.run_id == second.run_id and first.replayed != second.replayed
    assert db.execute("SELECT count(*) FROM panadan_knowledge.coverage_snapshots").fetchone() == (1,)
