-- M01.1: Panadan-owned PostgreSQL 18 only. No source or legacy changes.
-- Run in one transaction, by the explicitly authorized owned DB administrator.
-- The caller must set LOCAL panadan.knowledge_migration_target to the exact DB
-- name. This is an accidental-target guard, NOT proof of operational approval.
-- No automatic invocation from existing platform-db init, auth or web startup.
DO $guard$
BEGIN
  IF current_database() NOT IN ('panadan', 'panadan_ci')
     OR current_setting('server_version_num')::int / 10000 <> 18
     OR current_setting('panadan.knowledge_migration_target', true)
        IS DISTINCT FROM current_database()
     OR current_user <> session_user
     OR (current_database() = 'panadan' AND session_user <> 'panadan_owner')
     OR (current_database() = 'panadan_ci' AND session_user <> 'panadan_ci')
     OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = current_user AND rolsuper)
  THEN
    RAISE EXCEPTION 'Refusing knowledge foundation: requires explicit owned PostgreSQL 18 target and administrator';
  END IF;
END
$guard$;

-- Dedicated owner, not a runtime login. Do not repair or repurpose a conflicting role.
DO $owner$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'panadan_knowledge_owner') THEN
    CREATE ROLE panadan_knowledge_owner NOLOGIN NOINHERIT NOSUPERUSER
      NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  END IF;
  IF EXISTS (
    SELECT 1 FROM pg_roles
    WHERE rolname = 'panadan_knowledge_owner'
      AND (rolcanlogin OR rolinherit OR rolsuper OR rolcreatedb OR rolcreaterole
           OR rolreplication OR rolbypassrls)
  ) OR EXISTS (
    SELECT 1 FROM pg_auth_members m JOIN pg_roles r
      ON r.oid = m.roleid OR r.oid = m.member
    WHERE r.rolname = 'panadan_knowledge_owner'
  ) THEN
    RAISE EXCEPTION 'Conflicting knowledge owner role; review ownership manually';
  END IF;
  IF EXISTS (
    SELECT 1 FROM pg_namespace n JOIN pg_roles r ON r.oid = n.nspowner
    WHERE n.nspname = 'panadan_knowledge' AND r.rolname <> 'panadan_knowledge_owner'
  ) THEN
    RAISE EXCEPTION 'Conflicting knowledge schema owner; refusing to adopt existing schema';
  END IF;
END
$owner$;

CREATE SCHEMA IF NOT EXISTS panadan_knowledge AUTHORIZATION panadan_knowledge_owner;
SET LOCAL ROLE panadan_knowledge_owner;
SET LOCAL search_path = pg_catalog;
REVOKE ALL ON SCHEMA panadan_knowledge FROM PUBLIC;

CREATE TABLE IF NOT EXISTS panadan_knowledge.workspaces (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug TEXT NOT NULL UNIQUE CHECK (slug ~ '^[a-z][a-z0-9_-]{1,62}$'),
  name TEXT NOT NULL CHECK (char_length(btrim(name)) BETWEEN 1 AND 160 AND char_length(name) <= 160),
  state TEXT NOT NULL DEFAULT 'disabled' CHECK (state IN ('disabled','active','suspended')),
  policy_epoch BIGINT NOT NULL DEFAULT 0 CHECK (policy_epoch >= 0),
  timezone TEXT CHECK (char_length(timezone) BETWEEN 1 AND 128 AND btrim(timezone) <> ''),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  lock_version BIGINT NOT NULL DEFAULT 0 CHECK (lock_version >= 0)
);

-- This is only a stable external-identity reference, not an auth account or credential store.
CREATE TABLE IF NOT EXISTS panadan_knowledge.principals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  authority_namespace TEXT NOT NULL CHECK (char_length(authority_namespace) BETWEEN 1 AND 256 AND btrim(authority_namespace) <> ''),
  authority_subject TEXT NOT NULL CHECK (char_length(authority_subject) BETWEEN 1 AND 512 AND btrim(authority_subject) <> ''),
  kind TEXT NOT NULL CHECK (kind IN ('human','service')),
  state TEXT NOT NULL DEFAULT 'disabled' CHECK (state IN ('active','disabled')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  lock_version BIGINT NOT NULL DEFAULT 0 CHECK (lock_version >= 0),
  UNIQUE (authority_namespace, authority_subject)
);

