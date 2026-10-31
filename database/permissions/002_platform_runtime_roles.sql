-- Panadan PostgreSQL 18 roles (apply AFTER schema 001 and role creation).
-- Only on Panadan-owned database. Requires both login roles to exist.
-- Never apply this file to the read-only Odoo PostgreSQL database.
--
-- Reader sees ONLY the explicitly allowlisted, sanitized v1 facts. Raw
-- source revisions, transcripts, account metadata and source IDs stay
-- inaccessible. The view exposes only an internal revision ID.
--
-- Guard database identity, not just schema name.
DO $guard$
BEGIN
  IF current_database() NOT IN ('panadan', 'panadan_ci') THEN
    RAISE EXCEPTION 'Refusing Panadan permissions in database %', current_database();
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'panadan_ingest_writer')
     OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'panadan_report_reader') THEN
    RAISE EXCEPTION 'Expected Panadan restricted login roles must exist first';
  END IF;
END
$guard$;

-- Keep future objects closed by default. These roles are NOT owners and
-- cannot CREATE schemas, create tables or register/enable new sources.
DO $revoke$
BEGIN
  EXECUTE format('REVOKE ALL ON DATABASE %I FROM PUBLIC', current_database());
  EXECUTE format('REVOKE ALL ON DATABASE %I FROM panadan_ingest_writer, panadan_report_reader', current_database());
  EXECUTE format('GRANT CONNECT ON DATABASE %I TO panadan_ingest_writer, panadan_report_reader', current_database());
END
$revoke$;

REVOKE ALL ON SCHEMA panadan_ingest FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA panadan_ingest FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA panadan_ingest FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA panadan_ingest TO panadan_ingest_writer, panadan_report_reader;

-- First clear any prior discretionary grants (safe to reapply).
REVOKE ALL ON ALL TABLES IN SCHEMA panadan_ingest FROM panadan_ingest_writer, panadan_report_reader;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA panadan_ingest FROM panadan_ingest_writer, panadan_report_reader;

-- The ingestion library must SELECT the enabled source but must not be
-- allowed to register new sources or turn them on. The separate owner
-- must explicitly approve a source before any import.
GRANT SELECT ON panadan_ingest.sources TO panadan_ingest_writer;
GRANT SELECT, INSERT, UPDATE ON panadan_ingest.source_records TO panadan_ingest_writer;
GRANT SELECT, INSERT ON panadan_ingest.raw_revisions TO panadan_ingest_writer;
GRANT SELECT, INSERT, UPDATE ON panadan_ingest.processing_jobs TO panadan_ingest_writer;
GRANT SELECT, INSERT, UPDATE ON panadan_ingest.derived_facts TO panadan_ingest_writer;
GRANT SELECT, INSERT, UPDATE ON panadan_ingest.sync_checkpoints TO panadan_ingest_writer;
GRANT SELECT, INSERT ON panadan_ingest.sync_runs TO panadan_ingest_writer;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA panadan_ingest TO panadan_ingest_writer;

-- Public v1 fact projection. All output is reconstructed from bounded
-- primitive fields rather than leaking an arbitrary JSONB value.
-- Only the current revision of non-deleted records may be served.
-- Do not expose this view directly to users without API-level RBAC.
CREATE OR REPLACE VIEW panadan_ingest.safe_call_facts_v1
WITH (security_barrier = true) AS
SELECT s.source_key, d.revision_id, d.fact_key,
  CASE d.fact_key
    WHEN 'call_direction' THEN jsonb_build_object(
       'code', d.value->>'code',
       'meaning', CASE d.value->>'code' WHEN 'IntoOut' THEN 'outgoing'
                  WHEN 'OutToIn' THEN 'incoming' END)
    WHEN 'call_type' THEN jsonb_build_object('source_code', d.value->>'source_code')
    WHEN 'ai_call_status' THEN jsonb_build_object('source_code', d.value->>'source_code')
    WHEN 'recording_duration' THEN jsonb_build_object(
       'seconds', CASE WHEN jsonb_typeof(d.value->'seconds') = 'number'
                  THEN (d.value->>'seconds')::numeric END)
    WHEN 'ai_sales_estimate' THEN jsonb_build_object(
       'score_0_100', CASE WHEN jsonb_typeof(d.value->'score_0_100') = 'number'
                      THEN (d.value->>'score_0_100')::numeric END,
       'is_confirmed_sale', false)
  END AS fact_value
FROM panadan_ingest.source_records s
JOIN panadan_ingest.raw_revisions r
  ON r.source_key = s.source_key
 AND r.external_id = s.external_id
 AND r.revision_no = s.revision_no
JOIN panadan_ingest.derived_facts d
  ON d.revision_id = r.revision_id
WHERE s.is_deleted = false
  AND r.operation = 'upsert'
  AND d.processor = 'normalize' AND d.processor_version = 'v1'
  AND (
    (d.fact_key = 'call_direction'
       AND d.value->>'code' IN ('IntoOut', 'OutToIn'))
    OR (d.fact_key IN ('call_type', 'ai_call_status')
       AND d.value->>'source_code' ~ '^[A-Za-z0-9_]{1,60}$')
    OR (d.fact_key = 'recording_duration'
       AND jsonb_typeof(d.value->'seconds') = 'number'
       AND (CASE WHEN jsonb_typeof(d.value->'seconds') = 'number'
                  THEN (d.value->>'seconds')::numeric END) >= 0
       AND (CASE WHEN jsonb_typeof(d.value->'seconds') = 'number'
                  THEN (d.value->>'seconds')::numeric END) < 10000000)
    OR (d.fact_key = 'ai_sales_estimate'
       AND jsonb_typeof(d.value->'score_0_100') = 'number'
       AND (CASE WHEN jsonb_typeof(d.value->'score_0_100') = 'number'
                  THEN (d.value->>'score_0_100')::numeric END) BETWEEN 0 AND 100)
  );

-- A PUBLIC view created by the privileged owner has no PUBLIC grants.
REVOKE ALL ON panadan_ingest.safe_call_facts_v1 FROM PUBLIC, panadan_ingest_writer;
GRANT SELECT ON panadan_ingest.safe_call_facts_v1 TO panadan_report_reader;

-- Deny default future tables/sequences to PUBLIC, explicitly opt in grants
-- for any new schema migration; future data classes are never implicitly
-- exposed to a reader or writer role.
ALTER DEFAULT PRIVILEGES IN SCHEMA panadan_ingest REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA panadan_ingest REVOKE ALL ON SEQUENCES FROM PUBLIC;
