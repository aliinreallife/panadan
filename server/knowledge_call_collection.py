"""One short, transactional synthetic collection page and its durable cursor."""

from contextlib import contextmanager
from dataclasses import dataclass
import os
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .knowledge_authorization import AccessDenied
from .knowledge_call_contract import UnsupportedCallContract, call_metadata_schema
from .knowledge_call_privacy import REDACTION_VERSION, prepare_call
from .knowledge_call_source import CallCursor, CallSourceUnavailable, MAX_ID, MAX_PAGE_SIZE, SyntheticCallReader


COLLECTOR_LOGIN = "panadan_knowledge_collector_ci"
COLLECTOR_PASSWORD = "synthetic_knowledge_collector_only"
COLLECTOR_NAMESPACE = "panadan.synthetic.collector"


class CollectionUnavailable(RuntimeError):
    """Safe failure at the owned database boundary."""


class CheckpointChanged(RuntimeError):
    """Another collection page or a policy change invalidated this snapshot."""


class _PageConflict(Exception):
    def __init__(self, external_id, reason):
        super().__init__(reason)
        self.external_id = external_id
        self.reason = reason


@dataclass(frozen=True, slots=True)
class CollectionScope:
    workspace: UUID
    source: UUID
    operator: UUID
    principal_subject: UUID
    checkpoint: UUID


@dataclass(frozen=True, slots=True)
class CollectionPage:
    cursor_version: int
    finished: bool
    examined: int = 0
    accepted: int = 0
    unchanged: int = 0
    excluded: int = 0
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class ReconciliationPage:
    after_id: int
    finished: bool
    examined: int
    restricted: int


@contextmanager
def _owned_transaction(port, scope):
    with psycopg.connect(host="127.0.0.1", port=port, dbname="panadan_ci", user=COLLECTOR_LOGIN,
            password=COLLECTOR_PASSWORD, sslmode="disable", connect_timeout=3, autocommit=True,
            options="-c search_path=pg_catalog -c statement_timeout=5000 -c lock_timeout=2000") as db, db.transaction():
        identity = db.execute("""SELECT current_database(),session_user,current_setting('server_version_num')::int/10000,
            NOT (r.rolsuper OR r.rolcreatedb OR r.rolcreaterole OR r.rolreplication OR r.rolbypassrls OR r.rolinherit),
            current_user=session_user AND NOT has_schema_privilege(session_user,'panadan_knowledge','USAGE'),
            (SELECT count(*)=1 AND bool_and(parent.rolname='panadan_knowledge_collector'
                AND NOT (m.admin_option OR m.inherit_option) AND m.set_option
                AND NOT (parent.rolcanlogin OR parent.rolinherit OR parent.rolsuper OR parent.rolcreatedb
                         OR parent.rolcreaterole OR parent.rolreplication OR parent.rolbypassrls)
                AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_auth_members p WHERE p.member=parent.oid))
             FROM pg_catalog.pg_auth_members m JOIN pg_catalog.pg_roles parent ON parent.oid=m.roleid
             WHERE m.member=r.oid)
            FROM pg_catalog.pg_roles r WHERE r.rolname=session_user""").fetchone()
        if identity != ("panadan_ci", COLLECTOR_LOGIN, 18, True, True, True):
            raise AccessDenied("Collection scope unavailable")
        db.execute("SET LOCAL ROLE panadan_knowledge_collector")
        settings = {
            "panadan.workspace_id": str(scope.workspace),
            "panadan.collection_source": str(scope.source),
            "panadan.collection_operator": str(scope.operator),
            "panadan.authority_namespace": COLLECTOR_NAMESPACE,
            "panadan.authority_subject": str(scope.principal_subject),
        }
        for key, value in settings.items():
            db.execute("SELECT set_config(%s,%s,true)", (key, value))
        with db.cursor(row_factory=dict_row) as cursor:
            yield cursor