CREATE TABLE IF NOT EXISTS panadan_knowledge.memberships (
  workspace_id UUID NOT NULL REFERENCES panadan_knowledge.workspaces(id) ON DELETE RESTRICT,
  id UUID NOT NULL DEFAULT gen_random_uuid(),
  principal_id UUID NOT NULL REFERENCES panadan_knowledge.principals(id) ON DELETE RESTRICT,
  state TEXT NOT NULL CHECK (state IN ('active','revoked')),
  granted_by UUID REFERENCES panadan_knowledge.principals(id) ON DELETE RESTRICT,
  revoked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  lock_version BIGINT NOT NULL DEFAULT 0 CHECK (lock_version >= 0),
  PRIMARY KEY (workspace_id, id),
  UNIQUE (workspace_id, principal_id),
  -- Additional composite candidate key for audit actor consistency.
  UNIQUE (workspace_id, id, principal_id),
  CHECK ((state = 'revoked') = (revoked_at IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS knowledge_memberships_principal ON panadan_knowledge.memberships(principal_id);
CREATE INDEX IF NOT EXISTS knowledge_memberships_grantor ON panadan_knowledge.memberships(granted_by);

CREATE TABLE IF NOT EXISTS panadan_knowledge.policy_versions (
  workspace_id UUID NOT NULL REFERENCES panadan_knowledge.workspaces(id) ON DELETE RESTRICT,
  id UUID NOT NULL DEFAULT gen_random_uuid(),
  kind TEXT NOT NULL CHECK (kind IN ('access','redaction','retention','validation','disclosure')),
  policy_key TEXT NOT NULL CHECK (policy_key ~ '^[a-z][a-z0-9_.-]{0,79}$'),
  rev INTEGER NOT NULL CHECK (rev > 0),
  definition JSONB NOT NULL CHECK (jsonb_typeof(definition) = 'object' AND octet_length(definition::text) <= 65536),
  state TEXT NOT NULL DEFAULT 'draft' CHECK (state IN ('draft','approved','retired')),
  approved_by UUID,
  approved_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  lock_version BIGINT NOT NULL DEFAULT 0 CHECK (lock_version >= 0),
  PRIMARY KEY (workspace_id, id),
  UNIQUE (workspace_id, kind, policy_key, rev),
  FOREIGN KEY (workspace_id, approved_by)
    REFERENCES panadan_knowledge.memberships(workspace_id, id) ON DELETE RESTRICT,
  CHECK ((state = 'draft' AND approved_by IS NULL AND approved_at IS NULL)
         OR (state IN ('approved','retired') AND approved_by IS NOT NULL AND approved_at IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS knowledge_policy_approver ON panadan_knowledge.policy_versions(workspace_id, approved_by);

-- Minimal metadata-only audit foundation. No payload, transcript, token or secret
-- fields. The command service must later enforce the safe metadata vocabulary,
-- immutable event writes, actual authorization and policy epoch freshness.
CREATE TABLE IF NOT EXISTS panadan_knowledge.audit_events (
  workspace_id UUID NOT NULL REFERENCES panadan_knowledge.workspaces(id) ON DELETE RESTRICT,
  id UUID NOT NULL DEFAULT gen_random_uuid(),
  principal_id UUID REFERENCES panadan_knowledge.principals(id) ON DELETE RESTRICT,
  membership_id UUID,
  channel TEXT NOT NULL CHECK (char_length(channel) BETWEEN 1 AND 32 AND btrim(channel) <> ''),
  action TEXT NOT NULL CHECK (char_length(action) BETWEEN 1 AND 80 AND btrim(action) <> ''),
  target_kind TEXT NOT NULL CHECK (char_length(target_kind) BETWEEN 1 AND 80 AND btrim(target_kind) <> ''),
  target_ref TEXT CHECK (char_length(target_ref) BETWEEN 1 AND 160),
  policy_epoch BIGINT NOT NULL CHECK (policy_epoch >= 0),
  outcome TEXT NOT NULL CHECK (char_length(outcome) BETWEEN 1 AND 32 AND btrim(outcome) <> ''),
  correlation_id UUID NOT NULL,
  safe_metadata JSONB NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(safe_metadata) = 'object' AND octet_length(safe_metadata::text) <= 4096),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (workspace_id, id),
  FOREIGN KEY (workspace_id, membership_id, principal_id)
    REFERENCES panadan_knowledge.memberships(workspace_id, id, principal_id) ON DELETE RESTRICT,
  CHECK (membership_id IS NULL OR principal_id IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS knowledge_audit_time ON panadan_knowledge.audit_events(workspace_id, created_at, id);
CREATE INDEX IF NOT EXISTS knowledge_audit_actor ON panadan_knowledge.audit_events(workspace_id, membership_id, principal_id);
CREATE INDEX IF NOT EXISTS knowledge_audit_principal ON panadan_knowledge.audit_events(principal_id);

-- Stage 1: no policies and no runtime grants. Even the NOLOGIN owner cannot
-- read tenant rows under ordinary RLS. M01.3 adds reviewed scoped policies.
ALTER TABLE panadan_knowledge.memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE panadan_knowledge.memberships FORCE ROW LEVEL SECURITY;
ALTER TABLE panadan_knowledge.policy_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE panadan_knowledge.policy_versions FORCE ROW LEVEL SECURITY;
ALTER TABLE panadan_knowledge.audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE panadan_knowledge.audit_events FORCE ROW LEVEL SECURITY;
REVOKE ALL ON ALL TABLES IN SCHEMA panadan_knowledge FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA panadan_knowledge FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA panadan_knowledge REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA panadan_knowledge REVOKE ALL ON SEQUENCES FROM PUBLIC;
RESET ROLE;
