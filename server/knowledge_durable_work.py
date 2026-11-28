"""Bounded synthetic work claims, fenced effects and resumable lifecycle."""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from psycopg.rows import dict_row

from .knowledge_authorization import AccessDenied
from .knowledge_configuration import PROCESSOR, _identifier, _require_member, _require_setup
from .knowledge_run_admission import _check_timeout, _scope


class StaleLease(RuntimeError):
    """The attempted effect no longer owns this item."""


@dataclass(frozen=True, slots=True)
class WorkLease:
    item_id: UUID
    worker_id: UUID
    fence: int
    expires_at: datetime


@contextmanager
def _run_transaction(conn, workspace, member, run_id, enabled, *, exclusive=False, authorize_source=True):
    _identifier(run_id)
    with conn.transaction(), conn.cursor(row_factory=dict_row) as db:
        _require_setup(conn,enabled)
        epoch = _require_member(db,workspace,member)
        lock = " FOR UPDATE" if exclusive else " FOR SHARE"
        run = db.execute("""SELECT pipeline_version_id,state,policy_epoch,started_at
            FROM panadan_knowledge.runs WHERE workspace_id=%s AND requested_by=%s AND id=%s""" + lock,
            (workspace,member,run_id)).fetchone()
        if run is None:
            raise AccessDenied("Run scope unavailable")
        scope = None
        if authorize_source:
            if epoch != run["policy_epoch"]:
                raise AccessDenied("Run scope changed")
            scope = _scope(db,workspace,run["pipeline_version_id"],member,active=True,current=False)
        yield db, run, scope


def start_run(conn, *, workspace, member, run_id, priority="fresh", max_attempts=3, enabled=False):
    if priority not in ("fresh","backfill") or type(max_attempts) is not int or not 1 <= max_attempts <= 5:
        raise ValueError("Invalid work configuration")
    with _run_transaction(conn,workspace,member,run_id,enabled,exclusive=True) as (db,run,scope):
        if run["state"] == "running":
            return
        if run["state"] != "queued":
            raise AccessDenied("Run is unavailable for dispatch")
        db.execute("""INSERT INTO panadan_knowledge.work_items (workspace_id,run_id,resource_id,priority_class,max_attempts)
            SELECT m.workspace_id,m.run_id,m.resource_id,
              CASE WHEN %s='backfill' OR v.event_at<%s::timestamptz-interval '1 day' THEN 'backfill' ELSE 'fresh' END,%s
            FROM panadan_knowledge.run_population_members m JOIN panadan_knowledge.resource_revisions v
              ON v.workspace_id=m.workspace_id AND v.id=m.resource_revision_id
            WHERE m.workspace_id=%s AND m.run_id=%s AND m.eligibility='ready'
            ON CONFLICT (workspace_id,run_id,resource_id) DO NOTHING""",
            (priority,scope["event_end"],max_attempts,workspace,run_id))
        db.execute("""UPDATE panadan_knowledge.runs SET state='running',started_at=clock_timestamp()
            WHERE workspace_id=%s AND id=%s""",(workspace,run_id))
        _check_timeout(db,scope)


def _now(db):
    return db.execute("SELECT clock_timestamp() AS instant").fetchone()["instant"]


def _attempt_outcome(db, workspace, item, fence, state, now):
    db.execute("""UPDATE panadan_knowledge.work_attempts SET outcome=%s,finished_at=%s
        WHERE workspace_id=%s AND item_id=%s AND fence=%s AND outcome='running'""",
        (state,now,workspace,item,fence))
    if db.rowcount != 1:
        raise StaleLease("Work lease is stale")


def _retry_at(now, attempts):
    return now + timedelta(seconds=2**attempts)


def _release(db, workspace, item, state, reason, available):
    db.execute("""UPDATE panadan_knowledge.work_items
        SET state=%s,owner_id=NULL,lease_until=NULL,outcome_code=%s,available_at=%s
        WHERE workspace_id=%s AND id=%s""",(state,reason,available,workspace,item))


def _recover_expired(db, workspace, run_id, now):
    expired = db.execute("""SELECT id,fence,attempt_count,max_attempts FROM panadan_knowledge.work_items
        WHERE workspace_id=%s AND run_id=%s AND state='running' AND lease_until<=%s
        ORDER BY lease_until,id LIMIT 32 FOR UPDATE SKIP LOCKED""",(workspace,run_id,now)).fetchall()
    for item in expired:
        _attempt_outcome(db,workspace,item["id"],item["fence"],"lease_expired",now)
        retry = item["attempt_count"] < item["max_attempts"]
        state = "retry_wait" if retry else "failed"
        _release(db,workspace,item["id"],state,"lease_expired",_retry_at(now,item["attempt_count"]) if retry else now)