_CHECKPOINT = """SELECT ch.*,w.policy_epoch,g.id AS grant_id,g.valid_until,
    s.kind,s.connection_ref,s.state AS source_state,o.external_operator_key,
    c.adapter_version,c.state AS contract_state,c.contract,a.json_schema,
    r.definition AS retention,q.definition AS redaction
  FROM panadan_knowledge.sync_checkpoints ch
  JOIN panadan_knowledge.workspaces w ON w.id=ch.workspace_id AND w.state='active'
  JOIN panadan_knowledge.memberships m ON m.workspace_id=w.id AND m.state='active' AND m.revoked_at IS NULL
  JOIN panadan_knowledge.principals p ON p.id=m.principal_id AND p.state='active' AND p.kind='service'
  JOIN panadan_knowledge.source_scope_grants g ON g.workspace_id=w.id AND g.membership_id=m.id
    AND g.scope_kind='operator' AND g.capability='source.collect' AND g.revoked_at IS NULL
    AND g.source_id=ch.source_id AND g.operator_scope_id=ch.operator_scope_id
    AND g.valid_from<=clock_timestamp() AND (g.valid_until IS NULL OR g.valid_until>clock_timestamp())
  JOIN panadan_knowledge.sources s ON s.workspace_id=w.id AND s.id=ch.source_id AND s.state='active'
    AND s.current_contract_id=ch.contract_id
  JOIN panadan_knowledge.source_contract_versions c ON c.workspace_id=w.id AND c.source_id=s.id AND c.id=ch.contract_id
  JOIN panadan_knowledge.operator_scopes o ON o.workspace_id=w.id AND o.source_id=s.id AND o.id=ch.operator_scope_id
    AND o.state='active'
  JOIN panadan_knowledge.contract_operator_scopes b ON b.workspace_id=w.id AND b.source_id=s.id
    AND b.contract_id=c.id AND b.operator_scope_id=o.id
  JOIN panadan_knowledge.attribute_schema_versions a ON a.workspace_id=w.id AND a.id=ch.attribute_schema_id
    AND a.schema_key='call_metadata' AND a.state='approved'
  JOIN panadan_knowledge.policy_versions r ON r.workspace_id=w.id AND r.id=ch.retention_policy_id
    AND r.kind='retention' AND r.state='approved'
  JOIN panadan_knowledge.policy_versions q ON q.workspace_id=w.id AND q.id=ch.redaction_policy_id
    AND q.kind='redaction' AND q.state='approved'
  WHERE ch.workspace_id=%s AND ch.id=%s"""
_SCOPE_LOCKS = " FOR SHARE OF w,m,p,g,s,c,o,b,a,r,q FOR UPDATE OF ch"


def _authorized(db, scope, *, lock=False):
    matching = db.execute(_CHECKPOINT + (_SCOPE_LOCKS if lock else ""), (scope.workspace, scope.checkpoint)).fetchall()
    if len(matching) != 1:
        raise AccessDenied("Collection scope unavailable")
    row = matching[0]
    retention = row["retention"]
    days = retention.get("days")
    if (row["connection_ref"] != "synthetic-calls" or row["redaction"] != {"processor": REDACTION_VERSION}
            or row["json_schema"] != call_metadata_schema()
            or retention.keys() != {"days"} or type(days) is not int or not 1 <= days <= 90):
        raise AccessDenied("Collection policy unavailable")
    return row


_CURRENT = """SELECT res.id,r.id AS revision_id,r.rev,r.source_order,r.event_at,r.operation,r.normalized_metadata,
       r.transcript_outcome,filtered.filtered_digest
  FROM panadan_knowledge.resources res
  LEFT JOIN panadan_knowledge.resource_revisions r ON r.workspace_id=res.workspace_id AND r.id=res.current_revision_id
  LEFT JOIN panadan_knowledge.representations filtered ON filtered.workspace_id=r.workspace_id
    AND filtered.resource_revision_id=r.id AND filtered.representation_rev=1
  WHERE res.workspace_id=%s AND res.source_id=%s AND res.external_id=%s
  FOR UPDATE OF res"""


