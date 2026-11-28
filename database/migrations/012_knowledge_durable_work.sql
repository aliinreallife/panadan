-- M03.3: synthetic worker state, leases, fencing and one effect per item.
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
     OR to_regclass('panadan_knowledge.run_population_members') IS NULL
  THEN RAISE EXCEPTION 'Refusing durable work migration: review owned target and prior migrations';
  END IF;
END
$guard$;
SET LOCAL ROLE panadan_knowledge_owner;
SET LOCAL search_path=pg_catalog;

ALTER TABLE panadan_knowledge.runs DROP CONSTRAINT IF EXISTS runs_state_check;
ALTER TABLE panadan_knowledge.runs
  ADD CONSTRAINT runs_state_check CHECK (state IN
    ('queued','running','paused','succeeded','partial','failed','canceled','blocked_policy')),
  ADD COLUMN IF NOT EXISTS started_at timestamptz,
  ADD COLUMN IF NOT EXISTS finished_at timestamptz;

CREATE OR REPLACE FUNCTION panadan_knowledge.guard_run_manifest()
RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $body$
BEGIN
  IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Run admission snapshots are immutable'; END IF;
  IF (to_jsonb(NEW)-ARRAY['state','started_at','finished_at']) IS DISTINCT FROM
      (to_jsonb(OLD)-ARRAY['state','started_at','finished_at']) THEN
    RAISE EXCEPTION 'Run admission snapshots are immutable';
  END IF;
  RETURN NEW;
END
$body$;
REVOKE ALL ON FUNCTION panadan_knowledge.guard_run_manifest() FROM PUBLIC;
DROP TRIGGER IF EXISTS knowledge_immutable_admission ON panadan_knowledge.runs;
CREATE TRIGGER knowledge_immutable_admission BEFORE UPDATE OR DELETE ON panadan_knowledge.runs
  FOR EACH ROW EXECUTE FUNCTION panadan_knowledge.guard_run_manifest();

CREATE TABLE IF NOT EXISTS panadan_knowledge.work_items (
  workspace_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  run_id uuid NOT NULL,
  resource_id uuid NOT NULL,
  priority_class text NOT NULL CHECK (priority_class IN ('fresh','backfill')),
  state text NOT NULL DEFAULT 'queued' CHECK (state IN
    ('queued','running','retry_wait','paused','succeeded','failed','canceled','blocked_policy')),
  available_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  owner_id uuid,
  lease_until timestamptz,
  fence bigint NOT NULL DEFAULT 0 CHECK (fence>=0),
  attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count>=0),
  max_attempts integer NOT NULL CHECK (max_attempts BETWEEN 1 AND 5),
  outcome_code text CHECK (outcome_code IN ('fixture_failed','lease_expired','resource_unavailable','attempts_exhausted')),
  PRIMARY KEY (workspace_id,id),
  UNIQUE (workspace_id,run_id,resource_id),
  FOREIGN KEY (workspace_id,run_id,resource_id)
    REFERENCES panadan_knowledge.run_population_members(workspace_id,run_id,resource_id) ON DELETE RESTRICT,
  CHECK (attempt_count<=max_attempts),
  CHECK ((state='running' AND owner_id IS NOT NULL AND lease_until IS NOT NULL) OR
         (state<>'running' AND owner_id IS NULL AND lease_until IS NULL))
);
CREATE INDEX IF NOT EXISTS knowledge_work_claim ON panadan_knowledge.work_items(workspace_id,run_id,available_at,id)
  WHERE state IN ('queued','retry_wait');
CREATE INDEX IF NOT EXISTS knowledge_work_expiry ON panadan_knowledge.work_items(workspace_id,run_id,lease_until,id)
  WHERE state='running';

CREATE TABLE IF NOT EXISTS panadan_knowledge.work_attempts (
  workspace_id uuid NOT NULL,
  item_id uuid NOT NULL,
  attempt_no integer NOT NULL CHECK (attempt_no BETWEEN 1 AND 5),
  fence bigint NOT NULL CHECK (fence>0),
  worker_id uuid NOT NULL,
  started_at timestamptz NOT NULL,
  finished_at timestamptz,
  outcome text NOT NULL DEFAULT 'running' CHECK (outcome IN
    ('running','succeeded','retry_wait','failed','lease_expired','paused','canceled','blocked_policy')),
  PRIMARY KEY (workspace_id,item_id,attempt_no),
  UNIQUE (workspace_id,item_id,fence),
  FOREIGN KEY (workspace_id,item_id) REFERENCES panadan_knowledge.work_items(workspace_id,id) ON DELETE RESTRICT,
  CHECK ((outcome='running')=(finished_at IS NULL))
);

CREATE TABLE IF NOT EXISTS panadan_knowledge.fixture_work_results (
  workspace_id uuid NOT NULL,
  item_id uuid NOT NULL,
  fence bigint NOT NULL,
  processor text NOT NULL CHECK (processor='synthetic-deterministic-v1'),
  input_digest text NOT NULL CHECK (input_digest ~ '^[0-9a-f]{64}$'),
  character_count integer NOT NULL CHECK (character_count BETWEEN 1 AND 262144),
  PRIMARY KEY (workspace_id,item_id),
  FOREIGN KEY (workspace_id,item_id,fence)
    REFERENCES panadan_knowledge.work_attempts(workspace_id,item_id,fence) ON DELETE RESTRICT
);

DO $rls$
DECLARE target text;
BEGIN
  FOREACH target IN ARRAY ARRAY['work_items','work_attempts','fixture_work_results']
  LOOP
    EXECUTE format('ALTER TABLE panadan_knowledge.%I ENABLE ROW LEVEL SECURITY',target);
    EXECUTE format('ALTER TABLE panadan_knowledge.%I FORCE ROW LEVEL SECURITY',target);
    EXECUTE format('REVOKE ALL ON TABLE panadan_knowledge.%I FROM PUBLIC',target);
  END LOOP;
END
$rls$;
RESET ROLE;
