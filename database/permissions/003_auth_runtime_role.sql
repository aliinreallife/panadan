-- Dedicated, least-privilege Panadan auth runtime grants.
-- Run as Panadan-owned PostgreSQL schema owner ONLY after role provisioning.
-- No access to source Odoo or ingestion/revision tables.
DO $guard$
BEGIN
  IF current_database() NOT IN ('panadan','panadan_ci')
     OR current_setting('server_version_num')::int / 10000 <> 18 THEN
    RAISE EXCEPTION 'Refusing auth grants outside Panadan PostgreSQL 18';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='panadan_auth_runtime') THEN
    RAISE EXCEPTION 'Create dedicated panadan_auth_runtime role first';
  END IF;
  IF to_regnamespace('panadan_auth') IS NULL THEN
    RAISE EXCEPTION 'Apply migration 003_auth_foundation.sql first';
  END IF;
END
$guard$;

DO $access$
BEGIN
  EXECUTE format('REVOKE ALL ON DATABASE %I FROM panadan_auth_runtime',current_database());
  EXECUTE format('GRANT CONNECT ON DATABASE %I TO panadan_auth_runtime',current_database());
END
$access$;

REVOKE ALL ON SCHEMA panadan_auth FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA panadan_auth FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA panadan_auth FROM PUBLIC;
REVOKE ALL ON SCHEMA panadan_auth FROM panadan_auth_runtime;
GRANT USAGE ON SCHEMA panadan_auth TO panadan_auth_runtime;
REVOKE ALL ON ALL TABLES IN SCHEMA panadan_auth FROM panadan_auth_runtime;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA panadan_auth FROM panadan_auth_runtime;
GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA panadan_auth TO panadan_auth_runtime;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA panadan_auth TO panadan_auth_runtime;
-- No TRUNCATE, REFERENCES, TRIGGER, schema CREATE, ownership, or DDL.
-- Default future tables remain inaccessible until reviewed grants.
ALTER DEFAULT PRIVILEGES IN SCHEMA panadan_auth REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA panadan_auth REVOKE ALL ON SEQUENCES FROM PUBLIC;
