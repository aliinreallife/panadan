-- M02.4: local, scoped collection state. No collector LOGIN is provisioned.
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
     OR to_regclass('panadan_knowledge.contract_operator_scopes') IS NULL
  THEN RAISE EXCEPTION 'Refusing call collection migration: review owned target and prior migrations';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='panadan_knowledge_collector') THEN
    CREATE ROLE panadan_knowledge_collector NOLOGIN NOINHERIT NOSUPERUSER
      NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='panadan_knowledge_collector'
      AND (rolcanlogin OR rolinherit OR rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls))
     OR EXISTS (SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member OR r.oid=m.roleid
                WHERE r.rolname='panadan_knowledge_collector')
  THEN RAISE EXCEPTION 'Conflicting collector role or membership; review manually';
  END IF;
END
$guard$;

SET LOCAL ROLE panadan_knowledge_owner;
SET LOCAL search_path=pg_catalog;

ALTER TABLE panadan_knowledge.resource_revisions ADD COLUMN IF NOT EXISTS transcript_outcome text
  NOT NULL DEFAULT 'transcript_unknown'
  CHECK (transcript_outcome IN ('filtered','transcript_unknown','transcript_missing','transcript_invalid',
    'transcript_review','transcript_oversize','filtered_oversize','tombstone'));

-- A trusted synthetic operator provisions an exact scope. The collector
-- can only advance an existing checkpoint; it cannot widen the window.
CREATE TABLE IF NOT EXISTS panadan_knowledge.sync_checkpoints (
  workspace_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  source_id uuid NOT NULL,
  contract_id uuid NOT NULL,
  operator_scope_id uuid NOT NULL,
  attribute_schema_id uuid NOT NULL,
  retention_policy_id uuid NOT NULL,
  redaction_policy_id uuid NOT NULL,
  event_start timestamptz NOT NULL,
  event_end timestamptz NOT NULL,
  change_start timestamptz NOT NULL,
  change_end timestamptz NOT NULL,
  cursor_time timestamptz,
  cursor_id bigint,
  cursor_version bigint NOT NULL DEFAULT 0 CHECK (cursor_version>=0),
  finished boolean NOT NULL DEFAULT false,
  PRIMARY KEY (workspace_id,id),
  UNIQUE (workspace_id,source_id,contract_id,operator_scope_id,attribute_schema_id,
    retention_policy_id,redaction_policy_id,event_start,event_end,change_start,change_end),
  FOREIGN KEY (workspace_id,source_id,contract_id,operator_scope_id)
    REFERENCES panadan_knowledge.contract_operator_scopes(workspace_id,source_id,contract_id,operator_scope_id) ON DELETE RESTRICT,
  FOREIGN KEY (workspace_id,attribute_schema_id)
    REFERENCES panadan_knowledge.attribute_schema_versions(workspace_id,id) ON DELETE RESTRICT,
  FOREIGN KEY (workspace_id,retention_policy_id)
    REFERENCES panadan_knowledge.policy_versions(workspace_id,id) ON DELETE RESTRICT,
  FOREIGN KEY (workspace_id,redaction_policy_id)
    REFERENCES panadan_knowledge.policy_versions(workspace_id,id) ON DELETE RESTRICT,
  CHECK (event_start<event_end AND extract(epoch FROM event_end-event_start)<=2592000 AND change_start<change_end),
  CHECK ((cursor_time IS NULL)=(cursor_id IS NULL)),
  CHECK (cursor_time IS NULL OR (cursor_time>=change_start AND cursor_time<change_end AND cursor_id>0))
);

