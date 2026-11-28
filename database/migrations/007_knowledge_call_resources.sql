-- M02.1 additive owned PG18 schema. Apply in one guarded transaction.
-- Collection and read roles are introduced only with their scoped services.
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
     OR to_regprocedure('panadan_knowledge.scoped_workspace()') IS NULL
  THEN RAISE EXCEPTION 'Refusing knowledge call resource migration: review owned target and prior migrations';
  END IF;
END
$guard$;

SET LOCAL ROLE panadan_knowledge_owner;
SET LOCAL search_path=pg_catalog;

CREATE TABLE IF NOT EXISTS panadan_knowledge.sources (
  workspace_id uuid NOT NULL REFERENCES panadan_knowledge.workspaces(id) ON DELETE RESTRICT,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  source_key text NOT NULL CHECK (source_key ~ '^[a-z][a-z0-9_.-]{0,79}$'),
  kind text NOT NULL DEFAULT 'database' CHECK (kind='database'),
  label text NOT NULL CHECK (char_length(btrim(label)) BETWEEN 1 AND 160 AND char_length(label)<=160),
  connection_ref text NOT NULL CHECK (connection_ref ~ '^[a-z][a-z0-9_.-]{0,79}$'),
  state text NOT NULL DEFAULT 'disabled' CHECK (state IN ('disabled','active','retired')),
  current_contract_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (workspace_id,id),
  UNIQUE (workspace_id,source_key),
  CHECK (state<>'active' OR current_contract_id IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS panadan_knowledge.source_contract_versions (
  workspace_id uuid NOT NULL,
  source_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  rev integer NOT NULL CHECK (rev>0),
  adapter_version text NOT NULL CHECK (adapter_version='synthetic-call-v1'),
  contract jsonb NOT NULL
    CHECK (jsonb_typeof(contract)='object' AND octet_length(contract::text)<=8192),
  state text NOT NULL DEFAULT 'draft' CHECK (state IN ('draft','synthetic','retired')),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (workspace_id,id),
  UNIQUE (workspace_id,source_id,rev),
  UNIQUE (workspace_id,source_id,id),
  FOREIGN KEY (workspace_id,source_id) REFERENCES panadan_knowledge.sources(workspace_id,id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS panadan_knowledge.operator_scopes (
  workspace_id uuid NOT NULL,
  source_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  external_operator_key text NOT NULL CHECK (external_operator_key ~ '^[a-z][a-z0-9_.-]{0,79}$'),
  label text CHECK (char_length(btrim(label)) BETWEEN 1 AND 160 AND char_length(label)<=160),
  state text NOT NULL DEFAULT 'disabled' CHECK (state IN ('disabled','active','revoked')),
  PRIMARY KEY (workspace_id,id),
  UNIQUE (workspace_id,source_id,id),
  UNIQUE (workspace_id,source_id,external_operator_key),
  FOREIGN KEY (workspace_id,source_id) REFERENCES panadan_knowledge.sources(workspace_id,id) ON DELETE RESTRICT
);

-- Scope identity stays stable. Each contract revision binds that identity separately.
CREATE TABLE IF NOT EXISTS panadan_knowledge.contract_operator_scopes (
  workspace_id uuid NOT NULL,
  source_id uuid NOT NULL,
  contract_id uuid NOT NULL,
  operator_scope_id uuid NOT NULL,
  PRIMARY KEY (workspace_id,source_id,contract_id,operator_scope_id),
  FOREIGN KEY (workspace_id,source_id,contract_id)
    REFERENCES panadan_knowledge.source_contract_versions(workspace_id,source_id,id) ON DELETE RESTRICT,
  FOREIGN KEY (workspace_id,source_id,operator_scope_id)
    REFERENCES panadan_knowledge.operator_scopes(workspace_id,source_id,id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS knowledge_contract_operator_scope
  ON panadan_knowledge.contract_operator_scopes(workspace_id,source_id,operator_scope_id);

-- Source and operator permissions are explicit and separate from workspace
-- administration. A source-level grant is not inferred from a missing target.
CREATE TABLE IF NOT EXISTS panadan_knowledge.source_scope_grants (
  workspace_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  membership_id uuid NOT NULL,
  grantor uuid NOT NULL,
  scope_kind text NOT NULL CHECK (scope_kind IN ('source','operator')),
  source_id uuid NOT NULL,
  operator_scope_id uuid,
  capability text NOT NULL CHECK (capability IN ('resource.list','resource.read','representation.read','source.collect')),
  valid_from timestamptz NOT NULL DEFAULT now(),
  valid_until timestamptz,
  revoked_at timestamptz,
  PRIMARY KEY (workspace_id,id),
  FOREIGN KEY (workspace_id,membership_id) REFERENCES panadan_knowledge.memberships(workspace_id,id) ON DELETE RESTRICT,
  FOREIGN KEY (workspace_id,grantor) REFERENCES panadan_knowledge.memberships(workspace_id,id) ON DELETE RESTRICT,
  FOREIGN KEY (workspace_id,source_id) REFERENCES panadan_knowledge.sources(workspace_id,id) ON DELETE RESTRICT,
  FOREIGN KEY (workspace_id,source_id,operator_scope_id)
    REFERENCES panadan_knowledge.operator_scopes(workspace_id,source_id,id) ON DELETE RESTRICT,
  CHECK ((scope_kind='operator') = (operator_scope_id IS NOT NULL)),
  CHECK (valid_until IS NULL OR valid_until>valid_from)
);
CREATE UNIQUE INDEX IF NOT EXISTS knowledge_active_source_scope_grant
  ON panadan_knowledge.source_scope_grants(workspace_id,membership_id,source_id,operator_scope_id,capability)
  NULLS NOT DISTINCT WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS panadan_knowledge.attribute_schema_versions (
  workspace_id uuid NOT NULL REFERENCES panadan_knowledge.workspaces(id) ON DELETE RESTRICT,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  schema_key text NOT NULL CHECK (schema_key='call_metadata'),
  rev integer NOT NULL CHECK (rev>0),
  json_schema jsonb NOT NULL CHECK (jsonb_typeof(json_schema)='object' AND octet_length(json_schema::text)<=8192),
  state text NOT NULL DEFAULT 'draft' CHECK (state IN ('draft','approved','retired')),
  PRIMARY KEY (workspace_id,id),
  UNIQUE (workspace_id,schema_key,rev)
);

CREATE UNIQUE INDEX IF NOT EXISTS knowledge_policy_version_kind
  ON panadan_knowledge.policy_versions(workspace_id,id,kind);

CREATE TABLE IF NOT EXISTS panadan_knowledge.resources (
  workspace_id uuid NOT NULL,
  source_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  external_id text NOT NULL CHECK (external_id ~ '^[1-9][0-9]{0,18}$'),
  resource_type text NOT NULL DEFAULT 'call' CHECK (resource_type='call'),
  current_revision_id uuid,
  availability text NOT NULL DEFAULT 'unknown' CHECK (availability IN ('active','stale','restricted','deleted','unknown')),
  first_seen_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (workspace_id,id),
  UNIQUE (workspace_id,source_id,id),
  UNIQUE (workspace_id,source_id,external_id),
  FOREIGN KEY (workspace_id,source_id) REFERENCES panadan_knowledge.sources(workspace_id,id) ON DELETE RESTRICT,
  CHECK (last_seen_at>=first_seen_at),
  CHECK (availability='unknown' OR current_revision_id IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS panadan_knowledge.resource_revisions (
  workspace_id uuid NOT NULL,
  source_id uuid NOT NULL,
  resource_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  contract_id uuid NOT NULL,
  operator_scope_id uuid NOT NULL,
  rev integer NOT NULL CHECK (rev>0),
  source_order bigint NOT NULL CHECK (source_order>0),
  source_changed_at timestamptz NOT NULL,
  event_at timestamptz NOT NULL,
  observed_at timestamptz NOT NULL DEFAULT now(),
  operation text NOT NULL CHECK (operation IN ('upsert','tombstone')),
  normalized_metadata jsonb NOT NULL DEFAULT '{}' CHECK (
    jsonb_typeof(normalized_metadata)='object'
    AND normalized_metadata - 'duration_seconds' = '{}'::jsonb
    AND CASE jsonb_typeof(normalized_metadata -> 'duration_seconds')
      WHEN 'number' THEN (normalized_metadata ->> 'duration_seconds')::numeric BETWEEN 0 AND 86400
                         AND mod((normalized_metadata ->> 'duration_seconds')::numeric,1)=0
      WHEN 'null' THEN true
      ELSE NOT (normalized_metadata ? 'duration_seconds')
    END),
  attribute_schema_id uuid NOT NULL,
  retention_policy_id uuid NOT NULL,
  retention_policy_kind text GENERATED ALWAYS AS ('retention'::text) STORED,
  availability text NOT NULL CHECK (availability IN ('active','stale','restricted','deleted','unknown')),
  PRIMARY KEY (workspace_id,id),
  UNIQUE (workspace_id,resource_id,rev),
  UNIQUE (workspace_id,resource_id,id),
  FOREIGN KEY (workspace_id,source_id,resource_id)
    REFERENCES panadan_knowledge.resources(workspace_id,source_id,id) ON DELETE RESTRICT,
  FOREIGN KEY (workspace_id,source_id,contract_id,operator_scope_id)
    REFERENCES panadan_knowledge.contract_operator_scopes(workspace_id,source_id,contract_id,operator_scope_id) ON DELETE RESTRICT,
  FOREIGN KEY (workspace_id,attribute_schema_id)
    REFERENCES panadan_knowledge.attribute_schema_versions(workspace_id,id) ON DELETE RESTRICT,
  FOREIGN KEY (workspace_id,retention_policy_id,retention_policy_kind)
    REFERENCES panadan_knowledge.policy_versions(workspace_id,id,kind) ON DELETE RESTRICT,
  CHECK (operation<>'tombstone' OR (availability='deleted' AND normalized_metadata='{}'::jsonb))
);
CREATE INDEX IF NOT EXISTS knowledge_call_revision_scope
  ON panadan_knowledge.resource_revisions(workspace_id,source_id,contract_id,operator_scope_id,event_at,id);

CREATE TABLE IF NOT EXISTS panadan_knowledge.representations (
  workspace_id uuid NOT NULL,
  resource_revision_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  kind text NOT NULL DEFAULT 'filtered_transcript' CHECK (kind='filtered_transcript'),
  representation_rev integer NOT NULL CHECK (representation_rev>0),
  text_payload text,
  filtered_digest text,
  redaction_policy_id uuid NOT NULL,
  redaction_policy_kind text GENERATED ALWAYS AS ('redaction'::text) STORED,
  availability text NOT NULL CHECK (availability IN ('active','stale','restricted','deleted','unknown')),
  expires_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (workspace_id,id),
  UNIQUE (workspace_id,resource_revision_id,kind,representation_rev),
  FOREIGN KEY (workspace_id,resource_revision_id)
    REFERENCES panadan_knowledge.resource_revisions(workspace_id,id) ON DELETE RESTRICT,
  FOREIGN KEY (workspace_id,redaction_policy_id,redaction_policy_kind)
    REFERENCES panadan_knowledge.policy_versions(workspace_id,id,kind) ON DELETE RESTRICT,
  CHECK ((text_payload IS NULL) = (filtered_digest IS NULL)),
  CHECK (text_payload IS NULL OR (octet_length(text_payload) BETWEEN 1 AND 262144
    AND filtered_digest=encode(sha256(convert_to(text_payload,'UTF8')),'hex'))),
  CHECK (availability<>'active' OR text_payload IS NOT NULL),
  CHECK (availability<>'deleted' OR text_payload IS NULL)
);

-- Both parents must exist before adding their current-version pointers.
DO $pointers$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='knowledge_source_current_contract'
                 AND conrelid='panadan_knowledge.sources'::regclass) THEN
    ALTER TABLE panadan_knowledge.sources ADD CONSTRAINT knowledge_source_current_contract
      FOREIGN KEY (workspace_id,id,current_contract_id)
      REFERENCES panadan_knowledge.source_contract_versions(workspace_id,source_id,id) ON DELETE RESTRICT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='knowledge_resource_current_revision'
                 AND conrelid='panadan_knowledge.resources'::regclass) THEN
    ALTER TABLE panadan_knowledge.resources ADD CONSTRAINT knowledge_resource_current_revision
      FOREIGN KEY (workspace_id,id,current_revision_id)
      REFERENCES panadan_knowledge.resource_revisions(workspace_id,resource_id,id) ON DELETE RESTRICT;
  END IF;
END
$pointers$;

DO $rls$
DECLARE target text;
BEGIN
  FOREACH target IN ARRAY ARRAY['sources','source_contract_versions','operator_scopes',
    'contract_operator_scopes','source_scope_grants','attribute_schema_versions','resources','resource_revisions','representations']
  LOOP
    EXECUTE format('ALTER TABLE panadan_knowledge.%I ENABLE ROW LEVEL SECURITY',target);
    EXECUTE format('ALTER TABLE panadan_knowledge.%I FORCE ROW LEVEL SECURITY',target);
    EXECUTE format('REVOKE ALL ON TABLE panadan_knowledge.%I FROM PUBLIC',target);
  END LOOP;
END
$rls$;

RESET ROLE;
