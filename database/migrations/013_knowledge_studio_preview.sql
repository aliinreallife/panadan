-- Read projections for explicitly authorized synthetic Studio users.
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
     OR EXISTS (SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.roleid OR r.oid=m.member
                WHERE r.rolname='panadan_knowledge_owner')
     OR to_regclass('panadan_knowledge.fixture_work_results') IS NULL
  THEN RAISE EXCEPTION 'Refusing Studio preview migration: review owned target and prior migrations';
  END IF;
END
$guard$;
SET LOCAL ROLE panadan_knowledge_owner;
SET LOCAL search_path=pg_catalog;

ALTER TABLE panadan_knowledge.scope_grants DROP CONSTRAINT IF EXISTS scope_grants_capability_check;
ALTER TABLE panadan_knowledge.scope_grants ADD CONSTRAINT scope_grants_capability_check
  CHECK (capability IN ('workspace.read','members.manage','roles.manage','objective.configure','pipeline.configure','pipeline.run'));

CREATE OR REPLACE FUNCTION panadan_knowledge.studio_capability(permission text)
RETURNS boolean LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $body$
 SELECT panadan_knowledge.resource_member() IS NOT NULL
    AND permission=ANY(string_to_array(current_setting('panadan.studio_capabilities',true),','))
$body$;
REVOKE ALL ON FUNCTION panadan_knowledge.studio_capability(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION panadan_knowledge.studio_capability(text) TO panadan_knowledge_reader;

DO $policies$
DECLARE binding record;
BEGIN
  FOR binding IN SELECT * FROM (VALUES
    ('objective_templates',$predicate$panadan_knowledge.studio_capability('objective.configure')$predicate$),
    ('objectives',$predicate$workspace_id=panadan_knowledge.scoped_workspace()
       AND panadan_knowledge.studio_capability('objective.configure')$predicate$),
    ('objective_versions',$predicate$workspace_id=panadan_knowledge.scoped_workspace()
       AND panadan_knowledge.studio_capability('objective.configure')$predicate$),
    ('pipeline_sources',$predicate$workspace_id=panadan_knowledge.scoped_workspace()
       AND (panadan_knowledge.studio_capability('pipeline.configure') OR panadan_knowledge.studio_capability('pipeline.run'))
       AND panadan_knowledge.resource_granted(source_id,operator_scope_id,'representation.read')$predicate$),
    ('pipeline_versions',$predicate$workspace_id=panadan_knowledge.scoped_workspace()
       AND EXISTS (SELECT 1 FROM panadan_knowledge.pipeline_sources b WHERE b.workspace_id=pipeline_versions.workspace_id
                   AND b.pipeline_version_id=pipeline_versions.id)$predicate$),
    ('pipelines',$predicate$workspace_id=panadan_knowledge.scoped_workspace()
       AND EXISTS (SELECT 1 FROM panadan_knowledge.pipeline_versions v WHERE v.workspace_id=pipelines.workspace_id
                   AND v.id=pipelines.current_version_id)$predicate$),
    ('pipeline_objectives',$predicate$workspace_id=panadan_knowledge.scoped_workspace()
       AND EXISTS (SELECT 1 FROM panadan_knowledge.pipeline_versions v WHERE v.workspace_id=pipeline_objectives.workspace_id
                   AND v.id=pipeline_objectives.pipeline_version_id)$predicate$),
    ('schedules',$predicate$workspace_id=panadan_knowledge.scoped_workspace()
       AND requested_by=panadan_knowledge.resource_member()
       AND EXISTS (SELECT 1 FROM panadan_knowledge.pipeline_versions v WHERE v.workspace_id=schedules.workspace_id
                   AND v.id=schedules.pipeline_version_id)$predicate$),
    ('runs',$predicate$workspace_id=panadan_knowledge.scoped_workspace()
       AND panadan_knowledge.studio_capability('pipeline.run') AND requested_by=panadan_knowledge.resource_member()
       AND EXISTS (SELECT 1 FROM panadan_knowledge.pipeline_versions v WHERE v.workspace_id=runs.workspace_id
                   AND v.id=runs.pipeline_version_id)$predicate$),
    ('coverage_snapshots',$predicate$workspace_id=panadan_knowledge.scoped_workspace()
       AND EXISTS (SELECT 1 FROM panadan_knowledge.runs r WHERE r.workspace_id=coverage_snapshots.workspace_id
                   AND r.id=coverage_snapshots.run_id)$predicate$),
    ('work_items',$predicate$workspace_id=panadan_knowledge.scoped_workspace()
       AND EXISTS (SELECT 1 FROM panadan_knowledge.runs r WHERE r.workspace_id=work_items.workspace_id
                   AND r.id=work_items.run_id)$predicate$)
  ) AS bindings(relation,predicate)
  LOOP
    EXECUTE format('DROP POLICY IF EXISTS studio_preview_reader ON panadan_knowledge.%I',binding.relation);
    EXECUTE format('CREATE POLICY studio_preview_reader ON panadan_knowledge.%I FOR SELECT TO panadan_knowledge_reader USING (%s)',
      binding.relation,binding.predicate);
  END LOOP;
END
$policies$;

GRANT SELECT (id,template_key,rev,label,input_kind,state) ON panadan_knowledge.objective_templates TO panadan_knowledge_reader;
GRANT SELECT (workspace_id,id,objective_key,current_version_id) ON panadan_knowledge.objectives TO panadan_knowledge_reader;
GRANT SELECT (workspace_id,id,objective_id,template_id,rev,label,purpose,input_kind,state) ON panadan_knowledge.objective_versions TO panadan_knowledge_reader;
GRANT SELECT (workspace_id,id,current_version_id,enabled) ON panadan_knowledge.pipelines TO panadan_knowledge_reader;
GRANT SELECT (workspace_id,id,pipeline_id,rev,label,processor,max_resources,event_start,event_end,state)
  ON panadan_knowledge.pipeline_versions TO panadan_knowledge_reader;
GRANT SELECT (workspace_id,pipeline_version_id,objective_version_id,stage_order)
  ON panadan_knowledge.pipeline_objectives TO panadan_knowledge_reader;
GRANT SELECT (workspace_id,pipeline_version_id,source_id,contract_id,operator_scope_id)
  ON panadan_knowledge.pipeline_sources TO panadan_knowledge_reader;
GRANT SELECT (workspace_id,pipeline_version_id,requested_by,enabled,next_due_at,cadence_seconds)
  ON panadan_knowledge.schedules TO panadan_knowledge_reader;
GRANT SELECT (workspace_id,id,pipeline_version_id,requested_by,trigger_kind,state,created_at,started_at,finished_at)
  ON panadan_knowledge.runs TO panadan_knowledge_reader;
GRANT SELECT (workspace_id,run_id,stage,measured_count,ready_count,excluded_count,source_eligible_count,bounded)
  ON panadan_knowledge.coverage_snapshots TO panadan_knowledge_reader;
GRANT SELECT (workspace_id,run_id,state) ON panadan_knowledge.work_items TO panadan_knowledge_reader;
RESET ROLE;
