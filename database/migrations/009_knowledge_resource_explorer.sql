-- M02.5 guarded browser projections. Authorizer locks grants; reader sees
-- only the workspace, operator and data class selected by current authority.
DO $guard$
BEGIN
  IF current_database() NOT IN ('panadan','panadan_ci')
     OR current_setting('server_version_num')::int / 10000 <> 18
     OR current_setting('panadan.knowledge_migration_target',true) IS DISTINCT FROM current_database()
     OR current_user <> session_user
     OR (current_database()='panadan' AND session_user<>'panadan_owner')
     OR (current_database()='panadan_ci' AND session_user<>'panadan_ci')
     OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname=current_user AND rolsuper)
     OR NOT EXISTS (
         SELECT 1 FROM pg_namespace n JOIN pg_roles r ON r.oid=n.nspowner
         WHERE n.nspname='panadan_knowledge' AND r.rolname='panadan_knowledge_owner'
           AND NOT (r.rolcanlogin OR r.rolinherit OR r.rolsuper OR r.rolcreatedb
                    OR r.rolcreaterole OR r.rolreplication OR r.rolbypassrls))
     OR EXISTS (SELECT 1 FROM pg_auth_members m JOIN pg_roles r
                ON r.oid=m.roleid OR r.oid=m.member WHERE r.rolname='panadan_knowledge_owner')
     OR to_regclass('panadan_knowledge.sync_runs') IS NULL
  THEN RAISE EXCEPTION 'Refusing resource explorer migration: review owned target and prior migrations';
  END IF;
END
$guard$;

SET LOCAL ROLE panadan_knowledge_owner;
SET LOCAL search_path=pg_catalog;

-- Narrow SELECT and FOR SHARE authority for the current human's own grants.
DROP POLICY IF EXISTS source_grant_authorizer ON panadan_knowledge.source_scope_grants;
CREATE POLICY source_grant_authorizer ON panadan_knowledge.source_scope_grants
  FOR SELECT TO panadan_knowledge_authorizer USING (
    workspace_id=panadan_knowledge.scoped_workspace() AND capability<>'source.collect' AND
    EXISTS (SELECT 1 FROM panadan_knowledge.memberships m JOIN panadan_knowledge.principals p ON p.id=m.principal_id
      WHERE m.workspace_id=source_scope_grants.workspace_id AND m.id=source_scope_grants.membership_id
        AND m.state='active' AND m.revoked_at IS NULL AND p.state='active' AND p.kind='human'
        AND p.authority_namespace=current_setting('panadan.authority_namespace',true)
        AND p.authority_subject=current_setting('panadan.authority_subject',true)));
DROP POLICY IF EXISTS source_grant_authorizer_lock ON panadan_knowledge.source_scope_grants;
CREATE POLICY source_grant_authorizer_lock ON panadan_knowledge.source_scope_grants
  FOR UPDATE TO panadan_knowledge_authorizer USING (
    workspace_id=panadan_knowledge.scoped_workspace() AND capability<>'source.collect' AND
    EXISTS (SELECT 1 FROM panadan_knowledge.memberships m JOIN panadan_knowledge.principals p ON p.id=m.principal_id
      WHERE m.workspace_id=source_scope_grants.workspace_id AND m.id=source_scope_grants.membership_id
        AND m.state='active' AND m.revoked_at IS NULL AND p.state='active' AND p.kind='human'
        AND p.authority_namespace=current_setting('panadan.authority_namespace',true)
        AND p.authority_subject=current_setting('panadan.authority_subject',true))) WITH CHECK (false);
GRANT SELECT (id,workspace_id,membership_id,capability,valid_from,valid_until,revoked_at), UPDATE (id)
  ON panadan_knowledge.source_scope_grants TO panadan_knowledge_authorizer;

CREATE OR REPLACE FUNCTION panadan_knowledge.resource_member()
RETURNS uuid LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $body$
 SELECT CASE WHEN current_setting('panadan.read_authorized',true)='yes'
    AND current_setting('panadan.resource_member',true) ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    AND EXISTS (SELECT 1 FROM panadan_knowledge.workspaces w WHERE w.id=panadan_knowledge.scoped_workspace())
    THEN current_setting('panadan.resource_member',true)::uuid ELSE NULL END