def _current_input(db, workspace, item):
    return db.execute("""SELECT p.filtered_digest,p.expires_at,char_length(p.text_payload) AS characters
        FROM panadan_knowledge.work_items i
        JOIN panadan_knowledge.run_population_members m ON m.workspace_id=i.workspace_id AND m.run_id=i.run_id
          AND m.resource_id=i.resource_id AND m.eligibility='ready'
        JOIN panadan_knowledge.resources r ON r.workspace_id=m.workspace_id AND r.id=m.resource_id
          AND r.current_revision_id=m.resource_revision_id AND r.availability='active'
        JOIN panadan_knowledge.resource_revisions v ON v.workspace_id=r.workspace_id AND v.id=r.current_revision_id
          AND v.availability='active'
        JOIN panadan_knowledge.representations p ON p.workspace_id=v.workspace_id AND p.resource_revision_id=v.id
          AND p.id=m.representation_id AND p.availability='active'
          AND (p.expires_at IS NULL OR p.expires_at>clock_timestamp())
        WHERE i.workspace_id=%s AND i.id=%s FOR SHARE OF r,v,p""",(workspace,item)).fetchone()


def claim_work(conn, *, workspace, member, run_id, worker_id, lease_seconds=30, enabled=False):
    _identifier(worker_id)
    if type(lease_seconds) is not int or not 5 <= lease_seconds <= 300:
        raise ValueError("Invalid work lease duration")
    with _run_transaction(conn,workspace,member,run_id,enabled) as (db,run,scope):
        if run["state"] != "running":
            return None
        now = _now(db)
        _recover_expired(db,workspace,run_id,now)
        # Aged work takes precedence over new arrivals. Within each tier
        # stable FIFO ordering prevents a continuous stream starving backfill.
        for _ in range(32):
            item = db.execute("""SELECT id,fence,attempt_count FROM panadan_knowledge.work_items
                WHERE workspace_id=%s AND run_id=%s AND state IN ('queued','retry_wait') AND available_at<=%s
                  AND attempt_count<max_attempts
                ORDER BY CASE WHEN available_at<=%s-interval '30 seconds' THEN 0
                              WHEN priority_class='fresh' THEN 1 ELSE 2 END,available_at,id
                LIMIT 1 FOR UPDATE SKIP LOCKED""",(workspace,run_id,now,now)).fetchone()
            if item is None:
                return None
            current = _current_input(db,workspace,item["id"])
            moment = _now(db)
            if current is None or (current["expires_at"] is not None and current["expires_at"]<=moment):
                _release(db,workspace,item["id"],"blocked_policy","resource_unavailable",now)
                continue
            fence = item["fence"]+1
            until = moment+timedelta(seconds=lease_seconds)
            db.execute("""UPDATE panadan_knowledge.work_items SET state='running',owner_id=%s,lease_until=%s,
                fence=%s,attempt_count=attempt_count+1,outcome_code=NULL WHERE workspace_id=%s AND id=%s""",
                (worker_id,until,fence,workspace,item["id"]))
            db.execute("""INSERT INTO panadan_knowledge.work_attempts
                (workspace_id,item_id,attempt_no,fence,worker_id,started_at) VALUES (%s,%s,%s,%s,%s,%s)""",
                (workspace,item["id"],item["attempt_count"]+1,fence,worker_id,now))
            _check_timeout(db,scope)
            return WorkLease(item["id"],worker_id,fence,until)
        return None


