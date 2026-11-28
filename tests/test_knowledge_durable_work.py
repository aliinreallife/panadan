"""M03.3 task leases, durable retries and run controls with real PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import psycopg
from psycopg import errors
import pytest

from server.knowledge_authorization import AccessDenied
from server.knowledge_durable_work import StaleLease, claim_work, control_run, finish_work, reconcile_run, start_run
from server.knowledge_run_admission import request_run, set_pipeline_enabled
from test_knowledge_configuration import configuration
from test_knowledge_foundation import ROOT, _reject, db
from test_knowledge_resource_web import _seed_resource, resource_web, runtime
from test_knowledge_run_admission import admission
from tools.knowledge_preview_resources import END


M012 = ROOT / "database/migrations/012_knowledge_durable_work.sql"


@pytest.fixture
def work(admission):
    config, scope, pipeline, _ = admission
    _, db, left, _, _, _ = config
    with db.transaction():
        _reject(db,errors.RaiseException,M012.read_text(encoding="utf-8"))
        db.execute("SELECT set_config('panadan.knowledge_migration_target','panadan_ci',true)")
        for _ in range(2):
            db.execute(M012.read_text(encoding="utf-8"))
    pipeline_args = scope | {"pipeline_version":pipeline.version_id}
    set_pipeline_enabled(db,**pipeline_args,activate=True)

    def admit():
        run = request_run(db,**pipeline_args,request_key=uuid4())
        return scope | {"run_id":run.run_id}

    return db, left, admit


def test_single_effect_and_successful_run_resolution(work):
    db, _, admit = work
    args = admit()
    assert claim_work(db,**args,worker_id=uuid4()) is None
    start_run(db,**args)
    start_run(db,**args)
    lease = claim_work(db,**args,worker_id=uuid4())
    assert lease.fence == 1
    assert finish_work(db,**args,lease=lease) == "succeeded"
    with pytest.raises(StaleLease):
        finish_work(db,**args,lease=lease)
    assert db.execute("SELECT count(*) FROM panadan_knowledge.fixture_work_results").fetchone() == (1,)
    assert reconcile_run(db,**args) == "succeeded"
    assert reconcile_run(db,**args) == "succeeded"


def test_expired_worker_is_fenced_and_retry_exhaustion_is_terminal(work):
    db, _, admit = work
    args = admit()
    start_run(db,**args,max_attempts=2)
    first = claim_work(db,**args,worker_id=uuid4())
    db.execute("UPDATE panadan_knowledge.work_items SET lease_until=clock_timestamp()-interval '1 second'")
    assert claim_work(db,**args,worker_id=uuid4()) is None
    with pytest.raises(StaleLease):
        finish_work(db,**args,lease=first)
    assert db.execute("SELECT state,outcome_code FROM panadan_knowledge.work_items").fetchone() == ("retry_wait","lease_expired")
    db.execute("UPDATE panadan_knowledge.work_items SET available_at=clock_timestamp()-interval '1 second'")
    second = claim_work(db,**args,worker_id=uuid4())
    assert second.item_id == first.item_id and second.fence == first.fence+1
    with pytest.raises(StaleLease):
        finish_work(db,**args,lease=first)
    assert finish_work(db,**args,lease=second,outcome="retryable_failure") == "failed"
    assert claim_work(db,**args,worker_id=uuid4()) is None
    assert reconcile_run(db,**args) == "failed"
    assert db.execute("SELECT outcome FROM panadan_knowledge.work_attempts ORDER BY attempt_no").fetchall() == [
        ("lease_expired",),("failed",),
    ]


def test_pause_resume_and_cancel_invalidate_previous_claims(work):
    db, _, admit = work
    args = admit()
    start_run(db,**args)
    first = claim_work(db,**args,worker_id=uuid4())
    assert control_run(db,**args,action="pause") == "paused"
    assert claim_work(db,**args,worker_id=uuid4()) is None
    with pytest.raises(StaleLease):
        finish_work(db,**args,lease=first)
    assert control_run(db,**args,action="resume") == "running"
    second = claim_work(db,**args,worker_id=uuid4())
    assert second.fence == first.fence+1
    assert control_run(db,**args,action="cancel") == "canceled"
    with pytest.raises(StaleLease):
        finish_work(db,**args,lease=second)
    assert reconcile_run(db,**args) == "canceled"
    assert db.execute("SELECT outcome FROM panadan_knowledge.work_attempts ORDER BY attempt_no").fetchall() == [
        ("paused",),("canceled",),
    ]


def test_current_representation_is_rechecked_before_any_effect(work):
    db, left, admit = work
    args = admit()
    start_run(db,**args)
    lease = claim_work(db,**args,worker_id=uuid4())
    db.execute("UPDATE panadan_knowledge.resources SET availability='restricted' WHERE workspace_id=%s",(left.workspace,))
    assert finish_work(db,**args,lease=lease) == "blocked_policy"
    assert db.execute("SELECT count(*) FROM panadan_knowledge.fixture_work_results").fetchone() == (0,)
    assert reconcile_run(db,**args) == "blocked_policy"


def test_scope_revocation_blocks_work_but_allows_owner_to_cancel(work):
    db, _, admit = work
    args = admit()
    start_run(db,**args)
    lease = claim_work(db,**args,worker_id=uuid4())
    db.execute("""UPDATE panadan_knowledge.source_scope_grants SET revoked_at=clock_timestamp()
        WHERE workspace_id=%s AND membership_id=%s AND capability='representation.read'""",
        (args["workspace"],args["member"]))
    with pytest.raises(AccessDenied):
        finish_work(db,**args,lease=lease)
    assert control_run(db,**args,action="cancel") == "canceled"
    assert db.execute("SELECT count(*) FROM panadan_knowledge.fixture_work_results").fetchone() == (0,)


def test_parallel_workers_claim_distinct_tasks(work):
    db, left, admit = work
    _seed_resource(db,left,102)
    args = admit()
    start_run(db,**args)
    def claim():
        with psycopg.connect(db.info.dsn,password="synthetic_ci_password_only",connect_timeout=3) as separate:
            return claim_work(separate,**args,worker_id=uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(claim) for _ in range(2)]
        leases = [job.result(timeout=20) for job in jobs]
    assert len({lease.item_id for lease in leases}) == 2
    for lease in leases:
        assert finish_work(db,**args,lease=lease) == "succeeded"
    assert reconcile_run(db,**args) == "succeeded"


def test_fresh_priority_and_aging_prevent_backfill_from_starving(work):
    db, left, admit = work
    for call in (102,103):
        resource = _seed_resource(db,left,call)
        db.execute("UPDATE panadan_knowledge.resource_revisions SET event_at=%s WHERE resource_id=%s",
                   (END-timedelta(hours=1),resource))
    args = admit()
    start_run(db,**args)
    first = claim_work(db,**args,worker_id=uuid4())
    assert db.execute("SELECT priority_class FROM panadan_knowledge.work_items WHERE id=%s",(first.item_id,)).fetchone() == ("fresh",)
    db.execute("UPDATE panadan_knowledge.work_items SET available_at=clock_timestamp()-interval '1 minute' WHERE priority_class='backfill'")
    next_item = claim_work(db,**args,worker_id=uuid4())
    assert db.execute("SELECT priority_class FROM panadan_knowledge.work_items WHERE id=%s",(next_item.item_id,)).fetchone() == ("backfill",)
