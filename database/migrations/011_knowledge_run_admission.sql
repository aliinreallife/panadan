-- M03.2: default-off schedule occurrences, idempotent admission and frozen population.
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
     OR to_regclass('panadan_knowledge.pipeline_sources') IS NULL
  THEN RAISE EXCEPTION 'Refusing run admission migration: review owned target and prior migrations';
  END IF;
END
$guard$;
SET LOCAL ROLE panadan_knowledge_owner;
SET LOCAL search_path=pg_catalog;

CREATE UNIQUE INDEX IF NOT EXISTS knowledge_representation_revision_parent
  ON panadan_knowledge.representations (workspace_id,resource_revision_id,id);

CREATE TABLE IF NOT EXISTS panadan_knowledge.schedules (
  workspace_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  schedule_key text NOT NULL CHECK (schedule_key ~ '^[a-z][a-z0-9_]{0,39}$'),
  pipeline_version_id uuid NOT NULL,
  requested_by uuid NOT NULL,
  cadence_seconds integer NOT NULL CHECK (cadence_seconds BETWEEN 900 AND 604800),
  first_due_at timestamptz NOT NULL,
  next_due_at timestamptz NOT NULL CHECK (next_due_at>=first_due_at),
  enabled boolean NOT NULL DEFAULT false,
  PRIMARY KEY (workspace_id,id),
  UNIQUE (workspace_id,pipeline_version_id,schedule_key),
  UNIQUE (workspace_id,pipeline_version_id,id,requested_by),
  FOREIGN KEY (workspace_id,pipeline_version_id) REFERENCES panadan_knowledge.pipeline_versions(workspace_id,id) ON DELETE RESTRICT,
  FOREIGN KEY (workspace_id,requested_by) REFERENCES panadan_knowledge.memberships(workspace_id,id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS knowledge_schedule_due ON panadan_knowledge.schedules (next_due_at,workspace_id,id) WHERE enabled;

CREATE TABLE IF NOT EXISTS panadan_knowledge.runs (
  workspace_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  pipeline_version_id uuid NOT NULL,
  requested_by uuid NOT NULL,
  trigger_kind text NOT NULL CHECK (trigger_kind IN ('manual','schedule')),
  request_key uuid,
  schedule_id uuid,
  occurrence_at timestamptz,
  policy_epoch bigint NOT NULL CHECK (policy_epoch>=0),
  manifest jsonb NOT NULL CHECK (jsonb_typeof(manifest)='object' AND octet_length(manifest::text)<=8192),
  state text NOT NULL DEFAULT 'queued' CHECK (state='queued'),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (workspace_id,id),
  FOREIGN KEY (workspace_id,pipeline_version_id) REFERENCES panadan_knowledge.pipeline_versions(workspace_id,id) ON DELETE RESTRICT,
  FOREIGN KEY (workspace_id,requested_by) REFERENCES panadan_knowledge.memberships(workspace_id,id) ON DELETE RESTRICT,
  FOREIGN KEY (workspace_id,pipeline_version_id,schedule_id,requested_by)
    REFERENCES panadan_knowledge.schedules(workspace_id,pipeline_version_id,id,requested_by) ON DELETE RESTRICT,
  CHECK ((trigger_kind='manual' AND request_key IS NOT NULL AND schedule_id IS NULL AND occurrence_at IS NULL)
      OR (trigger_kind='schedule' AND request_key IS NULL AND schedule_id IS NOT NULL AND occurrence_at IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS knowledge_manual_run_identity ON panadan_knowledge.runs (workspace_id,request_key)
  WHERE request_key IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS knowledge_run_occurrence ON panadan_knowledge.runs (workspace_id,schedule_id,occurrence_at)
  WHERE schedule_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS panadan_knowledge.run_population_members (
  workspace_id uuid NOT NULL,
  run_id uuid NOT NULL,
  resource_id uuid NOT NULL,
  resource_revision_id uuid NOT NULL,
  representation_id uuid,
  eligibility text NOT NULL CHECK (eligibility IN ('ready','excluded')),
  reason_code text CHECK (reason_code IN ('resource_unavailable','filtered_text_unavailable')),
  PRIMARY KEY (workspace_id,run_id,resource_id),
  FOREIGN KEY (workspace_id,run_id) REFERENCES panadan_knowledge.runs(workspace_id,id) ON DELETE RESTRICT,
  FOREIGN KEY (workspace_id,resource_id,resource_revision_id)
    REFERENCES panadan_knowledge.resource_revisions(workspace_id,resource_id,id) ON DELETE RESTRICT,
  FOREIGN KEY (workspace_id,resource_revision_id,representation_id)
    REFERENCES panadan_knowledge.representations(workspace_id,resource_revision_id,id) ON DELETE RESTRICT,
  CHECK ((eligibility='ready' AND representation_id IS NOT NULL AND reason_code IS NULL) OR
         (eligibility='excluded' AND representation_id IS NULL AND reason_code IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS panadan_knowledge.coverage_snapshots (
  workspace_id uuid NOT NULL,
  run_id uuid NOT NULL,
  stage text NOT NULL CHECK (stage='admission'),
  measured_count integer NOT NULL CHECK (measured_count BETWEEN 0 AND 500),
  ready_count integer NOT NULL CHECK (ready_count>=0),
  excluded_count integer NOT NULL CHECK (excluded_count>=0),
  source_eligible_count bigint CHECK (source_eligible_count>=0),
  bounded boolean NOT NULL,
  as_of timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (workspace_id,run_id,stage),
  FOREIGN KEY (workspace_id,run_id) REFERENCES panadan_knowledge.runs(workspace_id,id) ON DELETE RESTRICT,
  CHECK (measured_count=ready_count+excluded_count)
);

CREATE OR REPLACE FUNCTION panadan_knowledge.guard_admission_snapshot()
RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $body$
BEGIN
  IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Run admission snapshots are immutable'; END IF;
  IF to_jsonb(NEW) IS DISTINCT FROM to_jsonb(OLD) THEN
    RAISE EXCEPTION 'Run admission snapshots are immutable';
  END IF;
  RETURN NEW;
END
$body$;
REVOKE ALL ON FUNCTION panadan_knowledge.guard_admission_snapshot() FROM PUBLIC;

DO $rls$
DECLARE target text;
BEGIN
  FOREACH target IN ARRAY ARRAY['schedules','runs','run_population_members','coverage_snapshots']
  LOOP
    EXECUTE format('ALTER TABLE panadan_knowledge.%I ENABLE ROW LEVEL SECURITY',target);
    EXECUTE format('ALTER TABLE panadan_knowledge.%I FORCE ROW LEVEL SECURITY',target);
    EXECUTE format('REVOKE ALL ON TABLE panadan_knowledge.%I FROM PUBLIC',target);
  END LOOP;
  FOREACH target IN ARRAY ARRAY['runs','run_population_members','coverage_snapshots']
  LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS knowledge_immutable_admission ON panadan_knowledge.%I',target);
    EXECUTE format('CREATE TRIGGER knowledge_immutable_admission BEFORE UPDATE OR DELETE ON panadan_knowledge.%I
      FOR EACH ROW EXECUTE FUNCTION panadan_knowledge.guard_admission_snapshot()',target);
  END LOOP;
END
$rls$;
RESET ROLE;