def finish_work(conn, *, workspace, member, run_id, lease, outcome="succeeded", enabled=False):
    if (type(lease) is not WorkLease or type(lease.fence) is not int or lease.fence<1
            or outcome not in ("succeeded","retryable_failure","terminal_failure")):
        raise ValueError("Invalid work result")
    _identifier(lease.item_id)
    _identifier(lease.worker_id)
    with _run_transaction(conn,workspace,member,run_id,enabled) as (db,run,scope):
        item = db.execute("""SELECT id,attempt_count,max_attempts,lease_until FROM panadan_knowledge.work_items
            WHERE workspace_id=%s AND run_id=%s AND id=%s AND state='running' AND owner_id=%s AND fence=%s
            FOR UPDATE""",(workspace,run_id,lease.item_id,lease.worker_id,lease.fence)).fetchone()
        now = _now(db)
        if run["state"]!="running" or item is None or item["lease_until"]<=now:
            raise StaleLease("Work lease is stale")
        current = _current_input(db,workspace,lease.item_id)
        now = _now(db)
        if item["lease_until"]<=now:
            raise StaleLease("Work lease is stale")
        reason = None
        available = now
        if current is None or (current["expires_at"] is not None and current["expires_at"]<=now):
            state, reason = "blocked_policy", "resource_unavailable"
        elif outcome == "succeeded":
            db.execute("""INSERT INTO panadan_knowledge.fixture_work_results
                (workspace_id,item_id,fence,processor,input_digest,character_count) VALUES (%s,%s,%s,%s,%s,%s)""",
                (workspace,lease.item_id,lease.fence,PROCESSOR,current["filtered_digest"],current["characters"]))
            state = "succeeded"
        elif outcome == "retryable_failure" and item["attempt_count"] < item["max_attempts"]:
            state, reason = "retry_wait", "fixture_failed"
            available = _retry_at(now,item["attempt_count"])
        else:
            state, reason = "failed", "fixture_failed"
        _attempt_outcome(db,workspace,lease.item_id,lease.fence,state,now)
        _release(db,workspace,lease.item_id,state,reason,available)
        _check_timeout(db,scope)
        return state


def control_run(conn, *, workspace, member, run_id, action, enabled=False):
    if action not in ("pause","resume","cancel"):
        raise ValueError("Unknown run action")
    with _run_transaction(conn,workspace,member,run_id,enabled,exclusive=True,authorize_source=action=="resume") as (db,run,scope):
        state = run["state"]
        if action == "resume" and state == "paused":
            next_state = "running" if run["started_at"] else "queued"
            db.execute("""UPDATE panadan_knowledge.work_items SET
                state=CASE WHEN attempt_count=max_attempts THEN 'failed' ELSE 'queued' END,
                outcome_code=CASE WHEN attempt_count=max_attempts THEN 'attempts_exhausted' END
                WHERE workspace_id=%s AND run_id=%s AND state='paused'""",(workspace,run_id))
            _check_timeout(db,scope)
        elif action in ("pause","cancel") and state in ("queued","running","paused"):
            next_state = "paused" if action == "pause" else "canceled"
            db.execute("""UPDATE panadan_knowledge.work_attempts a SET outcome=%s,finished_at=clock_timestamp()
                FROM panadan_knowledge.work_items i WHERE a.workspace_id=i.workspace_id AND a.item_id=i.id
                  AND a.fence=i.fence AND a.outcome='running' AND i.workspace_id=%s AND i.run_id=%s""",
                (next_state,workspace,run_id))
            db.execute("""UPDATE panadan_knowledge.work_items SET state=%s,owner_id=NULL,lease_until=NULL
                WHERE workspace_id=%s AND run_id=%s AND state IN ('queued','running','retry_wait','paused')""",
                (next_state,workspace,run_id))
        else:
            raise AccessDenied("Run action unavailable")
        db.execute("""UPDATE panadan_knowledge.runs SET state=%s,finished_at=CASE WHEN %s='canceled'
            THEN clock_timestamp() END WHERE workspace_id=%s AND id=%s""",(next_state,next_state,workspace,run_id))
        return next_state


def reconcile_run(conn, *, workspace, member, run_id, enabled=False):
    """Resolve the run once. Recovery can repeat this after any worker exit."""
    with _run_transaction(conn,workspace,member,run_id,enabled,exclusive=True,authorize_source=False) as (db,run,_):
        if run["state"] != "running":
            return run["state"]
        now = _now(db)
        _recover_expired(db,workspace,run_id,now)
        counts = {row["state"]:row["count"] for row in db.execute("""SELECT state,count(*) FROM panadan_knowledge.work_items
            WHERE workspace_id=%s AND run_id=%s GROUP BY state""",(workspace,run_id)).fetchall()}
        if any(counts.get(state,0) for state in ("queued","running","retry_wait","paused")):
            return "running"
        coverage = db.execute("""SELECT excluded_count,bounded FROM panadan_knowledge.coverage_snapshots
            WHERE workspace_id=%s AND run_id=%s AND stage='admission'""",(workspace,run_id)).fetchone()
        if counts.get("failed") and not counts.get("succeeded"):
            state = "failed"
        elif counts.get("blocked_policy") and not counts.get("succeeded"):
            state = "blocked_policy"
        elif coverage["excluded_count"] or coverage["bounded"] or counts.get("failed") or counts.get("blocked_policy"):
            state = "partial"
        else:
            state = "succeeded"
        db.execute("UPDATE panadan_knowledge.runs SET state=%s,finished_at=%s WHERE workspace_id=%s AND id=%s",
                   (state,now,workspace,run_id))
        return state
