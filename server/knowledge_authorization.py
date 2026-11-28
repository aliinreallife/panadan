"""M01.2 workspace authorization commands; not wired to HTTP or workers.

Uses a caller-managed owned PG transaction/connection. M01.3 must provide
the narrow trusted role/context; no runtime grants or production DSN here.
Only operational workspace administration via current SQLite browser session
is supported. Data, source, API/MCP and service grants remain denied.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4
import re

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .knowledge_identity import SQLiteIdentityBridge

CAPABILITIES = frozenset({"workspace.read", "members.manage", "roles.manage"})
ROLE_TEMPLATES = {
    "workspace_reader": ("workspace.read",),
    "workspace_administrator": ("workspace.read", "members.manage", "roles.manage"),
}
PURPOSE = "workspace_administration"


class AccessDenied(Exception):
    """Uniform denial; no tenant or principal existence details."""


def _caps(value) -> frozenset[str]:
    if (not isinstance(value, list) or any(type(x) is not str or x not in CAPABILITIES for x in value)
            or len(set(value)) != len(value)):
        raise AccessDenied("Access denied")
    return frozenset(value)


def _uuid(value) -> UUID:
    if not isinstance(value, UUID) or not value.int:
        raise AccessDenied("Access denied")
    return value


def _earliest(a, b):
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)


def _latest(a, b):
    if a is None or b is None:
        return None
    return max(a, b)


@dataclass(frozen=True, slots=True)
class WorkspaceAccess:
    workspace_id: UUID
    principal_id: UUID
    membership_id: UUID
    policy_epoch: int
    capabilities: frozenset[str]


class WorkspaceAuthorization:
    def __init__(self, connection, identity: SQLiteIdentityBridge):
        if type(identity) is not SQLiteIdentityBridge:
            raise ValueError("Verified SQLite identity adapter required")
        self._conn = connection
        self._identity = identity

    def _current(self, raw):
        identity = self._identity.resolve_session(raw)
        if identity is None:
            raise AccessDenied("Access denied")
        return identity

    def _load(self, cur, workspace, identity):
        _uuid(workspace)
        # Every command and check locks the workspace before reading grants.
        # All policy mutations in this service use this same serialization point.
        w = cur.execute("""SELECT id,state,policy_epoch FROM panadan_knowledge.workspaces
                         WHERE id=%s FOR UPDATE""", (workspace,)).fetchone()
        if not w or w["state"] != "active":
            raise AccessDenied("Access denied")
        now = cur.execute("SELECT clock_timestamp() AS t").fetchone()["t"]
        m = cur.execute("""SELECT m.id,m.principal_id
            FROM panadan_knowledge.memberships m JOIN panadan_knowledge.principals p ON p.id=m.principal_id
            WHERE m.workspace_id=%s AND m.state='active' AND m.revoked_at IS NULL
              AND p.state='active' AND p.kind='human' AND p.authority_namespace=%s AND p.authority_subject=%s""",
            (workspace,identity.namespace,identity.subject)).fetchone()
        if not m:
            raise AccessDenied("Access denied")
        roles = cur.execute("""SELECT r.capability_set,a.valid_until
            FROM panadan_knowledge.membership_roles a JOIN panadan_knowledge.role_versions r
              ON (r.workspace_id,r.id)=(a.workspace_id,a.role_version_id)
            WHERE a.workspace_id=%s AND a.membership_id=%s AND a.revoked_at IS NULL
              AND r.state='active' AND (a.valid_until IS NULL OR a.valid_until>%s)""",
            (workspace,m["id"],now)).fetchall()
        ceiling = {}
        for role in roles:
            for cap in _caps(role["capability_set"]):
                deadline = role["valid_until"]
                ceiling[cap] = _latest(ceiling[cap],deadline) if cap in ceiling else deadline
        grants = cur.execute("""SELECT capability,valid_until FROM panadan_knowledge.scope_grants
            WHERE workspace_id=%s AND membership_id=%s AND revoked_at IS NULL
            AND scope_kind='workspace' AND data_class='operational' AND purpose=%s
            AND valid_from<=%s AND (valid_until IS NULL OR valid_until>%s)""",
            (workspace,m["id"],PURPOSE,now,now)).fetchall()
        effective = {g["capability"]: _earliest(ceiling[g["capability"]],g["valid_until"])
                     for g in grants if g["capability"] in ceiling}
        access = WorkspaceAccess(workspace,m["principal_id"],m["id"],w["policy_epoch"],frozenset(effective))
        return access,effective,now

    def authorize(self, raw, workspace: UUID, capability: str, *,
                  channel: str = "web", purpose: str = PURPOSE,
                  data_class: str = "operational") -> WorkspaceAccess:
        """Fresh check, not a reusable credential. No data or external access."""
        if (type(capability) is not str or capability not in CAPABILITIES
                or channel != "web" or purpose != PURPOSE or data_class != "operational"):
            raise AccessDenied("Access denied")
        identity = self._current(raw)
        with self._conn.transaction(), self._conn.cursor(row_factory=dict_row) as cur:
            access,effective,_ = self._load(cur,workspace,identity)
            if capability not in access.capabilities or self._current(raw) != identity:
                raise AccessDenied("Access denied")
            now = cur.execute("SELECT clock_timestamp() AS t").fetchone()["t"]
            if effective[capability] is not None and effective[capability] <= now:
                raise AccessDenied("Access denied")
            return access

    @staticmethod
    def _delegate(effective, required, capabilities, until, now):
        if until is not None and (not isinstance(until, datetime) or until.tzinfo is None or until <= now):
            raise AccessDenied("Access denied")
        for cap in set(capabilities) | {required}:
            if cap not in effective:
                raise AccessDenied("Access denied")
            deadline = effective[cap]
            if deadline is not None and (until is None or until > deadline):
                raise AccessDenied("Access denied")

    @staticmethod
    def _target(cur, workspace, member, actor, *, require_active_principal=True):
        _uuid(member)
        if member == actor:
            raise AccessDenied("Access denied")
        if not cur.execute("""SELECT 1 FROM panadan_knowledge.memberships m
            JOIN panadan_knowledge.principals p ON p.id=m.principal_id
            WHERE m.workspace_id=%s AND m.id=%s AND m.state='active'
            AND m.revoked_at IS NULL AND (NOT %s OR p.state='active')""",
            (workspace,member,require_active_principal)).fetchone():
            raise AccessDenied("Access denied")

    def _change(self, raw, workspace, required, action, target_kind, operation):
        identity = self._current(raw)
        with self._conn.transaction(), self._conn.cursor(row_factory=dict_row) as cur:
            access,effective,now = self._load(cur,workspace,identity)
            if required not in effective:
                raise AccessDenied("Access denied")
            target = operation(cur,access,effective,now)
            # Separate auth stores cannot be atomically committed together.
            # Recheck current session before publishing any local change. M01.3+
            # must recheck at actual dispatch/read boundaries; never cache this.
            if self._current(raw) != identity:
                raise AccessDenied("Access denied")
            checked_at = cur.execute("SELECT clock_timestamp() AS t").fetchone()["t"]
            # Conservative: if any effective authorization expires during a
            # command, roll back instead of extending a stale delegation.
            if any(deadline is not None and deadline <= checked_at for deadline in effective.values()):
                raise AccessDenied("Access denied")
            epoch = cur.execute("""UPDATE panadan_knowledge.workspaces
                SET policy_epoch=policy_epoch+1,lock_version=lock_version+1,updated_at=clock_timestamp()
                WHERE id=%s RETURNING policy_epoch""",(workspace,)).fetchone()["policy_epoch"]
            cur.execute("""INSERT INTO panadan_knowledge.audit_events
                (workspace_id,principal_id,membership_id,channel,action,target_kind,target_ref,
                 policy_epoch,outcome,correlation_id)
                VALUES (%s,%s,%s,'web',%s,%s,%s,%s,'succeeded',%s)""",
                (workspace,access.principal_id,access.membership_id,action,target_kind,str(target),epoch,uuid4()))
            return target

    def create_role(self, raw, workspace, role_key, name, capabilities):
        caps = _caps(capabilities)
        if (not isinstance(role_key,str) or not re.fullmatch(r"[a-z][a-z0-9_.-]{0,79}",role_key)
                or not isinstance(name,str) or not 1 <= len(name) <= 160 or not name.strip()):
            raise AccessDenied("Access denied")
        def op(cur,a,e,now):
            if not caps <= a.capabilities:
                raise AccessDenied("Access denied")
            rev=cur.execute("""SELECT coalesce(max(rev),0)+1 AS rev FROM panadan_knowledge.role_versions
                WHERE workspace_id=%s AND role_key=%s""",(workspace,role_key)).fetchone()["rev"]
            return cur.execute("""INSERT INTO panadan_knowledge.role_versions
                (workspace_id,role_key,rev,name,capability_set,state)
                VALUES (%s,%s,%s,%s,%s,'active') RETURNING id""",
                (workspace,role_key,rev,name,Jsonb(sorted(caps)))).fetchone()["id"]
        return self._change(raw,workspace,"roles.manage","role.publish","role_version",op)

    def add_member(self, raw, workspace, principal):
        _uuid(principal)
        def op(cur,a,e,now):
            if principal == a.principal_id or not cur.execute("""SELECT 1 FROM panadan_knowledge.principals
                WHERE id=%s AND state='active' AND kind='human'""",(principal,)).fetchone():
                raise AccessDenied("Access denied")
            # Registry is provisioned separately; no automatic principal binding
            # or legacy role assignment. Revoked membership is not reactivated.
            row=cur.execute("""INSERT INTO panadan_knowledge.memberships
                (workspace_id,principal_id,state,granted_by) VALUES (%s,%s,'active',%s)
                ON CONFLICT(workspace_id,principal_id) DO NOTHING RETURNING id""",
                (workspace,principal,a.principal_id)).fetchone()
            if not row:
                raise AccessDenied("Access denied")
            return row["id"]
        return self._change(raw,workspace,"members.manage","membership.add","membership",op)

    def assign_role(self, raw, workspace, member, role, *, valid_until=None):
        _uuid(role)
        def op(cur,a,e,now):
            self._target(cur,workspace,member,a.membership_id)
            row=cur.execute("""SELECT capability_set FROM panadan_knowledge.role_versions
                WHERE workspace_id=%s AND id=%s AND state='active'""",(workspace,role)).fetchone()
            if not row:
                raise AccessDenied("Access denied")
            self._delegate(e,"roles.manage",_caps(row["capability_set"]),valid_until,now)
            result=cur.execute("""INSERT INTO panadan_knowledge.membership_roles
                (workspace_id,membership_id,role_version_id,granted_by,valid_until)
                VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id""",
                (workspace,member,role,a.membership_id,valid_until)).fetchone()
            if not result:
                raise AccessDenied("Access denied")
            return result["id"]
        return self._change(raw,workspace,"roles.manage","role.assign","membership_role",op)

    def grant_scope(self, raw, workspace, member, capability, *, valid_until=None):
        if type(capability) is not str or capability not in CAPABILITIES:
            raise AccessDenied("Access denied")
        def op(cur,a,e,now):
            self._target(cur,workspace,member,a.membership_id)
            self._delegate(e,"roles.manage",{capability},valid_until,now)
            row=cur.execute("""INSERT INTO panadan_knowledge.scope_grants
                (workspace_id,membership_id,capability,grantor,valid_until)
                VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id""",
                (workspace,member,capability,a.membership_id,valid_until)).fetchone()
            if not row:
                raise AccessDenied("Access denied")
            return row["id"]
        return self._change(raw,workspace,"roles.manage","scope.grant","scope_grant",op)

    def revoke_membership(self, raw, workspace, member):
        def op(cur,a,e,now):
            self._target(cur,workspace,member,a.membership_id,require_active_principal=False)
            cur.execute("""UPDATE panadan_knowledge.memberships SET state='revoked',revoked_at=%s,
                updated_at=%s,lock_version=lock_version+1 WHERE workspace_id=%s AND id=%s""",
                (now,now,workspace,member))
            for table in ("membership_roles","scope_grants"):
                # Fixed internal table names, never request-provided.
                cur.execute("UPDATE panadan_knowledge."+table+
                    " SET revoked_at=%s,updated_at=%s,lock_version=lock_version+1"
                    " WHERE workspace_id=%s AND membership_id=%s AND revoked_at IS NULL",
                    (now,now,workspace,member))
            return member
        return self._change(raw,workspace,"members.manage","membership.revoke","membership",op)

    def _revoke(self, raw, workspace, assignment, table, action):
        _uuid(assignment)
        def op(cur,a,e,now):
            row=cur.execute("SELECT membership_id FROM panadan_knowledge."+table+
                " WHERE workspace_id=%s AND id=%s AND revoked_at IS NULL",(workspace,assignment)).fetchone()
            if not row:
                raise AccessDenied("Access denied")
            self._target(cur,workspace,row["membership_id"],a.membership_id,require_active_principal=False)
            cur.execute("UPDATE panadan_knowledge."+table+
                " SET revoked_at=%s,updated_at=%s,lock_version=lock_version+1 WHERE workspace_id=%s AND id=%s",
                (now,now,workspace,assignment))
            return assignment
        return self._change(raw,workspace,"roles.manage",action,table,op)

    def revoke_role(self, raw, workspace, assignment):
        return self._revoke(raw,workspace,assignment,"membership_roles","role.revoke")

    def revoke_scope(self, raw, workspace, grant):
        return self._revoke(raw,workspace,grant,"scope_grants","scope.revoke")

    def retire_role(self, raw, workspace, role):
        _uuid(role)
        def op(cur,a,e,now):
            row=cur.execute("""UPDATE panadan_knowledge.role_versions SET state='retired',
                updated_at=%s,lock_version=lock_version+1 WHERE workspace_id=%s AND id=%s AND state='active'
                RETURNING id""",(now,workspace,role)).fetchone()
            if not row:
                raise AccessDenied("Access denied")
            return role
        return self._change(raw,workspace,"roles.manage","role.retire","role_version",op)
