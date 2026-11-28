"""M02.4 source-to-owned tests with actual distinct read and collector logins."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

from psycopg import errors
from psycopg.types.json import Jsonb
import pytest

from server.knowledge_authorization import AccessDenied
from server.knowledge_call_collection import (
    COLLECTOR_LOGIN,
    COLLECTOR_NAMESPACE,
    COLLECTOR_PASSWORD,
    CheckpointChanged,
    CollectionPage,
    CollectionScope,
    ReconciliationPage,
    _owned_transaction,
    collect_page,
    reconcile_page,
)
from server.knowledge_call_contract import SYNTHETIC_ADAPTER, call_metadata_schema, synthetic_call_contract
from server.knowledge_call_privacy import REDACTION_VERSION
from server.knowledge_call_source import SOURCE_READER, SyntheticCallReader
from test_knowledge_call_resources import M007, _previous
from test_knowledge_call_source import CHANGED, CUTOFF, END, START, _row, source
from test_knowledge_foundation import ROOT, _reject, db


M008 = ROOT / "database/migrations/008_knowledge_call_collection.sql"
ROLE = "panadan_knowledge_collector"
BASE_CHANGE = CHANGED - timedelta(hours=1)
PRIVATE_FIXTURE = "بلیط، تماس ۰۹۱۲۳۴۵۶۷۸۹ یا canary-private@example.invalid"


def _insert(db, query, params):
    return db.execute(query, params).fetchone()[0]


@pytest.fixture
def collection(db, source):
    source_admin, port, _ = source
    with db.transaction():
        _previous(db)
        db.execute(M007.read_text(encoding="utf-8"))
        for _ in range(2):
            db.execute(M008.read_text(encoding="utf-8"))
        db.execute(f"CREATE ROLE {COLLECTOR_LOGIN} LOGIN NOINHERIT PASSWORD '{COLLECTOR_PASSWORD}'")
        db.execute(f"GRANT CONNECT ON DATABASE panadan_ci TO {COLLECTOR_LOGIN}")
        db.execute(f"GRANT {ROLE} TO {COLLECTOR_LOGIN} WITH INHERIT FALSE, SET TRUE")
        workspace = _insert(db, """INSERT INTO panadan_knowledge.workspaces(slug,name,state)
            VALUES ('collector-test','Collection test','active') RETURNING id""", ())
        subject = uuid4()
        principal = _insert(db, """INSERT INTO panadan_knowledge.principals(authority_namespace,authority_subject,kind,state)
            VALUES (%s,%s,'service','active') RETURNING id""", (COLLECTOR_NAMESPACE, str(subject)))
        membership = _insert(db, """INSERT INTO panadan_knowledge.memberships(workspace_id,principal_id,state)
            VALUES (%s,%s,'active') RETURNING id""", (workspace, principal))
        registry = _insert(db, """INSERT INTO panadan_knowledge.sources(workspace_id,source_key,label,connection_ref)
            VALUES (%s,'calls','Synthetic calls','synthetic-calls') RETURNING id""", (workspace,))
        contract = _insert(db, """INSERT INTO panadan_knowledge.source_contract_versions
            (workspace_id,source_id,rev,adapter_version,contract,state) VALUES (%s,%s,1,%s,%s,'synthetic') RETURNING id""",
            (workspace, registry, SYNTHETIC_ADAPTER, Jsonb(synthetic_call_contract())))
        db.execute("UPDATE panadan_knowledge.sources SET current_contract_id=%s,state='active' WHERE workspace_id=%s AND id=%s",
                   (contract, workspace, registry))
        operator = _insert(db, """INSERT INTO panadan_knowledge.operator_scopes
            (workspace_id,source_id,external_operator_key,state) VALUES (%s,%s,'operator-a','active') RETURNING id""",
            (workspace, registry))
        db.execute("INSERT INTO panadan_knowledge.contract_operator_scopes VALUES (%s,%s,%s,%s)",
                   (workspace, registry, contract, operator))
        grant = _insert(db, """INSERT INTO panadan_knowledge.source_scope_grants
            (workspace_id,membership_id,grantor,scope_kind,source_id,operator_scope_id,capability,valid_from)
            VALUES (%s,%s,%s,'operator',%s,%s,'source.collect',clock_timestamp()-interval '1 day') RETURNING id""",
            (workspace, membership, membership, registry, operator))
        schema = _insert(db, """INSERT INTO panadan_knowledge.attribute_schema_versions
            (workspace_id,schema_key,rev,json_schema,state) VALUES (%s,'call_metadata',1,%s,'approved') RETURNING id""",
            (workspace, Jsonb(call_metadata_schema())))
        policy_ids = []
        for kind, definition in (("retention", {"days": 30}), ("redaction", {"processor": REDACTION_VERSION})):
            policy_ids.append(_insert(db, """INSERT INTO panadan_knowledge.policy_versions
                (workspace_id,kind,policy_key,rev,definition,state,approved_by,approved_at)
                VALUES (%s,%s,'synthetic',1,%s,'approved',%s,now()) RETURNING id""",
                (workspace, kind, Jsonb(definition), membership)))

    def new_checkpoint(change_start=BASE_CHANGE, change_end=CUTOFF):
        return _insert(db, """INSERT INTO panadan_knowledge.sync_checkpoints
            (workspace_id,source_id,contract_id,operator_scope_id,attribute_schema_id,retention_policy_id,redaction_policy_id,
             event_start,event_end,change_start,change_end)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (workspace, registry, contract, operator, schema, *policy_ids, START, END, change_start, change_end))

    scope = CollectionScope(workspace, registry, operator, subject, new_checkpoint())

    def collect(target=scope, limit=50):
        return collect_page(owned_port=port, source_port=port, scope=target, limit=limit, enabled=True)

    try:
        yield db, source_admin, port, scope, grant, new_checkpoint, collect
    finally:
        with db.transaction():
            db.execute("DROP SCHEMA panadan_knowledge CASCADE")
            db.execute(f"REVOKE CONNECT ON DATABASE panadan_ci FROM {COLLECTOR_LOGIN}")
            db.execute(f"DROP ROLE {COLLECTOR_LOGIN}")
            db.execute(f"DROP ROLE {ROLE},panadan_knowledge_authorizer,panadan_knowledge_reader,panadan_knowledge_owner")


