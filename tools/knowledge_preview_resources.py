"""Provision synthetic resources for the explicitly isolated workspace preview."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb

from server.knowledge_authorization import RESOURCE_CAPABILITIES
from server.knowledge_call_collection import (
    COLLECTOR_LOGIN, COLLECTOR_NAMESPACE, COLLECTOR_PASSWORD, CollectionScope, collect_page, reconcile_page,
)
from server.knowledge_call_contract import SOURCE_FIELDS, SYNTHETIC_ADAPTER, call_metadata_schema, synthetic_call_contract
from server.knowledge_call_privacy import REDACTION_VERSION
from server.knowledge_call_source import SOURCE_DATABASE, SOURCE_PASSWORD, SOURCE_READER


START = datetime(2026, 10, 1, tzinfo=timezone.utc)
END = START + timedelta(days=30)
CHANGED = END + timedelta(hours=1)


def _insert(db, query, params):
    return db.execute(query, params).fetchone()[0]


def grant_preview_resource_access(db, workspace, source, operator, membership, grantor, *, transcript):
    capabilities = RESOURCE_CAPABILITIES if transcript else RESOURCE_CAPABILITIES - {"representation.read"}
    role_key = "resource-reader" if transcript else "resource-metadata-reader"
    role = db.execute("""SELECT id FROM panadan_knowledge.role_versions
        WHERE workspace_id=%s AND role_key=%s AND rev=1""", (workspace, role_key)).fetchone()
    if role is None:
        role = db.execute("""INSERT INTO panadan_knowledge.role_versions
            (workspace_id,role_key,rev,name,capability_set,state)
            VALUES (%s,%s,1,%s,%s,'active') RETURNING id""",
            (workspace, role_key, "دسترسی کامل منابع" if transcript else "مشخصات منابع",
             Jsonb(sorted(capabilities)))).fetchone()
    db.execute("""INSERT INTO panadan_knowledge.membership_roles
        (workspace_id,membership_id,role_version_id,granted_by) VALUES (%s,%s,%s,%s)""",
        (workspace, membership, role[0], grantor))
    for capability in capabilities:
        db.execute("""INSERT INTO panadan_knowledge.source_scope_grants
            (workspace_id,membership_id,grantor,scope_kind,source_id,operator_scope_id,capability,valid_from)
            VALUES (%s,%s,%s,'operator',%s,%s,%s,clock_timestamp()-interval '1 day')""",
            (workspace, membership, grantor, source, operator, capability))


def seed_preview_resource_scope(db, workspace, operator_key, administrator, regional_reader, *, reader_transcript):
    label = {"operator-a": "گروه رزرو", "operator-b": "گروه پشتیبانی"}[operator_key]
    source = _insert(db, """INSERT INTO panadan_knowledge.sources(workspace_id,source_key,label,connection_ref)
        VALUES (%s,'synthetic-calls','مرکز تماس نمونه','synthetic-calls') RETURNING id""", (workspace,))
    contract = _insert(db, """INSERT INTO panadan_knowledge.source_contract_versions
        (workspace_id,source_id,rev,adapter_version,contract,state)
        VALUES (%s,%s,1,%s,%s,'synthetic') RETURNING id""",
        (workspace, source, SYNTHETIC_ADAPTER, Jsonb(synthetic_call_contract())))
    db.execute("UPDATE panadan_knowledge.sources SET state='active',current_contract_id=%s WHERE workspace_id=%s AND id=%s",
               (contract, workspace, source))
    operator = _insert(db, """INSERT INTO panadan_knowledge.operator_scopes
        (workspace_id,source_id,external_operator_key,label,state) VALUES (%s,%s,%s,%s,'active') RETURNING id""",
        (workspace, source, operator_key, label))
    db.execute("INSERT INTO panadan_knowledge.contract_operator_scopes VALUES (%s,%s,%s,%s)",
               (workspace, source, contract, operator))
    grant_preview_resource_access(db, workspace, source, operator, administrator, administrator, transcript=True)
    if regional_reader is not None:
        grant_preview_resource_access(db, workspace, source, operator, regional_reader, administrator, transcript=reader_transcript)
    subject = uuid4()
    principal = _insert(db, """INSERT INTO panadan_knowledge.principals(authority_namespace,authority_subject,kind,state)
        VALUES (%s,%s,'service','active') RETURNING id""", (COLLECTOR_NAMESPACE, str(subject)))
    worker = _insert(db, """INSERT INTO panadan_knowledge.memberships(workspace_id,principal_id,state)
        VALUES (%s,%s,'active') RETURNING id""", (workspace, principal))
    db.execute("""INSERT INTO panadan_knowledge.source_scope_grants
        (workspace_id,membership_id,grantor,scope_kind,source_id,operator_scope_id,capability,valid_from)
        VALUES (%s,%s,%s,'operator',%s,%s,'source.collect',clock_timestamp()-interval '1 day')""",
        (workspace, worker, administrator, source, operator))
    schema = _insert(db, """INSERT INTO panadan_knowledge.attribute_schema_versions
        (workspace_id,schema_key,rev,json_schema,state) VALUES (%s,'call_metadata',1,%s,'approved') RETURNING id""",
        (workspace, Jsonb(call_metadata_schema())))
    policy_ids = []
    for kind, definition in (("retention", {"days": 30}), ("redaction", {"processor": REDACTION_VERSION})):
        policy_ids.append(_insert(db, """INSERT INTO panadan_knowledge.policy_versions
            (workspace_id,kind,policy_key,rev,definition,state,approved_by,approved_at)
            VALUES (%s,%s,'synthetic',1,%s,'approved',%s,now()) RETURNING id""",
            (workspace, kind, Jsonb(definition), administrator)))
    checkpoint = _insert(db, """INSERT INTO panadan_knowledge.sync_checkpoints
        (workspace_id,source_id,contract_id,operator_scope_id,attribute_schema_id,retention_policy_id,redaction_policy_id,
        event_start,event_end,change_start,change_end)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (workspace, source, contract, operator, schema, *policy_ids, START, END, CHANGED, CHANGED + timedelta(days=1)))
    return CollectionScope(workspace, source, operator, subject, checkpoint)


