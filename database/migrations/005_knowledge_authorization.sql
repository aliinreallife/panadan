-- M01.2. Additive, offline-owned PostgreSQL migration. No runtime grants.
DO $guard$
BEGIN
  IF current_database() NOT IN ('panadan','panadan_ci')
     OR current_setting('server_version_num')::int / 10000 <> 18
     OR current_setting('panadan.knowledge_migration_target',true) IS DISTINCT FROM current_database()
     OR current_user <> session_user
     OR (current_database()='panadan' AND session_user<>'panadan_owner')
     OR (current_database()='panadan_ci' AND session_user<>'panadan_ci')
     OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname=current_user AND rolsuper)
     OR NOT EXISTS (SELECT 1 FROM pg_namespace n JOIN pg_roles r ON r.oid=n.nspowner
                    WHERE n.nspname='panadan_knowledge' AND r.rolname='panadan_knowledge_owner'
                    AND NOT (r.rolcanlogin OR r.rolinherit OR r.rolsuper OR r.rolcreatedb
                             OR r.rolcreaterole OR r.rolreplication OR r.rolbypassrls))
     OR EXISTS (SELECT 1 FROM pg_auth_members m JOIN pg_roles r
                ON r.oid=m.roleid OR r.oid=m.member WHERE r.rolname='panadan_knowledge_owner')
     OR to_regclass('panadan_knowledge.memberships') IS NULL
  THEN RAISE EXCEPTION 'Refusing knowledge authorization migration: review owned target and foundation first';
  END IF;
END
$guard$;
SET LOCAL ROLE panadan_knowledge_owner;
SET LOCAL search_path=pg_catalog;

CREATE TABLE IF NOT EXISTS panadan_knowledge.role_versions (
  workspace_id uuid NOT NULL REFERENCES panadan_knowledge.workspaces(id) ON DELETE RESTRICT,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  role_key text NOT NULL CHECK (role_key ~ '^[a-z][a-z0-9_.-]{0,79}$'),
  rev integer NOT NULL CHECK (rev>0),
  name text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 160 AND btrim(name)<>''),
  capability_set jsonb NOT NULL CHECK (jsonb_typeof(capability_set)='array' AND octet_length(capability_set::text)<=4096),
  state text NOT NULL DEFAULT 'draft' CHECK (state IN ('draft','active','retired')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  lock_version bigint NOT NULL DEFAULT 0 CHECK (lock_version>=0),
  PRIMARY KEY(workspace_id,id),
  UNIQUE(workspace_id,role_key,rev)
);
CREATE TABLE IF NOT EXISTS panadan_knowledge.membership_roles (
  workspace_id uuid NOT NULL REFERENCES panadan_knowledge.workspaces(id) ON DELETE RESTRICT,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  membership_id uuid NOT NULL,
  role_version_id uuid NOT NULL,
  granted_by uuid NOT NULL,
  valid_until timestamptz,
  revoked_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  lock_version bigint NOT NULL DEFAULT 0 CHECK(lock_version>=0),
  PRIMARY KEY(workspace_id,id),
  FOREIGN KEY(workspace_id,membership_id) REFERENCES panadan_knowledge.memberships(workspace_id,id) ON DELETE RESTRICT,
  FOREIGN KEY(workspace_id,role_version_id) REFERENCES panadan_knowledge.role_versions(workspace_id,id) ON DELETE RESTRICT,
  FOREIGN KEY(workspace_id,granted_by) REFERENCES panadan_knowledge.memberships(workspace_id,id) ON DELETE RESTRICT,
  CHECK(valid_until IS NULL OR valid_until>created_at),
  CHECK(revoked_at IS NULL OR revoked_at>=created_at)
);
CREATE UNIQUE INDEX IF NOT EXISTS knowledge_active_role_assignment
 ON panadan_knowledge.membership_roles(workspace_id,membership_id,role_version_id) WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS knowledge_role_assignment_version ON panadan_knowledge.membership_roles(workspace_id,role_version_id);
CREATE INDEX IF NOT EXISTS knowledge_role_assignment_grantor ON panadan_knowledge.membership_roles(workspace_id,granted_by);

