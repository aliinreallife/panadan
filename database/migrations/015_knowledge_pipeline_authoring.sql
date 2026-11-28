-- Pipeline-only authoring role. Membership is provisioned separately.
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
     OR to_regprocedure('panadan_knowledge.objective_author_workspace()') IS NULL
  THEN RAISE EXCEPTION 'Refusing pipeline authoring migration: review owned target and prior migrations';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='panadan_knowledge_pipeline_author') THEN
    CREATE ROLE panadan_knowledge_pipeline_author NOLOGIN NOINHERIT NOSUPERUSER
      NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='panadan_knowledge_pipeline_author'
      AND (rolcanlogin OR rolinherit OR rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls))
     OR EXISTS (SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member OR r.oid=m.roleid
                WHERE r.rolname='panadan_knowledge_pipeline_author')
  THEN RAISE EXCEPTION 'Conflicting pipeline author role or membership; review manually';
  END IF;
END
$guard$;
SET LOCAL ROLE panadan_knowledge_owner;
SET LOCAL search_path=pg_catalog;

CREATE OR REPLACE FUNCTION panadan_knowledge.pipeline_author_member()
RETURNS uuid LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $body$
 SELECT CASE WHEN panadan_knowledge.scoped_workspace() IS NOT NULL
    AND current_setting('panadan.pipeline_author_member',true) ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    THEN current_setting('panadan.pipeline_author_member',true)::uuid ELSE NULL END
$body$;
CREATE OR REPLACE FUNCTION panadan_knowledge.pipeline_author_workspace()
RETURNS uuid LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $body$
 SELECT CASE WHEN panadan_knowledge.pipeline_author_member() IS NOT NULL
        THEN panadan_knowledge.scoped_workspace() ELSE NULL END
$body$;
CREATE OR REPLACE FUNCTION panadan_knowledge.pipeline_author_source(source uuid, operator_scope uuid)
RETURNS boolean LANGUAGE sql VOLATILE SECURITY INVOKER SET search_path=pg_catalog AS $body$
 SELECT EXISTS (SELECT 1 FROM panadan_knowledge.source_scope_grants g
   WHERE g.workspace_id=panadan_knowledge.pipeline_author_workspace() AND g.source_id=source
     AND (operator_scope IS NULL OR g.scope_kind='source' OR g.operator_scope_id=operator_scope))
$body$;
REVOKE ALL ON FUNCTION panadan_knowledge.pipeline_author_member(),panadan_knowledge.pipeline_author_workspace(),
  panadan_knowledge.pipeline_author_source(uuid,uuid) FROM PUBLIC;
GRANT USAGE ON SCHEMA panadan_knowledge TO panadan_knowledge_pipeline_author;
GRANT EXECUTE ON FUNCTION panadan_knowledge.context_uuid(text),panadan_knowledge.scoped_workspace(),
  panadan_knowledge.pipeline_author_member(),panadan_knowledge.pipeline_author_workspace(),
  panadan_knowledge.pipeline_author_source(uuid,uuid) TO panadan_knowledge_pipeline_author;

