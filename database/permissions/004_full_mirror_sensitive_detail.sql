-- Draft, additive, owner-executed migration for *sensitive* Odoo detail.
-- Apply on Panadan-owned PG18 after 001, 002 and 003. Never on Odoo.
-- A separate dedicated login role panadan_mirror_sensitive_reader must exist
-- and its credentials MUST be isolated from the normal dashboard/report role.
-- Database view access is NOT end-user authorization: the application MUST
-- verify a current Panadan principal + numeric operator grant, and audit the
-- attempt BEFORE issuing a detail read. No HTTP/MCP endpoint is enabled.
DO $guard$
BEGIN
    IF current_database() NOT IN ('panadan', 'panadan_ci') THEN
        RAISE EXCEPTION 'Refusing sensitive mirror migration on unexpected DB';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname='panadan_mirror_sensitive_reader'
        AND NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole
        AND NOT rolbypassrls AND NOT rolreplication
    ) THEN
        RAISE EXCEPTION 'Dedicated unprivileged mirror detail role required';
    END IF;
    IF to_regclass('panadan_ingest.safe_mirror_call_listing_v1') IS NULL THEN
        RAISE EXCEPTION 'Apply the sanitized mirror listing migration first';
    END IF;
END
$guard$;

-- 002 revoked PUBLIC database CONNECT; grant only CONNECT to this new role.
-- No TEMP, CREATE, table-owner or raw-table privileges.
DO $db_connect$
BEGIN
    EXECUTE format(
        'REVOKE ALL ON DATABASE %I FROM panadan_mirror_sensitive_reader',
        current_database()
    );
    EXECUTE format(
        'GRANT CONNECT ON DATABASE %I TO panadan_mirror_sensitive_reader',
        current_database()
    );
END
$db_connect$;

REVOKE ALL ON SCHEMA panadan_ingest FROM PUBLIC;
GRANT USAGE ON SCHEMA panadan_ingest TO panadan_mirror_sensitive_reader;

-- Revoke direct access even if an older deployment incorrectly granted it.
REVOKE ALL ON ALL TABLES IN SCHEMA panadan_ingest
    FROM panadan_mirror_sensitive_reader;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA panadan_ingest
    FROM panadan_mirror_sensitive_reader;
REVOKE ALL ON FUNCTION panadan_ingest.lock_source_for_ingest(TEXT)
    FROM panadan_mirror_sensitive_reader;

-- Require the SAME current-state + unambiguous-operator predicate as 003.
-- Preserve ALL joined source rows verbatim: no arbitrary winner among the
-- multiple analyses sharing one id, and no stale historical revision.
-- This returns deliberately sensitive fields and must never be granted to
-- the ordinary reporting reader, ingest writer or PUBLIC.
CREATE OR REPLACE VIEW panadan_ingest.sensitive_mirror_call_detail_v1
WITH (security_barrier = true) AS
SELECT
    l.source_key,
    l.call_id,
    l.operator_id,
    l.source_row_count,
    r.revision_no,
    r.ingested_at,
    r.payload->'source_rows' AS source_rows
FROM panadan_ingest.safe_mirror_call_listing_v1 AS l
JOIN panadan_ingest.source_records AS s
  ON s.source_key=l.source_key
 AND s.external_id=l.call_id::text
 AND s.is_deleted=false
JOIN panadan_ingest.raw_revisions AS r
  ON r.source_key=s.source_key
 AND r.external_id=s.external_id
 AND r.revision_no=s.revision_no
WHERE l.source_key='odoo_calls_full_v1'
  AND r.operation='upsert'
  AND r.payload->>'source_schema'='odoo_view_37_v1'
  AND jsonb_typeof(r.payload->'source_rows')='array';

REVOKE ALL ON panadan_ingest.sensitive_mirror_call_detail_v1
    FROM PUBLIC, panadan_ingest_writer, panadan_report_reader,
         panadan_mirror_sensitive_reader;
GRANT SELECT ON panadan_ingest.sensitive_mirror_call_detail_v1
    TO panadan_mirror_sensitive_reader;