-- First slice supports only explicit operational workspace scope. Source/operator
-- columns and scoped data grants must arrive with their actual parents in M02.
CREATE TABLE IF NOT EXISTS panadan_knowledge.scope_grants (
  workspace_id uuid NOT NULL REFERENCES panadan_knowledge.workspaces(id) ON DELETE RESTRICT,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  membership_id uuid NOT NULL,
  capability text NOT NULL CHECK (capability IN ('workspace.read','members.manage','roles.manage')),
  scope_kind text NOT NULL DEFAULT 'workspace' CHECK(scope_kind='workspace'),
  data_class text NOT NULL DEFAULT 'operational' CHECK(data_class='operational'),
  purpose text NOT NULL DEFAULT 'workspace_administration' CHECK(purpose='workspace_administration'),
  valid_from timestamptz NOT NULL DEFAULT now(),
  valid_until timestamptz,
  revoked_at timestamptz,
  grantor uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  lock_version bigint NOT NULL DEFAULT 0 CHECK(lock_version>=0),
  PRIMARY KEY(workspace_id,id),
  FOREIGN KEY(workspace_id,membership_id) REFERENCES panadan_knowledge.memberships(workspace_id,id) ON DELETE RESTRICT,
  FOREIGN KEY(workspace_id,grantor) REFERENCES panadan_knowledge.memberships(workspace_id,id) ON DELETE RESTRICT,
  CHECK(valid_until IS NULL OR valid_until>valid_from),
  CHECK(revoked_at IS NULL OR revoked_at>=created_at)
);
CREATE UNIQUE INDEX IF NOT EXISTS knowledge_active_workspace_grant
 ON panadan_knowledge.scope_grants(workspace_id,membership_id,capability,scope_kind,data_class,purpose)
 WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS knowledge_scope_grantor ON panadan_knowledge.scope_grants(workspace_id,grantor);

-- Published role definitions are immutable; replacement requires a new version.
CREATE OR REPLACE FUNCTION panadan_knowledge.guard_role_version() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $body$
BEGIN
  IF TG_OP='DELETE' THEN
    IF OLD.state<>'draft' THEN RAISE EXCEPTION 'Published role versions cannot be deleted'; END IF;
    RETURN OLD;
  END IF;
  IF (NEW.workspace_id,NEW.id,NEW.role_key,NEW.rev,NEW.created_at)
      IS DISTINCT FROM (OLD.workspace_id,OLD.id,OLD.role_key,OLD.rev,OLD.created_at)
     OR (OLD.state<>'draft' AND (NEW.name,NEW.capability_set) IS DISTINCT FROM (OLD.name,OLD.capability_set))
     OR (OLD.state='active' AND NEW.state NOT IN ('active','retired'))
     OR (OLD.state='retired' AND NEW.state<>'retired')
  THEN RAISE EXCEPTION 'Role version identity or published definition is immutable'; END IF;
  RETURN NEW;
END
$body$;
DROP TRIGGER IF EXISTS knowledge_role_version_guard ON panadan_knowledge.role_versions;
CREATE TRIGGER knowledge_role_version_guard BEFORE UPDATE OR DELETE ON panadan_knowledge.role_versions
 FOR EACH ROW EXECUTE FUNCTION panadan_knowledge.guard_role_version();
REVOKE ALL ON FUNCTION panadan_knowledge.guard_role_version() FROM PUBLIC;
ALTER TABLE panadan_knowledge.role_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE panadan_knowledge.role_versions FORCE ROW LEVEL SECURITY;
ALTER TABLE panadan_knowledge.membership_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE panadan_knowledge.membership_roles FORCE ROW LEVEL SECURITY;
ALTER TABLE panadan_knowledge.scope_grants ENABLE ROW LEVEL SECURITY;
ALTER TABLE panadan_knowledge.scope_grants FORCE ROW LEVEL SECURITY;
REVOKE ALL ON ALL TABLES IN SCHEMA panadan_knowledge FROM PUBLIC;
RESET ROLE;
