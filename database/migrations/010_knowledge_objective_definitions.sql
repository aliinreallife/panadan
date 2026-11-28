-- M03.1: curated catalog and versioned, non-executing configuration.
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
     OR to_regprocedure('panadan_knowledge.resource_granted(uuid,uuid,text)') IS NULL
  THEN RAISE EXCEPTION 'Refusing objective migration: review owned target and prior migrations';
  END IF;
END
$guard$;

SET LOCAL ROLE panadan_knowledge_owner;
SET LOCAL search_path=pg_catalog;

ALTER TABLE panadan_knowledge.attribute_schema_versions
  DROP CONSTRAINT IF EXISTS attribute_schema_versions_schema_key_check;
ALTER TABLE panadan_knowledge.attribute_schema_versions
  ADD CONSTRAINT attribute_schema_versions_schema_key_check
    CHECK (schema_key='call_metadata' OR schema_key ~ '^(output|context)\.[a-z][a-z0-9_]{0,39}$'),
  ADD COLUMN IF NOT EXISTS schema_purpose text GENERATED ALWAYS AS (split_part(schema_key,'.',1)) STORED;
CREATE UNIQUE INDEX IF NOT EXISTS knowledge_attribute_schema_purpose
  ON panadan_knowledge.attribute_schema_versions(workspace_id,id,schema_purpose);

DROP POLICY IF EXISTS call_collector_read ON panadan_knowledge.attribute_schema_versions;
CREATE POLICY call_collector_read ON panadan_knowledge.attribute_schema_versions FOR SELECT TO panadan_knowledge_collector
  USING (workspace_id=panadan_knowledge.scoped_workspace() AND schema_key='call_metadata');
DROP POLICY IF EXISTS call_collector_lock ON panadan_knowledge.attribute_schema_versions;
CREATE POLICY call_collector_lock ON panadan_knowledge.attribute_schema_versions FOR UPDATE TO panadan_knowledge_collector
  USING (workspace_id=panadan_knowledge.scoped_workspace() AND schema_key='call_metadata') WITH CHECK (false);

CREATE TABLE IF NOT EXISTS panadan_knowledge.objective_templates (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  template_key text NOT NULL CHECK (template_key ~ '^[a-z][a-z0-9_]{0,39}$'),
  rev integer NOT NULL CHECK (rev>0),
  label text NOT NULL CHECK (char_length(btrim(label)) BETWEEN 1 AND 160),
  input_kind text NOT NULL CHECK (input_kind IN ('filtered_call','validated_knowledge')),
  definition jsonb NOT NULL CHECK (jsonb_typeof(definition)='object' AND octet_length(definition::text)<=8192),
  state text NOT NULL DEFAULT 'active' CHECK (state IN ('active','retired')),
  UNIQUE (template_key,rev),
  UNIQUE (id,input_kind)
);

CREATE TABLE IF NOT EXISTS panadan_knowledge.objectives (
  workspace_id uuid NOT NULL REFERENCES panadan_knowledge.workspaces(id) ON DELETE RESTRICT,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  objective_key text NOT NULL CHECK (objective_key ~ '^[a-z][a-z0-9_]{0,39}$'),
  current_version_id uuid,
  PRIMARY KEY (workspace_id,id),
  UNIQUE (workspace_id,objective_key)
);

CREATE TABLE IF NOT EXISTS panadan_knowledge.objective_versions (
  workspace_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  objective_id uuid NOT NULL,
  template_id uuid,
  rev integer NOT NULL CHECK (rev>0),
  label text NOT NULL CHECK (char_length(label)<=160 AND btrim(label)<>''),
  purpose text NOT NULL CHECK (char_length(purpose)<=1200 AND btrim(purpose)<>''),
  input_kind text NOT NULL CHECK (input_kind IN ('filtered_call','validated_knowledge')),
  output_schema_id uuid NOT NULL,
  context_schema_id uuid NOT NULL,
  validation_policy_id uuid NOT NULL,
  output_purpose text GENERATED ALWAYS AS ('output'::text) STORED,
  context_purpose text GENERATED ALWAYS AS ('context'::text) STORED,
  policy_kind text GENERATED ALWAYS AS ('validation'::text) STORED,
  state text NOT NULL DEFAULT 'active' CHECK (state IN ('active','retired')),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (workspace_id,id),
  UNIQUE (workspace_id,id,input_kind),
  UNIQUE (workspace_id,objective_id,id),
  UNIQUE (workspace_id,objective_id,rev),
  FOREIGN KEY (workspace_id,objective_id) REFERENCES panadan_knowledge.objectives(workspace_id,id) ON DELETE RESTRICT,
  FOREIGN KEY (template_id,input_kind) REFERENCES panadan_knowledge.objective_templates(id,input_kind) ON DELETE RESTRICT,
  FOREIGN KEY (workspace_id,output_schema_id,output_purpose)
    REFERENCES panadan_knowledge.attribute_schema_versions(workspace_id,id,schema_purpose) ON DELETE RESTRICT,
  FOREIGN KEY (workspace_id,context_schema_id,context_purpose)
    REFERENCES panadan_knowledge.attribute_schema_versions(workspace_id,id,schema_purpose) ON DELETE RESTRICT,
  FOREIGN KEY (workspace_id,validation_policy_id,policy_kind)
    REFERENCES panadan_knowledge.policy_versions(workspace_id,id,kind) ON DELETE RESTRICT,
  CHECK (template_id IS NOT NULL OR input_kind='filtered_call')
);

