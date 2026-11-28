-- M01.3: guarded owned PG18 migration, never automatically applied.
-- These are NOLOGIN capability roles; no login membership is provisioned.
-- Context is trusted server state, not a boundary against arbitrary SQL.
DO $guard$
DECLARE rname text;
BEGIN
  IF current_database() NOT IN ('panadan','panadan_ci')
     OR current_setting('server_version_num')::int / 10000 <> 18
     OR current_setting('panadan.knowledge_migration_target',true) IS DISTINCT FROM current_database()
     OR current_user <> session_user
     OR (current_database()='panadan' AND session_user<>'panadan_owner')
     OR (current_database()='panadan_ci' AND session_user<>'panadan_ci')
     OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname=current_user AND rolsuper)
     OR NOT EXISTS (SELECT 1 FROM pg_namespace n JOIN pg_roles r ON r.oid=n.nspowner
          WHERE n.nspname='panadan_knowledge' AND r.rolname='panadan_knowledge_owner'
          AND NOT (r.rolcanlogin OR r.rolinherit OR r.rolsuper OR r.rolcreatedb
                   OR r.rolcreaterole OR r.rolreplication OR r.rolbypassrls))
     OR EXISTS (SELECT 1 FROM pg_auth_members m JOIN pg_roles r
                ON r.oid=m.roleid OR r.oid=m.member WHERE r.rolname='panadan_knowledge_owner')
     OR to_regclass('panadan_knowledge.scope_grants') IS NULL
  THEN RAISE EXCEPTION 'Refusing knowledge RLS migration: review owned target and prior migrations';
  END IF;
  FOREACH rname IN ARRAY ARRAY['panadan_knowledge_authorizer','panadan_knowledge_reader']
  LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname=rname) THEN
      EXECUTE format('CREATE ROLE %I NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS',rname);
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=rname AND
           (rolcanlogin OR rolinherit OR rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls))
       OR EXISTS (SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member OR r.oid=m.roleid
                  WHERE r.rolname=rname)
    THEN RAISE EXCEPTION 'Conflicting runtime role or membership; review manually';
    END IF;
  END LOOP;
END
$guard$;

SET LOCAL ROLE panadan_knowledge_owner;
SET LOCAL search_path=pg_catalog;

-- Return NULL for unset, empty or malformed context. No exception or wildcard.
CREATE OR REPLACE FUNCTION panadan_knowledge.context_uuid(setting_name text)
RETURNS uuid LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog
AS $body$
 SELECT CASE WHEN setting_name IN ('panadan.workspace_id','panadan.target_principal')
     AND current_setting(setting_name,true) ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
     THEN current_setting(setting_name,true)::uuid ELSE NULL END
$body$;
CREATE OR REPLACE FUNCTION panadan_knowledge.scoped_workspace()
RETURNS uuid LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog
AS $body$
 SELECT CASE WHEN nullif(current_setting('panadan.authority_namespace',true),'') IS NOT NULL
       AND nullif(current_setting('panadan.authority_subject',true),'') IS NOT NULL
       THEN panadan_knowledge.context_uuid('panadan.workspace_id') ELSE NULL END
$body$;
REVOKE ALL ON FUNCTION panadan_knowledge.context_uuid(text),panadan_knowledge.scoped_workspace() FROM PUBLIC;
GRANT USAGE ON SCHEMA panadan_knowledge TO panadan_knowledge_authorizer,panadan_knowledge_reader;
GRANT EXECUTE ON FUNCTION panadan_knowledge.context_uuid(text),panadan_knowledge.scoped_workspace()
 TO panadan_knowledge_authorizer,panadan_knowledge_reader;

-- Global catalogs are no longer unrestricted even under ordinary owner access.
ALTER TABLE panadan_knowledge.workspaces ENABLE ROW LEVEL SECURITY;
ALTER TABLE panadan_knowledge.workspaces FORCE ROW LEVEL SECURITY;
ALTER TABLE panadan_knowledge.principals ENABLE ROW LEVEL SECURITY;
ALTER TABLE panadan_knowledge.principals FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS knowledge_workspace_authorizer ON panadan_knowledge.workspaces;
CREATE POLICY knowledge_workspace_authorizer ON panadan_knowledge.workspaces
 FOR ALL TO panadan_knowledge_authorizer
 USING (id=panadan_knowledge.scoped_workspace())
 WITH CHECK (id=panadan_knowledge.scoped_workspace());
DROP POLICY IF EXISTS knowledge_workspace_reader ON panadan_knowledge.workspaces;
CREATE POLICY knowledge_workspace_reader ON panadan_knowledge.workspaces
 FOR SELECT TO panadan_knowledge_reader
 USING (id=panadan_knowledge.scoped_workspace() AND state='active'
        AND current_setting('panadan.read_authorized',true)='yes'
        AND policy_epoch::text=current_setting('panadan.policy_epoch',true));

