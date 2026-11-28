-- Objective-only authoring role. Membership is provisioned separately.
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
     OR to_regprocedure('panadan_knowledge.studio_capability(text)') IS NULL
  THEN RAISE EXCEPTION 'Refusing objective authoring migration: review owned target and prior migrations';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='panadan_knowledge_objective_author') THEN
    CREATE ROLE panadan_knowledge_objective_author NOLOGIN NOINHERIT NOSUPERUSER
      NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='panadan_knowledge_objective_author'
      AND (rolcanlogin OR rolinherit OR rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls))
     OR EXISTS (SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member OR r.oid=m.roleid
                WHERE r.rolname='panadan_knowledge_objective_author')
  THEN RAISE EXCEPTION 'Conflicting objective author role or membership; review manually';
  END IF;
END
$guard$;
SET LOCAL ROLE panadan_knowledge_owner;
SET LOCAL search_path=pg_catalog;

CREATE OR REPLACE FUNCTION panadan_knowledge.objective_author_workspace()
RETURNS uuid LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $body$
 SELECT CASE WHEN current_setting('panadan.objective_authorized',true)='yes'
        THEN panadan_knowledge.scoped_workspace() ELSE NULL END
$body$;
REVOKE ALL ON FUNCTION panadan_knowledge.objective_author_workspace() FROM PUBLIC;
GRANT USAGE ON SCHEMA panadan_knowledge TO panadan_knowledge_objective_author;
GRANT EXECUTE ON FUNCTION panadan_knowledge.context_uuid(text),panadan_knowledge.scoped_workspace(),
  panadan_knowledge.objective_author_workspace() TO panadan_knowledge_objective_author;

DO $policies$
DECLARE binding record;
BEGIN
  FOR binding IN SELECT * FROM (VALUES
    ('objectives','workspace_id=panadan_knowledge.objective_author_workspace()'),
    ('objective_versions','workspace_id=panadan_knowledge.objective_author_workspace()'),
    ('attribute_schema_versions',$predicate$workspace_id=panadan_knowledge.objective_author_workspace()
       AND schema_key ~ '^(output|context)\.'$predicate$)
  ) AS bindings(relation,predicate)
  LOOP
    EXECUTE format('DROP POLICY IF EXISTS objective_author_access ON panadan_knowledge.%I',binding.relation);
    EXECUTE format('CREATE POLICY objective_author_access ON panadan_knowledge.%I
      FOR ALL TO panadan_knowledge_objective_author USING (%s) WITH CHECK (%s)',
      binding.relation,binding.predicate,binding.predicate);
  END LOOP;
  FOR binding IN SELECT * FROM (VALUES
    ('policy_versions',$predicate$workspace_id=panadan_knowledge.objective_author_workspace()
       AND kind='validation' AND state='approved'$predicate$),
    ('objective_templates',$predicate$panadan_knowledge.objective_author_workspace() IS NOT NULL AND state='active'$predicate$)
  ) AS bindings(relation,predicate)
  LOOP
    EXECUTE format('DROP POLICY IF EXISTS objective_author_read ON panadan_knowledge.%I',binding.relation);
    EXECUTE format('DROP POLICY IF EXISTS objective_author_lock ON panadan_knowledge.%I',binding.relation);
    EXECUTE format('CREATE POLICY objective_author_read ON panadan_knowledge.%I
      FOR SELECT TO panadan_knowledge_objective_author USING (%s)',binding.relation,binding.predicate);
    EXECUTE format('CREATE POLICY objective_author_lock ON panadan_knowledge.%I
      FOR UPDATE TO panadan_knowledge_objective_author USING (%s) WITH CHECK (false)',binding.relation,binding.predicate);
  END LOOP;
END
$policies$;

GRANT SELECT (workspace_id,id,objective_key,current_version_id),INSERT (workspace_id,objective_key),UPDATE (current_version_id)
  ON panadan_knowledge.objectives TO panadan_knowledge_objective_author;
GRANT SELECT (workspace_id,id,objective_id,template_id,rev,input_kind,output_schema_id,context_schema_id,validation_policy_id,state),
  INSERT (workspace_id,objective_id,template_id,rev,label,purpose,input_kind,output_schema_id,context_schema_id,validation_policy_id)
  ON panadan_knowledge.objective_versions TO panadan_knowledge_objective_author;
GRANT SELECT (id), INSERT (workspace_id,schema_key,rev,json_schema,state)
  ON panadan_knowledge.attribute_schema_versions TO panadan_knowledge_objective_author;
GRANT SELECT (workspace_id,id,kind,state),UPDATE (id)
  ON panadan_knowledge.policy_versions TO panadan_knowledge_objective_author;
GRANT SELECT (id,template_key,rev,input_kind,state),UPDATE (id)
  ON panadan_knowledge.objective_templates TO panadan_knowledge_objective_author;

DROP POLICY IF EXISTS studio_validation_policy ON panadan_knowledge.policy_versions;
CREATE POLICY studio_validation_policy ON panadan_knowledge.policy_versions FOR SELECT TO panadan_knowledge_reader
  USING (workspace_id=panadan_knowledge.scoped_workspace() AND kind='validation' AND state='approved'
        AND panadan_knowledge.studio_capability('objective.configure'));
GRANT SELECT (workspace_id,id,kind,policy_key,rev,state) ON panadan_knowledge.policy_versions TO panadan_knowledge_reader;
RESET ROLE;
