"""M01.3 trusted transaction boundary for the synthetic workspace service.

No HTTP endpoints, general query interface, runtime login provisioning or
production connection factory. The caller supplies an idle, dedicated,
autocommit PG18 connection as a restricted login that can SET ROLE to the
two NOLOGIN knowledge roles. Do not share a connection concurrently.
"""
from __future__ import annotations

from psycopg.pq import TransactionStatus
from psycopg.rows import tuple_row

from .knowledge_authorization import AccessDenied, WorkspaceAuthorization, _uuid
from .knowledge_identity import SQLiteIdentityBridge

AUTHOR = "panadan_knowledge_authorizer"
READER = "panadan_knowledge_reader"
_SETTINGS = (
    "panadan.workspace_id", "panadan.authority_namespace", "panadan.authority_subject",
    "panadan.target_principal", "panadan.read_authorized", "panadan.policy_epoch",
)
_COMMANDS = frozenset({
    "create_role", "add_member", "assign_role", "grant_scope", "revoke_membership",
    "revoke_role", "revoke_scope", "retire_role",
})


class ScopedWorkspace:
    """Fixed service operations, never caller-provided SQL/callbacks.

    RLS is defense in depth against missing workspace predicates, not a
    defense against SQL injection or an attacker with the trusted DB login.
    Only this internal boundary may establish scope. No client can choose
    a DB role, principal, epoch, context value or command implementation.
    """
    def __init__(self, connection, identity: SQLiteIdentityBridge, *, enabled=False):
        if enabled is not True or type(identity) is not SQLiteIdentityBridge:
            raise AccessDenied("Access denied")
        self._conn = connection
        self._identity = identity

    def _clean(self):
        c = self._conn
        if c.closed or not c.autocommit or c.info.transaction_status != TransactionStatus.IDLE:
            # Never borrow an active transaction or commit a caller's work.
            raise AccessDenied("Access denied")
        with c.cursor(row_factory=tuple_row) as cur:
            row = cur.execute("""SELECT current_database(),
                current_setting('server_version_num')::int / 10000,
                current_user=session_user,
                NOT (r.rolsuper OR r.rolinherit OR r.rolcreatedb OR r.rolcreaterole
                     OR r.rolreplication OR r.rolbypassrls),
                pg_has_role(session_user,'panadan_knowledge_authorizer','MEMBER'),
                pg_has_role(session_user,'panadan_knowledge_reader','MEMBER'),
                pg_has_role(session_user,'panadan_knowledge_owner','MEMBER')
                FROM pg_catalog.pg_roles r WHERE r.rolname=session_user""").fetchone()
            # Synthetic-only activation; actual deployment requires a reviewed
            # login and privilege inventory and a separate authorization.
            if row != ("panadan_ci",18,True,True,True,True,False):
                c.close()
                raise AccessDenied("Access denied")
            memberships = cur.execute("""SELECT parent.rolname,m.admin_option,m.inherit_option,m.set_option
                FROM pg_catalog.pg_auth_members m
                JOIN pg_catalog.pg_roles parent ON parent.oid=m.roleid
                JOIN pg_catalog.pg_roles child ON child.oid=m.member
                WHERE child.rolname=session_user""").fetchall()
            if (set(memberships) != {(AUTHOR,False,False,True),(READER,False,False,True)}
                    or cur.execute("SELECT has_schema_privilege(session_user,'panadan_knowledge','USAGE')").fetchone()[0]):
                c.close()
                raise AccessDenied("Access denied")
            if cur.execute("""SELECT count(*) FROM pg_catalog.pg_roles
                WHERE rolname IN ('panadan_knowledge_authorizer','panadan_knowledge_reader')
                AND NOT (rolcanlogin OR rolinherit OR rolsuper OR rolcreatedb OR rolcreaterole
                         OR rolreplication OR rolbypassrls)""").fetchone() != (2,):
                c.close()
                raise AccessDenied("Access denied")
            if any(cur.execute("SELECT current_setting(%s,true)",(key,)).fetchone()[0]
                   not in (None,"") for key in _SETTINGS):
                # Never reuse a connection carrying session-level identity.
                c.close()
                raise AccessDenied("Access denied")

    def _invoke(self, raw, workspace, operation, args, kwargs):
        _uuid(workspace)
        identity = self._identity.resolve_session(raw)
        if identity is None:
            raise AccessDenied("Access denied")
        c = self._conn
        # An active caller-owned transaction is rejected without committing
        # or rolling it back. Invalid idle connections are discarded.
        if c.closed or not c.autocommit or c.info.transaction_status != TransactionStatus.IDLE:
            raise AccessDenied("Access denied")
        try:
            self._clean()
        except BaseException:
            c.close()
            raise
        try:
            with c.transaction(), c.cursor(row_factory=tuple_row) as cur:
                cur.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
                cur.execute("SET LOCAL search_path=pg_catalog")
                cur.execute("SET LOCAL row_security=on")
                cur.execute("SET LOCAL lock_timeout='5s'")
                cur.execute("SET LOCAL statement_timeout='10s'")
                cur.execute("SET LOCAL ROLE panadan_knowledge_authorizer")
                # Establish candidate scope after verifying current identity.
                # Workspace selection alone never authorizes an operation.
                for key,value in zip(_SETTINGS,(str(workspace),identity.namespace,identity.subject,"","",""),strict=True):
                    cur.execute("SELECT set_config(%s,%s,true)",(key,value))
                service = WorkspaceAuthorization(c,self._identity)
                if operation == "read_workspace":
                    access = service.authorize(raw,workspace,"workspace.read")
                    cur.execute("SELECT set_config('panadan.policy_epoch',%s,true)",(str(access.policy_epoch),))
                    cur.execute("SELECT set_config('panadan.read_authorized','yes',true)")
                    cur.execute("SET LOCAL ROLE panadan_knowledge_reader")
                    row = cur.execute("""SELECT id,slug,name,state,policy_epoch,timezone
                        FROM panadan_knowledge.workspaces WHERE id=%s""",(workspace,)).fetchone()
                    if row is None:
                        raise AccessDenied("Access denied")
                    cur.execute("SET LOCAL ROLE panadan_knowledge_authorizer")
                    current = service.authorize(raw,workspace,"workspace.read")
                    if current != access:
                        raise AccessDenied("Access denied")
                    result = dict(zip(("id","slug","name","state","policy_epoch","timezone"),row,strict=True))
                elif operation == "authorize":
                    result = service.authorize(raw,workspace,*args,**kwargs)
                elif operation in _COMMANDS:
                    result = getattr(service,operation)(raw,workspace,*args,**kwargs)
                else:
                    raise AccessDenied("Access denied")
                if self._identity.resolve_session(raw) != identity:
                    raise AccessDenied("Access denied")
            return result
        finally:
            # SET LOCAL unwinds on commit and rollback, including nested
            # savepoints. Reject/close on any residual session scope or error.
            if not c.closed:
                try:
                    self._clean()
                except BaseException:
                    c.close()
                    raise

    def authorize(self, raw, workspace, capability):
        return self._invoke(raw,workspace,"authorize",(capability,),{})

    def read_workspace(self, raw, workspace):
        return self._invoke(raw,workspace,"read_workspace",(),{})

    def command(self, raw, workspace, operation, *args, **kwargs):
        if type(operation) is not str or operation not in _COMMANDS:
            raise AccessDenied("Access denied")
        return self._invoke(raw,workspace,operation,args,kwargs)