def test_collection_persists_filtered_revisions_and_cas_then_handles_overlap_and_tombstone(collection):
    db, src, _, scope, _, new_checkpoint, collect = collection
    _row(src, 1, text=PRIVATE_FIXTURE)
    _row(src, 2, text=None)
    _row(src, 3, duration=-1, text=PRIVATE_FIXTURE)
    _row(src, 4, operator="operator-b", text=PRIVATE_FIXTURE)
    assert collect(limit=2) == CollectionPage(1, False, examined=2, accepted=2)
    assert collect(limit=2) == CollectionPage(2, True, examined=1, excluded=1)
    assert collect() == CollectionPage(2, True)
    assert db.execute("""SELECT text_payload,expires_at>clock_timestamp() FROM panadan_knowledge.representations"""
                      ).fetchall() == [("بلیط، تماس [PHONE] یا [EMAIL]", True)]
    assert src.execute("SELECT transcript FROM panadan_synthetic_source.calls WHERE call_id=1").fetchone() == (PRIVATE_FIXTURE,)
    assert db.execute("SELECT count(*) FROM panadan_knowledge.collection_intents").fetchone() == (2,)
    assert db.execute("SELECT reason_code,terminal FROM panadan_knowledge.source_exclusions ORDER BY external_id").fetchall() == [
        ("transcript_missing", True), ("metadata_invalid", True),
    ]

    replay = replace(scope, checkpoint=new_checkpoint(change_end=CUTOFF + timedelta(minutes=1)))
    assert collect(replay) == CollectionPage(1, True, examined=3, unchanged=2, excluded=1)
    assert db.execute("SELECT count(*) FROM panadan_knowledge.resource_revisions").fetchone() == (2,)

    src.execute("""UPDATE panadan_synthetic_source.calls SET revision_no=2,is_deleted=true,changed_at=%s WHERE call_id=1""",
                (BASE_CHANGE - timedelta(seconds=1),))
    overlap = replace(scope, checkpoint=new_checkpoint(change_start=BASE_CHANGE - timedelta(minutes=1)))
    assert collect(overlap) == CollectionPage(1, True, examined=3, accepted=1, unchanged=1, excluded=1)
    assert db.execute("""SELECT r.availability,v.source_order,v.operation FROM panadan_knowledge.resources r
        JOIN panadan_knowledge.resource_revisions v ON v.workspace_id=r.workspace_id AND v.id=r.current_revision_id
        WHERE r.external_id='1'""").fetchone() == ("deleted", 2, "tombstone")
    assert db.execute("SELECT count(*) FROM panadan_knowledge.representations").fetchone() == (1,)


def test_equal_marker_conflict_rolls_back_page_and_does_not_advance(collection):
    db, src, _, scope, _, new_checkpoint, collect = collection
    _row(src, 2, text="initial sanitized fixture")
    assert collect().accepted == 1
    src.execute("UPDATE panadan_synthetic_source.calls SET transcript='conflicting synthetic fixture' WHERE call_id=2")
    _row(src, 1, changed_at=CHANGED - timedelta(seconds=1), text="new fixture before the conflict")
    replay = replace(scope, checkpoint=new_checkpoint(change_end=CUTOFF + timedelta(minutes=1)))
    assert collect(replay) == CollectionPage(0, False, examined=2, reason="revision_conflict")
    assert db.execute("SELECT external_id FROM panadan_knowledge.resources").fetchall() == [("2",)]
    assert db.execute("SELECT text_payload FROM panadan_knowledge.representations").fetchall() == [("initial sanitized fixture",)]
    assert db.execute("SELECT cursor_version,cursor_id FROM panadan_knowledge.sync_checkpoints WHERE id=%s",
                      (replay.checkpoint,)).fetchone() == (0, None)
    assert db.execute("SELECT reason_code,terminal FROM panadan_knowledge.source_exclusions").fetchone() == ("revision_conflict", False)