-- Authorizer sees the verified identity, existing members of this workspace,
-- or the one explicit provisioned target (set only within add_member after
-- members.manage is verified). No unrestricted registry enumeration.
DROP POLICY IF EXISTS knowledge_principal_authorizer ON panadan_knowledge.principals;
CREATE POLICY knowledge_principal_authorizer ON panadan_knowledge.principals
 FOR SELECT TO panadan_knowledge_authorizer
 USING (panadan_knowledge.scoped_workspace() IS NOT NULL AND (
    (authority_namespace=current_setting('panadan.authority_namespace',true)
      AND authority_subject=current_setting('panadan.authority_subject',true))
    OR EXISTS (SELECT 1 FROM panadan_knowledge.memberships m
         WHERE m.workspace_id=panadan_knowledge.scoped_workspace() AND m.principal_id=principals.id)
    OR (id=panadan_knowledge.context_uuid('panadan.target_principal')
        AND authority_namespace=current_setting('panadan.authority_namespace',true))
 ));

DO $policies$
DECLARE t text;
BEGIN
 FOREACH t IN ARRAY ARRAY['memberships','role_versions','membership_roles','scope_grants']
 LOOP
   EXECUTE format('DROP POLICY IF EXISTS knowledge_authorizer_scope ON panadan_knowledge.%I',t);
   EXECUTE format('CREATE POLICY knowledge_authorizer_scope ON panadan_knowledge.%I FOR ALL TO panadan_knowledge_authorizer USING (workspace_id=panadan_knowledge.scoped_workspace()) WITH CHECK (workspace_id=panadan_knowledge.scoped_workspace())',t);
 END LOOP;
END
$policies$;

DROP POLICY IF EXISTS knowledge_audit_append ON panadan_knowledge.audit_events;
CREATE POLICY knowledge_audit_append ON panadan_knowledge.audit_events
 FOR INSERT TO panadan_knowledge_authorizer
 WITH CHECK (workspace_id=panadan_knowledge.scoped_workspace()
   AND channel='web' AND outcome='succeeded' AND safe_metadata='{}'::jsonb
   AND EXISTS (SELECT 1 FROM panadan_knowledge.memberships m JOIN panadan_knowledge.principals p ON p.id=m.principal_id
       WHERE m.workspace_id=audit_events.workspace_id AND m.id=audit_events.membership_id
       AND p.id=audit_events.principal_id AND p.state='active' AND m.state='active'
       AND p.authority_namespace=current_setting('panadan.authority_namespace',true)
       AND p.authority_subject=current_setting('panadan.authority_subject',true))
   AND EXISTS (SELECT 1 FROM panadan_knowledge.workspaces w WHERE w.id=audit_events.workspace_id
       AND w.policy_epoch=audit_events.policy_epoch));

-- No DELETE/TRUNCATE, no principal writes, no policy definition reads,
-- no audit read/update, no schema CREATE and no grant option.
GRANT SELECT (id,state,policy_epoch,lock_version) ON panadan_knowledge.workspaces TO panadan_knowledge_authorizer;
GRANT UPDATE (policy_epoch,lock_version,updated_at) ON panadan_knowledge.workspaces TO panadan_knowledge_authorizer;
GRANT SELECT (id,authority_namespace,authority_subject,kind,state) ON panadan_knowledge.principals TO panadan_knowledge_authorizer;
GRANT SELECT ON panadan_knowledge.memberships,panadan_knowledge.role_versions,
 panadan_knowledge.membership_roles,panadan_knowledge.scope_grants TO panadan_knowledge_authorizer;
GRANT INSERT (workspace_id,principal_id,state,granted_by),
 UPDATE (state,revoked_at,updated_at,lock_version) ON panadan_knowledge.memberships TO panadan_knowledge_authorizer;
GRANT INSERT (workspace_id,role_key,rev,name,capability_set,state),
 UPDATE (state,updated_at,lock_version) ON panadan_knowledge.role_versions TO panadan_knowledge_authorizer;
GRANT INSERT (workspace_id,membership_id,role_version_id,granted_by,valid_until),
 UPDATE (revoked_at,updated_at,lock_version) ON panadan_knowledge.membership_roles TO panadan_knowledge_authorizer;
GRANT INSERT (workspace_id,membership_id,capability,grantor,valid_until),
 UPDATE (revoked_at,updated_at,lock_version) ON panadan_knowledge.scope_grants TO panadan_knowledge_authorizer;
GRANT INSERT (workspace_id,principal_id,membership_id,channel,action,target_kind,target_ref,policy_epoch,outcome,correlation_id)
 ON panadan_knowledge.audit_events TO panadan_knowledge_authorizer;
GRANT SELECT (id,slug,name,state,policy_epoch,timezone) ON panadan_knowledge.workspaces TO panadan_knowledge_reader;

REVOKE ALL ON ALL TABLES IN SCHEMA panadan_knowledge FROM PUBLIC;
REVOKE ALL ON SCHEMA panadan_knowledge FROM PUBLIC;
RESET ROLE;