CREATE TABLE IF NOT EXISTS panadan_knowledge.pipelines (
  workspace_id uuid NOT NULL REFERENCES panadan_knowledge.workspaces(id) ON DELETE RESTRICT,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  pipeline_key text NOT NULL CHECK (pipeline_key ~ '^[a-z][a-z0-9_]{0,39}$'),
  current_version_id uuid,
  enabled boolean NOT NULL DEFAULT false,
  PRIMARY KEY (workspace_id,id),
  UNIQUE (workspace_id,pipeline_key),
  CHECK (NOT enabled OR current_version_id IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS panadan_knowledge.pipeline_versions (
  workspace_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  pipeline_id uuid NOT NULL,
  rev integer NOT NULL CHECK (rev>0),
  label text NOT NULL CHECK (char_length(label)<=160 AND btrim(label)<>''),
  preprocessing_version text NOT NULL CHECK (preprocessing_version='call-redaction-v1'),
  processor text NOT NULL CHECK (processor='synthetic-deterministic-v1'),
  max_resources integer NOT NULL CHECK (max_resources BETWEEN 1 AND 500),
  event_start timestamptz NOT NULL,
  event_end timestamptz NOT NULL,
  state text NOT NULL DEFAULT 'draft' CHECK (state IN ('draft','active','retired')),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (workspace_id,id),
  UNIQUE (workspace_id,pipeline_id,id),
  UNIQUE (workspace_id,pipeline_id,rev),
  FOREIGN KEY (workspace_id,pipeline_id) REFERENCES panadan_knowledge.pipelines(workspace_id,id) ON DELETE RESTRICT,
  CHECK (event_start<event_end AND extract(epoch FROM event_end-event_start)<=2592000)
);

CREATE TABLE IF NOT EXISTS panadan_knowledge.pipeline_objectives (
  workspace_id uuid NOT NULL,
  pipeline_version_id uuid NOT NULL,
  objective_version_id uuid NOT NULL,
  stage_order integer NOT NULL CHECK (stage_order BETWEEN 1 AND 6),
  input_kind text GENERATED ALWAYS AS ('filtered_call'::text) STORED,
  PRIMARY KEY (workspace_id,pipeline_version_id,objective_version_id),
  UNIQUE (workspace_id,pipeline_version_id,stage_order),
  FOREIGN KEY (workspace_id,pipeline_version_id) REFERENCES panadan_knowledge.pipeline_versions(workspace_id,id) ON DELETE RESTRICT,
  FOREIGN KEY (workspace_id,objective_version_id,input_kind)
    REFERENCES panadan_knowledge.objective_versions(workspace_id,id,input_kind) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS panadan_knowledge.pipeline_sources (
  workspace_id uuid NOT NULL,
  pipeline_version_id uuid NOT NULL,
  source_id uuid NOT NULL,
  contract_id uuid NOT NULL,
  operator_scope_id uuid NOT NULL,
  PRIMARY KEY (workspace_id,pipeline_version_id),
  FOREIGN KEY (workspace_id,pipeline_version_id) REFERENCES panadan_knowledge.pipeline_versions(workspace_id,id) ON DELETE RESTRICT,
  FOREIGN KEY (workspace_id,source_id,contract_id,operator_scope_id)
    REFERENCES panadan_knowledge.contract_operator_scopes(workspace_id,source_id,contract_id,operator_scope_id) ON DELETE RESTRICT
);

DO $pointers$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='objective_current_version'
                 AND conrelid='panadan_knowledge.objectives'::regclass) THEN
    ALTER TABLE panadan_knowledge.objectives ADD CONSTRAINT objective_current_version
      FOREIGN KEY (workspace_id,id,current_version_id)
      REFERENCES panadan_knowledge.objective_versions(workspace_id,objective_id,id) ON DELETE RESTRICT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='pipeline_current_version'
                 AND conrelid='panadan_knowledge.pipelines'::regclass) THEN
    ALTER TABLE panadan_knowledge.pipelines ADD CONSTRAINT pipeline_current_version
      FOREIGN KEY (workspace_id,id,current_version_id)
      REFERENCES panadan_knowledge.pipeline_versions(workspace_id,pipeline_id,id) ON DELETE RESTRICT;
  END IF;
END
$pointers$;

CREATE OR REPLACE FUNCTION panadan_knowledge.guard_objective_definition()
RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $body$
BEGIN
  IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Published definitions are immutable'; END IF;
  IF (to_jsonb(NEW)-'state') IS DISTINCT FROM (to_jsonb(OLD)-'state')
     OR (OLD.state='retired' AND NEW.state<>'retired')
     OR (OLD.state<>'draft' AND NEW.state='draft')
  THEN RAISE EXCEPTION 'Published definitions are immutable'; END IF;
  RETURN NEW;
END
$body$;
REVOKE ALL ON FUNCTION panadan_knowledge.guard_objective_definition() FROM PUBLIC;
DROP TRIGGER IF EXISTS knowledge_immutable_objective_schema ON panadan_knowledge.attribute_schema_versions;
CREATE TRIGGER knowledge_immutable_objective_schema BEFORE UPDATE OR DELETE ON panadan_knowledge.attribute_schema_versions
  FOR EACH ROW WHEN (OLD.schema_purpose IN ('output','context'))
  EXECUTE FUNCTION panadan_knowledge.guard_objective_definition();

CREATE OR REPLACE FUNCTION panadan_knowledge.guard_pipeline_binding()
RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $body$
DECLARE expected_state text;
BEGIN
  IF TG_OP<>'INSERT' THEN
    RAISE EXCEPTION 'Pipeline bindings are immutable';
  END IF;
  SELECT state INTO expected_state FROM panadan_knowledge.pipeline_versions
    WHERE workspace_id=NEW.workspace_id AND id=NEW.pipeline_version_id FOR SHARE;
  IF expected_state IS DISTINCT FROM 'draft' THEN
    RAISE EXCEPTION 'Bindings require a draft pipeline version';
  END IF;
  RETURN NEW;
END
$body$;
REVOKE ALL ON FUNCTION panadan_knowledge.guard_pipeline_binding() FROM PUBLIC;

DO $rls$
DECLARE target text;
BEGIN
  FOREACH target IN ARRAY ARRAY['objective_templates','objectives','objective_versions','pipelines',
    'pipeline_versions','pipeline_objectives','pipeline_sources']
  LOOP
    EXECUTE format('ALTER TABLE panadan_knowledge.%I ENABLE ROW LEVEL SECURITY',target);
    EXECUTE format('ALTER TABLE panadan_knowledge.%I FORCE ROW LEVEL SECURITY',target);
    EXECUTE format('REVOKE ALL ON TABLE panadan_knowledge.%I FROM PUBLIC',target);
  END LOOP;
  FOREACH target IN ARRAY ARRAY['objective_templates','objective_versions','pipeline_versions']
  LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS knowledge_immutable_definition ON panadan_knowledge.%I',target);
    EXECUTE format('CREATE TRIGGER knowledge_immutable_definition BEFORE UPDATE OR DELETE ON panadan_knowledge.%I
      FOR EACH ROW EXECUTE FUNCTION panadan_knowledge.guard_objective_definition()',target);
  END LOOP;
  FOREACH target IN ARRAY ARRAY['pipeline_objectives','pipeline_sources']
  LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS knowledge_immutable_binding ON panadan_knowledge.%I',target);
    EXECUTE format('CREATE TRIGGER knowledge_immutable_binding BEFORE INSERT OR UPDATE OR DELETE ON panadan_knowledge.%I
      FOR EACH ROW EXECUTE FUNCTION panadan_knowledge.guard_pipeline_binding()',target);
  END LOOP;
END
$rls$;
RESET ROLE;