def _persist(db, checkpoint, call):
    workspace, source, operator = (checkpoint[k] for k in ("workspace_id", "source_id", "operator_scope_id"))
    external_id = call.cursor.call_id
    if call.outcome == "metadata_invalid":
        return "excluded"
    resource_key = (workspace, source, str(external_id))
    db.execute("""INSERT INTO panadan_knowledge.resources(workspace_id,source_id,external_id)
        VALUES (%s,%s,%s) ON CONFLICT (workspace_id,source_id,external_id) DO NOTHING""", resource_key)
    current = db.execute(_CURRENT, resource_key).fetchone()
    if current is None:
        raise _PageConflict(external_id, "source_scope_changed")
    representation = call.representation
    digest = representation.digest if representation else None
    if current["source_order"] is not None and call.revision_no <= current["source_order"]:
        if call.revision_no < current["source_order"]:
            return "unchanged"
        expected = (call.event_at, call.operation, call.metadata, call.outcome, digest)
        observed = tuple(current[key] for key in (
            "event_at", "operation", "normalized_metadata", "transcript_outcome", "filtered_digest",
        ))
        if observed != expected:
            raise _PageConflict(external_id, "revision_conflict")
        return "unchanged"

    if call.operation == "tombstone":
        availability = "deleted"
    elif call.outcome in {"transcript_review", "transcript_invalid", "transcript_oversize", "filtered_oversize"}:
        availability = "restricted"
    else:
        availability = "active"
    revision = db.execute("""INSERT INTO panadan_knowledge.resource_revisions
        (workspace_id,source_id,resource_id,contract_id,operator_scope_id,rev,source_order,source_changed_at,event_at,
         operation,normalized_metadata,attribute_schema_id,retention_policy_id,availability,transcript_outcome)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (workspace, source, current["id"], checkpoint["contract_id"], operator, (current["rev"] or 0) + 1,
         call.revision_no, call.cursor.changed_at, call.event_at, call.operation, Jsonb(call.metadata),
         checkpoint["attribute_schema_id"], checkpoint["retention_policy_id"], availability, call.outcome)).fetchone()["id"]
    if representation:
        db.execute("""INSERT INTO panadan_knowledge.representations
            (workspace_id,resource_revision_id,representation_rev,text_payload,filtered_digest,redaction_policy_id,availability,expires_at)
            VALUES (%s,%s,1,%s,%s,%s,'active',clock_timestamp()+make_interval(days=>%s))""",
            (workspace, revision, representation.text, digest, checkpoint["redaction_policy_id"], checkpoint["retention"]["days"]))
    db.execute("""UPDATE panadan_knowledge.resources SET current_revision_id=%s,availability=%s,
        last_seen_at=greatest(last_seen_at,clock_timestamp()) WHERE workspace_id=%s AND id=%s""",
        (revision, availability, workspace, current["id"]))
    db.execute("INSERT INTO panadan_knowledge.collection_intents(workspace_id,resource_revision_id) VALUES (%s,%s)",
               (workspace, revision))
    return "accepted"


def _record_run(db, checkpoint, result, exclusions):
    workspace = checkpoint["workspace_id"]
    run_id = db.execute("""INSERT INTO panadan_knowledge.sync_runs
        (workspace_id,checkpoint_id,cursor_version,state,examined,accepted,unchanged,excluded,reason_code)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (workspace, checkpoint["id"], result.cursor_version, "blocked" if result.reason else "succeeded",
         result.examined, result.accepted, result.unchanged, result.excluded, result.reason)).fetchone()["id"]
    for external_id, reason, terminal in exclusions:
        db.execute("""INSERT INTO panadan_knowledge.source_exclusions(workspace_id,run_id,external_id,reason_code,terminal)
            VALUES (%s,%s,%s,%s,%s)""", (workspace, run_id, external_id, reason, terminal))


def _require_binding(owned_port, source_port, scope, enabled, limit):
    if (enabled is not True or type(scope) is not CollectionScope
            or any(type(uid) is not UUID or not uid.int for uid in (
                scope.workspace, scope.source, scope.operator, scope.principal_subject, scope.checkpoint))
            or any(value for name, value in os.environ.items() if name.startswith("PG"))):
        raise AccessDenied("Collection scope unavailable")
    if any(type(port) is not int or not 1 <= port <= 65535 for port in (owned_port, source_port)):
        raise AccessDenied("Collection scope unavailable")
    if type(limit) is not int or not 1 <= limit <= MAX_PAGE_SIZE:
        raise ValueError("Invalid collection page limit")


def _reader(checkpoint, port):
    return SyntheticCallReader(port=port, operator_key=checkpoint["external_operator_key"],
        kind=checkpoint["kind"], adapter=checkpoint["adapter_version"], contract_state=checkpoint["contract_state"],
        source_state=checkpoint["source_state"], contract=checkpoint["contract"])


def _check_expiry(db, checkpoint):
    if checkpoint["valid_until"] is not None:
        moment = db.execute("SELECT clock_timestamp() AS moment").fetchone()["moment"]
        if moment >= checkpoint["valid_until"]:
            raise AccessDenied("Collection scope unavailable")