def _connect(port, database):
    return psycopg.connect(host="127.0.0.1", port=port, dbname=database, user="panadan_ci",
        password="synthetic_ci_password_only", sslmode="disable", connect_timeout=5, autocommit=True)


def collect_preview_resources(port, scopes):
    with _connect(port, "panadan_ci") as db:
        db.execute(f"CREATE ROLE {COLLECTOR_LOGIN} LOGIN NOINHERIT PASSWORD '{COLLECTOR_PASSWORD}'")
        db.execute(f"GRANT CONNECT ON DATABASE panadan_ci TO {COLLECTOR_LOGIN}")
        db.execute(f"GRANT panadan_knowledge_collector TO {COLLECTOR_LOGIN} WITH INHERIT FALSE, SET TRUE")
        db.execute(f"CREATE DATABASE {SOURCE_DATABASE} TEMPLATE template0")
        db.execute(f"CREATE ROLE {SOURCE_READER} LOGIN NOINHERIT PASSWORD '{SOURCE_PASSWORD}'")
        db.execute(f"REVOKE ALL ON DATABASE {SOURCE_DATABASE} FROM PUBLIC")
        db.execute(f"GRANT CONNECT ON DATABASE {SOURCE_DATABASE} TO {SOURCE_READER}")
    with _connect(port, SOURCE_DATABASE) as source:
        source.execute("CREATE SCHEMA panadan_synthetic_source")
        source.execute("""CREATE TABLE panadan_synthetic_source.calls (
            call_id bigint PRIMARY KEY, operator_key text NOT NULL, event_at timestamptz NOT NULL,
            changed_at timestamptz NOT NULL, revision_no bigint NOT NULL, is_deleted boolean NOT NULL,
            duration_seconds integer, transcript text)""")
        source.execute(f"GRANT USAGE ON SCHEMA panadan_synthetic_source TO {SOURCE_READER}")
        source.execute(f"GRANT SELECT ({','.join(SOURCE_FIELDS)}) ON panadan_synthetic_source.calls TO {SOURCE_READER}")
        fixtures = (
            (101, "operator-a", 156, False, "مسافر: برای پرواز صبح به شیراز بلیط رفت‌وبرگشت می‌خواهم.\nاپراتور: شرایط تغییر تاریخ را بررسی می‌کنم. شمارهٔ پیگیری ۰۹۱۲۳۴۵۶۷۸۹ است."),
            (102, "operator-a", 83, False, None),
            (103, "operator-a", None, True, None),
            (104, "operator-a", 94, False, "تماس آزمایشی با دسترسی موقت."),
            (201, "operator-b", 112, False, "مسافر: برای تغییر تاریخ رزرو چه گزینه‌هایی دارم؟"),
        )
        for index, (call_id, operator, duration, deleted, transcript) in enumerate(fixtures):
            source.execute("""INSERT INTO panadan_synthetic_source.calls VALUES (%s,%s,%s,%s,1,%s,%s,%s)""",
                (call_id, operator, START + timedelta(days=index + 1), CHANGED, deleted, duration, transcript))
        for scope in scopes:
            result = collect_page(owned_port=port, source_port=port, scope=scope, enabled=True)
            if not result.finished or result.reason or not result.accepted:
                raise RuntimeError("Synthetic preview collection failed")
        source.execute("UPDATE panadan_synthetic_source.calls SET operator_key='operator-withdrawn' WHERE call_id=104")
        result = reconcile_page(owned_port=port, source_port=port, scope=scopes[0], enabled=True)
        if result.restricted != 1:
            raise RuntimeError("Synthetic preview reconciliation failed")