DO $policies$
DECLARE binding record;
BEGIN
  FOR binding IN SELECT * FROM (VALUES
    ('objectives','true'),
    ('objective_versions',$q$input_kind='filtered_call' AND state='active'$q$),
    ('policy_versions',$q$kind='validation' AND state='approved'$q$),
    ('sources',$q$state='active' AND panadan_knowledge.pipeline_author_source(id,NULL)$q$),
    ('source_contract_versions',$q$state='synthetic' AND panadan_knowledge.pipeline_author_source(source_id,NULL)$q$),
    ('operator_scopes',$q$state='active' AND panadan_knowledge.pipeline_author_source(source_id,id)$q$),
    ('contract_operator_scopes','panadan_knowledge.pipeline_author_source(source_id,operator_scope_id)'),
    ('sync_checkpoints','panadan_knowledge.pipeline_author_source(source_id,operator_scope_id)'),
    ('source_scope_grants',$q$membership_id=panadan_knowledge.pipeline_author_member()
        AND capability='representation.read' AND revoked_at IS NULL AND valid_from<=clock_timestamp()
        AND (valid_until IS NULL OR valid_until>clock_timestamp())$q$),
    ('membership_roles','membership_id=panadan_knowledge.pipeline_author_member()'),
    ('role_versions',$q$state='active' AND capability_set ? 'representation.read'$q$)
  ) AS bindings(relation,predicate)
  LOOP
    EXECUTE format('DROP POLICY IF EXISTS pipeline_author_read ON panadan_knowledge.%I',binding.relation);
    EXECUTE format('DROP POLICY IF EXISTS pipeline_author_lock ON panadan_knowledge.%I',binding.relation);
    EXECUTE format('CREATE POLICY pipeline_author_read ON panadan_knowledge.%I FOR SELECT
      TO panadan_knowledge_pipeline_author USING (workspace_id=panadan_knowledge.pipeline_author_workspace() AND (%s))',
      binding.relation,binding.predicate);
    EXECUTE format('CREATE POLICY pipeline_author_lock ON panadan_knowledge.%I FOR UPDATE
      TO panadan_knowledge_pipeline_author USING (workspace_id=panadan_knowledge.pipeline_author_workspace() AND (%s))
      WITH CHECK (false)',binding.relation,binding.predicate);
  END LOOP;
  FOR binding IN SELECT * FROM (VALUES
    ('pipelines','NOT enabled'),
    ('pipeline_versions',$q$state IN ('draft','active')$q$),
    ('pipeline_objectives','true'),
    ('pipeline_sources','panadan_knowledge.pipeline_author_source(source_id,operator_scope_id)')
  ) AS bindings(relation,predicate)
  LOOP
    EXECUTE format('DROP POLICY IF EXISTS pipeline_author_access ON panadan_knowledge.%I',binding.relation);
    EXECUTE format('CREATE POLICY pipeline_author_access ON panadan_knowledge.%I FOR ALL TO panadan_knowledge_pipeline_author
      USING (workspace_id=panadan_knowledge.pipeline_author_workspace())
      WITH CHECK (workspace_id=panadan_knowledge.pipeline_author_workspace() AND (%s))',binding.relation,binding.predicate);
  END LOOP;
END
$policies$;

GRANT SELECT (workspace_id,id,current_version_id),UPDATE (id)
  ON panadan_knowledge.objectives TO panadan_knowledge_pipeline_author;
GRANT SELECT (workspace_id,id,rev,label,input_kind,state,validation_policy_id),UPDATE (id)
  ON panadan_knowledge.objective_versions TO panadan_knowledge_pipeline_author;
GRANT SELECT (workspace_id,id,kind,state),UPDATE (id)
  ON panadan_knowledge.policy_versions TO panadan_knowledge_pipeline_author;
GRANT SELECT (workspace_id,id,kind,state,label,current_contract_id),UPDATE (id)
  ON panadan_knowledge.sources TO panadan_knowledge_pipeline_author;
GRANT SELECT (workspace_id,id,source_id,adapter_version,state,contract),UPDATE (id)
  ON panadan_knowledge.source_contract_versions TO panadan_knowledge_pipeline_author;
GRANT SELECT (workspace_id,id,source_id,state,label,external_operator_key),UPDATE (id)
  ON panadan_knowledge.operator_scopes TO panadan_knowledge_pipeline_author;
GRANT SELECT (workspace_id,source_id,contract_id,operator_scope_id),UPDATE (contract_id)
  ON panadan_knowledge.contract_operator_scopes TO panadan_knowledge_pipeline_author;
GRANT SELECT (workspace_id,id,source_id,contract_id,operator_scope_id,event_start,event_end),UPDATE (id)
  ON panadan_knowledge.sync_checkpoints TO panadan_knowledge_pipeline_author;
GRANT SELECT (workspace_id,id,source_id,membership_id,operator_scope_id,scope_kind,capability,valid_from,valid_until,revoked_at),
  UPDATE (id) ON panadan_knowledge.source_scope_grants TO panadan_knowledge_pipeline_author;
GRANT SELECT (workspace_id,id,membership_id,role_version_id,valid_until,revoked_at),UPDATE (id)
  ON panadan_knowledge.membership_roles TO panadan_knowledge_pipeline_author;
GRANT SELECT (workspace_id,id,state,capability_set),UPDATE (id)
  ON panadan_knowledge.role_versions TO panadan_knowledge_pipeline_author;
GRANT SELECT (workspace_id,id,pipeline_key,current_version_id),INSERT (workspace_id,pipeline_key),
  UPDATE (current_version_id,enabled) ON panadan_knowledge.pipelines TO panadan_knowledge_pipeline_author;
GRANT SELECT (workspace_id,id,rev,state),
  INSERT (workspace_id,pipeline_id,rev,label,preprocessing_version,processor,max_resources,event_start,event_end),UPDATE (state)
  ON panadan_knowledge.pipeline_versions TO panadan_knowledge_pipeline_author;
GRANT SELECT (workspace_id,pipeline_version_id,objective_version_id,stage_order),
  INSERT (workspace_id,pipeline_version_id,objective_version_id,stage_order)
  ON panadan_knowledge.pipeline_objectives TO panadan_knowledge_pipeline_author;
GRANT SELECT (workspace_id,pipeline_version_id,source_id,contract_id,operator_scope_id),
  INSERT (workspace_id,pipeline_version_id,source_id,contract_id,operator_scope_id)
  ON panadan_knowledge.pipeline_sources TO panadan_knowledge_pipeline_author;
RESET ROLE;