def collect_page(*, owned_port, source_port, scope, enabled=False, limit=MAX_PAGE_SIZE):
    _require_binding(owned_port, source_port, scope, enabled, limit)
    try:
        with _owned_transaction(owned_port, scope) as db:
            checkpoint = _authorized(db, scope)
        if checkpoint["finished"]:
            return CollectionPage(checkpoint["cursor_version"], True)
        reader = _reader(checkpoint, source_port)
        after = CallCursor(checkpoint["cursor_time"], checkpoint["cursor_id"]) if checkpoint["cursor_id"] else None
        reason = None
        try:
            # Only prepared, filtered values survive into the owned transaction.
            calls = tuple(map(prepare_call, reader.read_page(
                event_start=checkpoint["event_start"], event_end=checkpoint["event_end"],
                changed_since=checkpoint["change_start"], changed_before=checkpoint["change_end"],
                after=after, limit=limit)))
        except CallSourceUnavailable:
            reason = "source_read_failed"
            calls = ()
        with _owned_transaction(owned_port, scope) as db:
            if _authorized(db, scope, lock=True) != checkpoint:
                raise CheckpointChanged("Collection checkpoint changed")
            conn = db.connection
            counts = dict(accepted=0, unchanged=0, excluded=0)
            exclusions = []
            try:
                with conn.transaction():
                    for call in calls:
                        outcome = _persist(db, checkpoint, call)
                        counts[outcome] += 1
                        if outcome != "unchanged" and call.outcome not in {"tombstone", "filtered"}:
                            exclusions.append((call.cursor.call_id, call.outcome, True))
            except _PageConflict as conflict:
                reason = conflict.reason
                exclusions = [(conflict.external_id, reason, False)]

            _check_expiry(db, checkpoint)
            version = checkpoint["cursor_version"]
            if reason:
                result = CollectionPage(version, False, examined=len(calls), reason=reason)
            else:
                next_cursor = calls[-1].cursor if calls else after
                finished = len(calls) < limit
                db.execute("""UPDATE panadan_knowledge.sync_checkpoints SET cursor_time=%s,cursor_id=%s,
                    cursor_version=cursor_version+1,finished=%s WHERE workspace_id=%s AND id=%s AND cursor_version=%s""",
                    (next_cursor.changed_at if next_cursor else None, next_cursor.call_id if next_cursor else None,
                     finished, scope.workspace, scope.checkpoint, version))
                if db.rowcount != 1:
                    raise CheckpointChanged("Collection checkpoint changed")
                result = CollectionPage(version + 1, finished, examined=len(calls), **counts)
            _record_run(db, checkpoint, result, exclusions)
            return result
    except UnsupportedCallContract:
        raise AccessDenied("Collection scope unavailable") from None
    except psycopg.Error:
        raise CollectionUnavailable("Owned collection database operation failed") from None


def reconcile_page(*, owned_port, source_port, scope, enabled=False, after_id=0, limit=MAX_PAGE_SIZE):
    """Recheck known calls against the approved source scope without fetching text."""
    _require_binding(owned_port, source_port, scope, enabled, limit)
    if type(after_id) is not int or not 0 <= after_id <= MAX_ID:
        raise ValueError("Invalid reconciliation cursor")
    try:
        with _owned_transaction(owned_port, scope) as db:
            checkpoint = _authorized(db, scope)
            known = db.execute("""SELECT r.id,r.current_revision_id,r.external_id::numeric AS external_id
                FROM panadan_knowledge.resources r JOIN panadan_knowledge.resource_revisions v
                  ON v.workspace_id=r.workspace_id AND v.id=r.current_revision_id
                WHERE r.workspace_id=%s AND r.source_id=%s AND v.operator_scope_id=%s
                  AND r.availability IN ('active','restricted')
                  AND v.event_at>=%s AND v.event_at<%s AND r.external_id::numeric>%s
                ORDER BY r.external_id::numeric LIMIT %s""",
                (scope.workspace, scope.source, scope.operator, checkpoint["event_start"],
                 checkpoint["event_end"], after_id, limit)).fetchall()
        source_ids = tuple(int(record["external_id"]) for record in known)
        eligibility = _reader(checkpoint, source_port).check_scope(
            known_ids=source_ids, event_start=checkpoint["event_start"], event_end=checkpoint["event_end"])
        restricted = 0
        with _owned_transaction(owned_port, scope) as db:
            if _authorized(db, scope, lock=True) != checkpoint:
                raise CheckpointChanged("Collection checkpoint changed")
            for record, external_id in zip(known, source_ids, strict=True):
                eligible = eligibility.get(external_id)
                if eligible is True:
                    continue
                # An absent row is stale, never a deletion. A positive
                # exclusion (reassignment or removed scope) suppresses text.
                state = "restricted" if eligible is False else "stale"
                db.execute("""UPDATE panadan_knowledge.resources SET availability=%s
                    WHERE workspace_id=%s AND id=%s AND current_revision_id=%s AND availability<>%s""",
                    (state, scope.workspace, record["id"], record["current_revision_id"], state))
                if db.rowcount:
                    restricted += 1
                    db.execute("""INSERT INTO panadan_knowledge.collection_intents(workspace_id,resource_revision_id,reason)
                        VALUES (%s,%s,'scope_unavailable') ON CONFLICT DO NOTHING""",
                        (scope.workspace, record["current_revision_id"]))
            _check_expiry(db, checkpoint)
        return ReconciliationPage(source_ids[-1] if source_ids else after_id, len(known) < limit, len(known), restricted)
    except UnsupportedCallContract:
        raise AccessDenied("Collection scope unavailable") from None
    except (psycopg.Error, CallSourceUnavailable):
        raise CollectionUnavailable("Collection reconciliation failed") from None