$body$;

DROP POLICY IF EXISTS source_grant_reader ON panadan_knowledge.source_scope_grants;
CREATE POLICY source_grant_reader ON panadan_knowledge.source_scope_grants
  FOR SELECT TO panadan_knowledge_reader USING (
    workspace_id=panadan_knowledge.scoped_workspace() AND membership_id=panadan_knowledge.resource_member()
    AND capability IN ('resource.list','resource.read','representation.read')
    AND capability=ANY(string_to_array(current_setting('panadan.resource_capabilities',true),','))
    AND revoked_at IS NULL AND valid_from<=clock_timestamp() AND (valid_until IS NULL OR valid_until>clock_timestamp()));
GRANT SELECT (workspace_id,source_id,operator_scope_id,scope_kind,capability)
  ON panadan_knowledge.source_scope_grants TO panadan_knowledge_reader;

CREATE OR REPLACE FUNCTION panadan_knowledge.resource_granted(source uuid, operator_scope uuid, permission text)
RETURNS boolean LANGUAGE sql VOLATILE SECURITY INVOKER SET search_path=pg_catalog AS $body$
 SELECT EXISTS (SELECT 1 FROM panadan_knowledge.source_scope_grants g
   WHERE g.workspace_id=panadan_knowledge.scoped_workspace() AND g.source_id=source AND g.capability=permission
     AND (operator_scope IS NULL OR g.scope_kind='source' OR g.operator_scope_id=operator_scope))