CREATE TABLE IF NOT EXISTS panadan_knowledge.sync_runs (
  workspace_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  checkpoint_id uuid NOT NULL,
  cursor_version bigint NOT NULL CHECK (cursor_version>=0),
  state text NOT NULL CHECK (state IN ('succeeded','blocked')),
  examined integer NOT NULL CHECK (examined BETWEEN 0 AND 50),
  accepted integer NOT NULL CHECK (accepted>=0),
  unchanged integer NOT NULL CHECK (unchanged>=0),
  excluded integer NOT NULL CHECK (excluded>=0),
  reason_code text CHECK (reason_code IN ('source_read_failed','revision_conflict','source_scope_changed')),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (workspace_id,id),
  FOREIGN KEY (workspace_id,checkpoint_id)
    REFERENCES panadan_knowledge.sync_checkpoints(workspace_id,id) ON DELETE RESTRICT,
  CHECK ((state='blocked')=(reason_code IS NOT NULL)),
  CHECK ((state='succeeded' AND examined=accepted+unchanged+excluded)
    OR (state='blocked' AND accepted=0 AND unchanged=0 AND excluded=0))
);
CREATE INDEX IF NOT EXISTS knowledge_sync_run_history
  ON panadan_knowledge.sync_runs(workspace_id,checkpoint_id,created_at DESC);