def test_scope_default_deny_and_collector_cannot_modify_authority_or_read_transcript(collection):
    db, _, port, scope, _, _, collect = collection
    with pytest.raises(AccessDenied):
        collect_page(owned_port=port, source_port=port, scope=scope)
    for wrong in (replace(scope, workspace=uuid4()), replace(scope, operator=uuid4()), replace(scope, principal_subject=uuid4())):
        with pytest.raises(AccessDenied):
            collect(wrong)
    with _owned_transaction(port, scope) as cursor:
        _reject(cursor.connection, errors.InsufficientPrivilege, "SELECT text_payload FROM panadan_knowledge.representations")
        _reject(cursor.connection, errors.InsufficientPrivilege, "UPDATE panadan_knowledge.sources SET id=id")
        _reject(cursor.connection, errors.InsufficientPrivilege, "DELETE FROM panadan_knowledge.resources")
    db.execute(f"GRANT panadan_knowledge_reader TO {COLLECTOR_LOGIN} WITH INHERIT FALSE, SET TRUE")
    with pytest.raises(AccessDenied):
        collect()


def test_revocation_between_read_and_commit_leaves_no_durable_payload(collection, monkeypatch):
    db, src, _, _, grant, _, collect = collection
    _row(src, 1, text=PRIVATE_FIXTURE)
    read = SyntheticCallReader.read_page

    def revoke_after_read(reader, **kwargs):
        rows = read(reader, **kwargs)
        db.execute("UPDATE panadan_knowledge.source_scope_grants SET revoked_at=clock_timestamp() WHERE id=%s", (grant,))
        return rows

    monkeypatch.setattr(SyntheticCallReader, "read_page", revoke_after_read)
    with pytest.raises(AccessDenied):
        collect()
    assert db.execute("SELECT count(*) FROM panadan_knowledge.resources").fetchone() == (0,)
    assert db.execute("SELECT cursor_version FROM panadan_knowledge.sync_checkpoints").fetchone() == (0,)


def test_concurrent_collection_has_one_winner_and_one_stale_checkpoint(collection, monkeypatch):
    db, src, _, _, _, _, collect = collection
    _row(src, 1, text=PRIVATE_FIXTURE)
    rendezvous = Barrier(2)
    read = SyntheticCallReader.read_page

    def concurrent_read(reader, **kwargs):
        rows = read(reader, **kwargs)
        rendezvous.wait(timeout=10)
        return rows

    monkeypatch.setattr(SyntheticCallReader, "read_page", concurrent_read)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = [pool.submit(collect) for _ in range(2)]
        results, stale = [], 0
        for job in pending:
            try:
                results.append(job.result(timeout=20))
            except CheckpointChanged:
                stale += 1
    assert stale == 1 and results == [CollectionPage(1, True, examined=1, accepted=1)]
    assert db.execute("SELECT count(*) FROM panadan_knowledge.collection_intents").fetchone() == (1,)


def test_source_unavailability_records_only_safe_failure(collection):
    db, src, _, _, _, _, collect = collection
    src.execute(f"REVOKE USAGE ON SCHEMA panadan_synthetic_source FROM {SOURCE_READER}")
    assert collect() == CollectionPage(0, False, reason="source_read_failed")
    assert db.execute("SELECT reason_code,examined FROM panadan_knowledge.sync_runs").fetchall() == [("source_read_failed", 0)]


def test_reconciliation_suppresses_scope_loss_without_inventing_deletion(collection):
    db, src, port, scope, _, _, collect = collection
    for call_id in (1, 2, 3):
        _row(src, call_id, text=PRIVATE_FIXTURE)
    assert collect().accepted == 3
    src.execute("UPDATE panadan_synthetic_source.calls SET operator_key='operator-b' WHERE call_id=1")
    src.execute("DELETE FROM panadan_synthetic_source.calls WHERE call_id=2")
    options = dict(owned_port=port, source_port=port, scope=scope, enabled=True)
    assert reconcile_page(**options, limit=2) == ReconciliationPage(2, False, 2, 2)
    assert reconcile_page(**options, after_id=2) == ReconciliationPage(3, True, 1, 0)
    assert db.execute("SELECT external_id,availability FROM panadan_knowledge.resources ORDER BY external_id").fetchall() == [
        ("1", "restricted"), ("2", "stale"), ("3", "active"),
    ]
    assert db.execute("SELECT count(*) FROM panadan_knowledge.resource_revisions WHERE operation='tombstone'").fetchone() == (0,)
    assert db.execute("SELECT count(*) FROM panadan_knowledge.collection_intents WHERE reason='scope_unavailable'").fetchone() == (2,)
    assert reconcile_page(**options).restricted == 0
