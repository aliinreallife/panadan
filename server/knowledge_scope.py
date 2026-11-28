"""M01.3 trusted transaction boundary for the synthetic workspace service.

No general query interface, runtime login provisioning or
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
                         OR rolreplication OR rolbypassrls)""").fetchone() != (2,) or cur.execute("""SELECT EXISTS (
                    SELECT 1 FROM pg_catalog.pg_auth_members m JOIN pg_catalog.pg_roles r ON r.oid=m.member
                    WHERE r.rolname IN ('panadan_knowledge_authorizer','panadan_knowledge_reader'))""").fetchone()[0]:
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
                if operation in ("read_workspace","ui_view"):
                    access = service.authorize(raw,workspace,"workspace.read")
                    page = args[0] if operation == "ui_view" else "overview"
                    required = {"overview":"workspace.read","members":"members.manage","roles":"roles.manage"}[page]
                    if required != "workspace.read":
                        service.authorize(raw,workspace,required)
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
                    if operation == "ui_view":
                        # Fixed, bounded projections under the same locked
                        # workspace transaction. Never expose authority subjects,
                        # policy definitions, raw audit, or unscoped registries.
                        result["capabilities"] = sorted(access.capabilities)
                        result["membership_id"] = access.membership_id
                        result["members"] = []
                        result["roles"] = []
                        result["assignments"] = []
                        result["grants"] = []
                        from psycopg.rows import dict_row
                        with c.cursor(row_factory=dict_row) as view:
                            if page in ("members","roles"):
                                result["members"] = view.execute("""SELECT m.id,m.state,m.created_at,m.revoked_at,
                                    CASE WHEN p.authority_namespace=%s THEN p.authority_subject ELSE NULL END AS label_ref
                                    FROM panadan_knowledge.memberships m JOIN panadan_knowledge.principals p ON p.id=m.principal_id
                                    WHERE m.workspace_id=%s ORDER BY m.created_at,m.id LIMIT 101""",
                                    (identity.namespace,workspace)).fetchall()
                            if page == "roles":
                                result["roles"] = view.execute("""SELECT id,role_key,rev,name,state,capability_set
                                    FROM panadan_knowledge.role_versions WHERE workspace_id=%s
                                    ORDER BY role_key,rev DESC LIMIT 101""",(workspace,)).fetchall()
                                result["assignments"] = view.execute("""SELECT id,membership_id,role_version_id,valid_until,
                                    revoked_at,(revoked_at IS NULL AND (valid_until IS NULL OR valid_until>clock_timestamp())) AS current
                                    FROM panadan_knowledge.membership_roles WHERE workspace_id=%s
                                    ORDER BY created_at,id LIMIT 101""",(workspace,)).fetchall()
                                result["grants"] = view.execute("""SELECT id,membership_id,capability,valid_from,valid_until,revoked_at,
                                    (revoked_at IS NULL AND valid_from<=clock_timestamp()
                                    AND (valid_until IS NULL OR valid_until>clock_timestamp())) AS current
                                    FROM panadan_knowledge.scope_grants WHERE workspace_id=%s
                                    ORDER BY created_at,id LIMIT 101""",(workspace,)).fetchall()
                        result["limited"] = any(len(result[key])>100 for key in ("members","roles","assignments","grants"))
                        for key in ("members","roles","assignments","grants"):
                            result[key] = result[key][:100]
                        # Labels are presentation-only and never expose the
                        # stable authority subjects in the returned projection.
                        names=self._identity._display_names(m["label_ref"] for m in result["members"])
                        for member in result["members"]:
                            member["name"]=names.get(member.pop("label_ref")) or "عضو"
                        result["member_names"]={m["id"]:m["name"] for m in result["members"]}
                        result["role_names"]={r["id"]:r["name"]+" · "+str(r["rev"]) for r in result["roles"]}
                        # Malformed catalog definitions are not rendered as
                        # effective permissions or arbitrary display content.
                        from .knowledge_authorization import _caps
                        for role in result["roles"]:
                            try:
                                _caps(role["capability_set"])
                                role["invalid"]=False
                            except AccessDenied:
                                role["capability_set"]=[]
                                role["invalid"]=True
                        if service.authorize(raw,workspace,required) != access:
                            raise AccessDenied("Access denied")
                        if service.authorize(raw,workspace,"workspace.read") != access:
                            raise AccessDenied("Access denied")
                elif operation == "ui_command":
                    service.authorize(raw,workspace,"workspace.read")
                    result = getattr(service,args[0])(raw,workspace,*args[1:],**kwargs)
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

    def ui_view(self, raw, workspace, page):
        if page not in ("overview","members","roles"):
            raise AccessDenied("Access denied")
        return self._invoke(raw,workspace,"ui_view",(page,),{})

    def ui_command(self, raw, workspace, operation, *args, **kwargs):
        if type(operation) is not str or operation not in _COMMANDS:
            raise AccessDenied("Access denied")
        return self._invoke(raw,workspace,"ui_command",(operation,*args),kwargs)

    def command(self, raw, workspace, operation, *args, **kwargs):
        if type(operation) is not str or operation not in _COMMANDS:
            raise AccessDenied("Access denied")
        return self._invoke(raw,workspace,operation,args,kwargs)