CREATE TABLE IF NOT EXISTS panadan_knowledge.source_exclusions (
  workspace_id uuid NOT NULL,
  run_id uuid NOT NULL,
  external_id bigint NOT NULL CHECK (external_id>0),
  reason_code text NOT NULL CHECK (reason_code IN ('metadata_invalid','transcript_invalid','transcript_review',
    'transcript_oversize','filtered_oversize','transcript_missing','revision_conflict','source_scope_changed')),
  terminal boolean NOT NULL,
  PRIMARY KEY (workspace_id,run_id,external_id),
  FOREIGN KEY (workspace_id,run_id) REFERENCES panadan_knowledge.sync_runs(workspace_id,id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS panadan_knowledge.collection_intents (
  workspace_id uuid NOT NULL,
  resource_revision_id uuid NOT NULL,
  reason text NOT NULL DEFAULT 'revision_changed' CHECK (reason IN ('revision_changed','scope_unavailable')),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (workspace_id,resource_revision_id,reason),
  FOREIGN KEY (workspace_id,resource_revision_id)
    REFERENCES panadan_knowledge.resource_revisions(workspace_id,id) ON DELETE RESTRICT
);

CREATE OR REPLACE FUNCTION panadan_knowledge.collection_uuid(setting_name text)
RETURNS uuid LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $body$
 SELECT CASE WHEN setting_name IN ('panadan.collection_source','panadan.collection_operator')
    AND current_setting(setting_name,true) ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    THEN current_setting(setting_name,true)::uuid ELSE NULL END
$body$;
REVOKE ALL ON FUNCTION panadan_knowledge.collection_uuid(text) FROM PUBLIC;
GRANT USAGE ON SCHEMA panadan_knowledge TO panadan_knowledge_collector;
GRANT EXECUTE ON FUNCTION panadan_knowledge.collection_uuid(text),panadan_knowledge.context_uuid(text),
  panadan_knowledge.scoped_workspace() TO panadan_knowledge_collector;

DO $parent_policies$
DECLARE binding record;
BEGIN
  -- Row locks are required to fence revocation. The lock policy authorizes
  -- row visibility for FOR SHARE and rejects every actual parent update.
  FOR binding IN SELECT * FROM (VALUES
    ('workspaces','id=panadan_knowledge.scoped_workspace()','id'),
    ('principals',$predicate$kind='service' AND authority_namespace=current_setting('panadan.authority_namespace',true)
         AND authority_subject=current_setting('panadan.authority_subject',true)$predicate$,'id'),
    ('memberships',$predicate$workspace_id=panadan_knowledge.scoped_workspace()
         AND EXISTS (SELECT 1 FROM panadan_knowledge.principals p WHERE p.id=memberships.principal_id)$predicate$,'id'),
    ('policy_versions',$predicate$workspace_id=panadan_knowledge.scoped_workspace()
         AND kind IN ('redaction','retention') AND state='approved'$predicate$,'id'),
    ('sources',$predicate$workspace_id=panadan_knowledge.scoped_workspace()
         AND id=panadan_knowledge.collection_uuid('panadan.collection_source')$predicate$,'id'),
    ('source_contract_versions',$predicate$workspace_id=panadan_knowledge.scoped_workspace()
         AND source_id=panadan_knowledge.collection_uuid('panadan.collection_source')$predicate$,'id'),
    ('operator_scopes',$predicate$workspace_id=panadan_knowledge.scoped_workspace()
         AND source_id=panadan_knowledge.collection_uuid('panadan.collection_source')
         AND id=panadan_knowledge.collection_uuid('panadan.collection_operator')$predicate$,'id'),
    ('contract_operator_scopes',$predicate$workspace_id=panadan_knowledge.scoped_workspace()
         AND source_id=panadan_knowledge.collection_uuid('panadan.collection_source')
         AND operator_scope_id=panadan_knowledge.collection_uuid('panadan.collection_operator')$predicate$,'operator_scope_id'),
    ('source_scope_grants',$predicate$workspace_id=panadan_knowledge.scoped_workspace() AND capability='source.collect'
         AND source_id=panadan_knowledge.collection_uuid('panadan.collection_source')
         AND operator_scope_id=panadan_knowledge.collection_uuid('panadan.collection_operator')
         AND EXISTS (SELECT 1 FROM panadan_knowledge.memberships m WHERE m.id=source_scope_grants.membership_id
                      AND m.workspace_id=source_scope_grants.workspace_id)$predicate$,'id'),
    ('attribute_schema_versions','workspace_id=panadan_knowledge.scoped_workspace()','id')
  ) AS bindings(relation,predicate,lock_column)
  LOOP
    EXECUTE format('DROP POLICY IF EXISTS call_collector_read ON panadan_knowledge.%I',binding.relation);
    EXECUTE format('DROP POLICY IF EXISTS call_collector_lock ON panadan_knowledge.%I',binding.relation);
    EXECUTE format('CREATE POLICY call_collector_read ON panadan_knowledge.%I FOR SELECT TO panadan_knowledge_collector USING (%s)',
      binding.relation,binding.predicate);
    EXECUTE format('CREATE POLICY call_collector_lock ON panadan_knowledge.%I FOR UPDATE TO panadan_knowledge_collector USING (%s) WITH CHECK (false)',
      binding.relation,binding.predicate);
    EXECUTE format('GRANT UPDATE (%I) ON panadan_knowledge.%I TO panadan_knowledge_collector',
      binding.lock_column,binding.relation);
  END LOOP;
END
$parent_policies$;

GRANT SELECT (id,state,policy_epoch) ON panadan_knowledge.workspaces TO panadan_knowledge_collector;
GRANT SELECT (id,kind,state,authority_namespace,authority_subject)
  ON panadan_knowledge.principals TO panadan_knowledge_collector;
GRANT SELECT (id,workspace_id,principal_id,state,revoked_at)
  ON panadan_knowledge.memberships TO panadan_knowledge_collector;
GRANT SELECT (id,workspace_id,kind,state,definition) ON panadan_knowledge.policy_versions TO panadan_knowledge_collector;
GRANT SELECT ON panadan_knowledge.sources,panadan_knowledge.source_contract_versions,panadan_knowledge.operator_scopes,
  panadan_knowledge.contract_operator_scopes,panadan_knowledge.source_scope_grants,panadan_knowledge.attribute_schema_versions
  TO panadan_knowledge_collector;

DO $write_policies$
DECLARE binding record;
BEGIN
  FOR binding IN SELECT * FROM (VALUES
    ('sync_checkpoints',$predicate$workspace_id=panadan_knowledge.scoped_workspace()
        AND source_id=panadan_knowledge.collection_uuid('panadan.collection_source')
        AND operator_scope_id=panadan_knowledge.collection_uuid('panadan.collection_operator')$predicate$),
    ('sync_runs',$predicate$workspace_id=panadan_knowledge.scoped_workspace()
        AND EXISTS (SELECT 1 FROM panadan_knowledge.sync_checkpoints c WHERE c.workspace_id=sync_runs.workspace_id
                     AND c.id=sync_runs.checkpoint_id)$predicate$),
    ('source_exclusions',$predicate$workspace_id=panadan_knowledge.scoped_workspace()
        AND EXISTS (SELECT 1 FROM panadan_knowledge.sync_runs r WHERE r.workspace_id=source_exclusions.workspace_id
                     AND r.id=source_exclusions.run_id)$predicate$),
    ('resource_revisions',$predicate$workspace_id=panadan_knowledge.scoped_workspace()
        AND source_id=panadan_knowledge.collection_uuid('panadan.collection_source')
        AND operator_scope_id=panadan_knowledge.collection_uuid('panadan.collection_operator')$predicate$),
    ('resources',$predicate$workspace_id=panadan_knowledge.scoped_workspace()
        AND source_id=panadan_knowledge.collection_uuid('panadan.collection_source')
        AND (current_revision_id IS NULL OR EXISTS (SELECT 1 FROM panadan_knowledge.resource_revisions r
           WHERE r.workspace_id=resources.workspace_id AND r.id=resources.current_revision_id))$predicate$),
    ('representations',$predicate$workspace_id=panadan_knowledge.scoped_workspace()
        AND EXISTS (SELECT 1 FROM panadan_knowledge.resource_revisions r WHERE r.workspace_id=representations.workspace_id
                     AND r.id=representations.resource_revision_id)$predicate$),
    ('collection_intents',$predicate$workspace_id=panadan_knowledge.scoped_workspace()
        AND EXISTS (SELECT 1 FROM panadan_knowledge.resource_revisions r WHERE r.workspace_id=collection_intents.workspace_id
                     AND r.id=collection_intents.resource_revision_id)$predicate$)
  ) AS bindings(relation,predicate)
  LOOP
    EXECUTE format('ALTER TABLE panadan_knowledge.%I ENABLE ROW LEVEL SECURITY',binding.relation);
    EXECUTE format('ALTER TABLE panadan_knowledge.%I FORCE ROW LEVEL SECURITY',binding.relation);
    EXECUTE format('REVOKE ALL ON TABLE panadan_knowledge.%I FROM PUBLIC',binding.relation);
    EXECUTE format('DROP POLICY IF EXISTS call_collector_access ON panadan_knowledge.%I',binding.relation);
    EXECUTE format('CREATE POLICY call_collector_access ON panadan_knowledge.%I FOR ALL TO panadan_knowledge_collector USING (%s) WITH CHECK (%s)',
      binding.relation,binding.predicate,binding.predicate);
  END LOOP;
END
$write_policies$;

GRANT SELECT, UPDATE (cursor_time,cursor_id,cursor_version,finished)
  ON panadan_knowledge.sync_checkpoints TO panadan_knowledge_collector;
GRANT SELECT, INSERT ON panadan_knowledge.sync_runs TO panadan_knowledge_collector;
GRANT INSERT ON panadan_knowledge.source_exclusions,panadan_knowledge.collection_intents TO panadan_knowledge_collector;
GRANT SELECT, INSERT (workspace_id,source_id,external_id), UPDATE (current_revision_id,availability,last_seen_at)
  ON panadan_knowledge.resources TO panadan_knowledge_collector;
GRANT SELECT, INSERT (workspace_id,source_id,resource_id,contract_id,operator_scope_id,rev,source_order,
  source_changed_at,event_at,operation,normalized_metadata,attribute_schema_id,retention_policy_id,availability,transcript_outcome)
  ON panadan_knowledge.resource_revisions TO panadan_knowledge_collector;
GRANT SELECT (workspace_id,resource_revision_id,representation_rev,filtered_digest,redaction_policy_id),
  INSERT (workspace_id,resource_revision_id,representation_rev,text_payload,filtered_digest,redaction_policy_id,availability,expires_at)
  ON panadan_knowledge.representations TO panadan_knowledge_collector;

RESET ROLE;