$body$;
REVOKE ALL ON FUNCTION panadan_knowledge.resource_member(),panadan_knowledge.resource_granted(uuid,uuid,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION panadan_knowledge.resource_member(),panadan_knowledge.resource_granted(uuid,uuid,text)
  TO panadan_knowledge_reader;

DROP POLICY IF EXISTS resource_explorer_sources ON panadan_knowledge.sources;
CREATE POLICY resource_explorer_sources ON panadan_knowledge.sources FOR SELECT TO panadan_knowledge_reader USING (
  workspace_id=panadan_knowledge.scoped_workspace() AND
  (panadan_knowledge.resource_granted(id,NULL,'resource.list') OR panadan_knowledge.resource_granted(id,NULL,'resource.read')));
DROP POLICY IF EXISTS resource_explorer_contracts ON panadan_knowledge.source_contract_versions;
CREATE POLICY resource_explorer_contracts ON panadan_knowledge.source_contract_versions FOR SELECT TO panadan_knowledge_reader USING (
  workspace_id=panadan_knowledge.scoped_workspace() AND panadan_knowledge.resource_granted(source_id,NULL,'resource.list'));
DROP POLICY IF EXISTS resource_explorer_operators ON panadan_knowledge.operator_scopes;
CREATE POLICY resource_explorer_operators ON panadan_knowledge.operator_scopes FOR SELECT TO panadan_knowledge_reader USING (
  workspace_id=panadan_knowledge.scoped_workspace() AND
  (panadan_knowledge.resource_granted(source_id,id,'resource.list') OR panadan_knowledge.resource_granted(source_id,id,'resource.read')));
DROP POLICY IF EXISTS resource_explorer_checkpoints ON panadan_knowledge.sync_checkpoints;
CREATE POLICY resource_explorer_checkpoints ON panadan_knowledge.sync_checkpoints FOR SELECT TO panadan_knowledge_reader USING (
  workspace_id=panadan_knowledge.scoped_workspace() AND panadan_knowledge.resource_granted(source_id,operator_scope_id,'resource.list'));
DROP POLICY IF EXISTS resource_explorer_runs ON panadan_knowledge.sync_runs;
CREATE POLICY resource_explorer_runs ON panadan_knowledge.sync_runs FOR SELECT TO panadan_knowledge_reader USING (
  workspace_id=panadan_knowledge.scoped_workspace() AND EXISTS (
    SELECT 1 FROM panadan_knowledge.sync_checkpoints c WHERE c.workspace_id=sync_runs.workspace_id AND c.id=sync_runs.checkpoint_id));

DROP POLICY IF EXISTS resource_explorer_revisions ON panadan_knowledge.resource_revisions;
CREATE POLICY resource_explorer_revisions ON panadan_knowledge.resource_revisions FOR SELECT TO panadan_knowledge_reader USING (
  workspace_id=panadan_knowledge.scoped_workspace()
  AND (panadan_knowledge.resource_granted(source_id,operator_scope_id,'resource.list')
    OR panadan_knowledge.resource_granted(source_id,operator_scope_id,'resource.read'))
  AND EXISTS (SELECT 1 FROM panadan_knowledge.sources s WHERE s.workspace_id=resource_revisions.workspace_id
    AND s.id=resource_revisions.source_id AND s.state='active')
  AND EXISTS (SELECT 1 FROM panadan_knowledge.operator_scopes o WHERE o.workspace_id=resource_revisions.workspace_id
    AND o.id=resource_revisions.operator_scope_id AND o.state='active'));
DROP POLICY IF EXISTS resource_explorer_resources ON panadan_knowledge.resources;
CREATE POLICY resource_explorer_resources ON panadan_knowledge.resources FOR SELECT TO panadan_knowledge_reader USING (
  workspace_id=panadan_knowledge.scoped_workspace() AND EXISTS (
    SELECT 1 FROM panadan_knowledge.resource_revisions v WHERE v.workspace_id=resources.workspace_id
      AND v.id=resources.current_revision_id AND v.resource_id=resources.id));
DROP POLICY IF EXISTS resource_explorer_transcript ON panadan_knowledge.representations;
CREATE POLICY resource_explorer_transcript ON panadan_knowledge.representations FOR SELECT TO panadan_knowledge_reader USING (
  workspace_id=panadan_knowledge.scoped_workspace() AND availability='active'
  AND (expires_at IS NULL OR expires_at>clock_timestamp()) AND EXISTS (
   SELECT 1 FROM panadan_knowledge.resource_revisions v JOIN panadan_knowledge.resources r
     ON r.workspace_id=v.workspace_id AND r.id=v.resource_id AND r.current_revision_id=v.id
   WHERE v.workspace_id=representations.workspace_id AND v.id=representations.resource_revision_id
     AND v.availability='active' AND r.availability='active'
     AND panadan_knowledge.resource_granted(v.source_id,v.operator_scope_id,'resource.read')
     AND panadan_knowledge.resource_granted(v.source_id,v.operator_scope_id,'representation.read')));

GRANT SELECT (workspace_id,id,source_key,label,state,current_contract_id)
  ON panadan_knowledge.sources TO panadan_knowledge_reader;
GRANT SELECT (workspace_id,id,source_id,rev,adapter_version,state)
  ON panadan_knowledge.source_contract_versions TO panadan_knowledge_reader;
GRANT SELECT (workspace_id,id,source_id,external_operator_key,label,state)
  ON panadan_knowledge.operator_scopes TO panadan_knowledge_reader;
GRANT SELECT (workspace_id,id,source_id,contract_id,operator_scope_id,event_start,event_end,finished)
  ON panadan_knowledge.sync_checkpoints TO panadan_knowledge_reader;
GRANT SELECT (workspace_id,checkpoint_id,state,examined,accepted,unchanged,excluded,reason_code,created_at)
  ON panadan_knowledge.sync_runs TO panadan_knowledge_reader;
GRANT SELECT (workspace_id,id,source_id,external_id,current_revision_id,availability)
  ON panadan_knowledge.resources TO panadan_knowledge_reader;
GRANT SELECT (workspace_id,id,source_id,resource_id,operator_scope_id,rev,event_at,observed_at,
    operation,normalized_metadata,availability,transcript_outcome)
  ON panadan_knowledge.resource_revisions TO panadan_knowledge_reader;
GRANT SELECT (workspace_id,resource_revision_id,representation_rev,text_payload,expires_at)
  ON panadan_knowledge.representations TO panadan_knowledge_reader;
RESET ROLE;
