-- Staging-only sanitized Odoo full-mirror listing. Apply after 001 and 002.
-- No customer names, phones, transcripts, free-text content or raw JSON leave
-- this projection. A separate API authorization check is STILL mandatory.
-- Apply to Panadan-owned PG18 only, never the Odoo source.
DO $guard$
BEGIN
  IF current_database() NOT IN ('panadan_ci', 'panadan') THEN
    RAISE EXCEPTION 'Refusing mirror projection in database %', current_database();
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'panadan_report_reader') THEN
    RAISE EXCEPTION 'Restricted reporting role missing';
  END IF;
END
$guard$;

-- This view must be the sole source of any first-stage local listing.
-- Odoo's JOIN can return more than one row per call. Only expose a call
-- when all variants agree on its identity, operator and source date.
-- Values that disagree (AI score, state, direction, duration) are NULL,
-- never arbitrarily selected from the first analysis.
CREATE OR REPLACE VIEW panadan_ingest.safe_mirror_call_listing_v1
WITH (security_barrier = true) AS
SELECT
    s.source_key,
    s.external_id::bigint AS call_id,
    firstrow.r->>'CALLDATE' AS call_date,
    (firstrow.r->>'vw_danix_base_info_users')::integer AS operator_id,
    jsonb_array_length(envelope.rows) AS source_row_count,
    s.first_observed_at,
    s.last_changed_at,
    CASE
      WHEN firstrow.r->>'tellside' IN ('IntoOut', 'OutToIn')
       AND NOT EXISTS (
          SELECT 1 FROM jsonb_array_elements(envelope.rows) AS variant(r)
          WHERE variant.r->'tellside' IS DISTINCT FROM firstrow.r->'tellside'
       )
      THEN firstrow.r->>'tellside' ELSE NULL
    END AS tellside,
    CASE
      WHEN firstrow.r->>'tellstate' ~ '^[A-Za-z0-9_]{1,60}$'
       AND NOT EXISTS (
          SELECT 1 FROM jsonb_array_elements(envelope.rows) AS variant(r)
          WHERE variant.r->'tellstate' IS DISTINCT FROM firstrow.r->'tellstate'
       )
      THEN firstrow.r->>'tellstate' ELSE NULL
    END AS tellstate,
    CASE
      WHEN firstrow.r->>'aicallinfostate' ~ '^[A-Za-z0-9_]{1,60}$'
       AND NOT EXISTS (
          SELECT 1 FROM jsonb_array_elements(envelope.rows) AS variant(r)
          WHERE variant.r->'aicallinfostate' IS DISTINCT FROM firstrow.r->'aicallinfostate'
       )
      THEN firstrow.r->>'aicallinfostate' ELSE NULL
    END AS aicallinfostate,
    CASE
      WHEN jsonb_typeof(firstrow.r->'voice_length') = 'number'
       AND NOT EXISTS (
          SELECT 1 FROM jsonb_array_elements(envelope.rows) AS variant(r)
          WHERE variant.r->'voice_length' IS DISTINCT FROM firstrow.r->'voice_length'
       )
      THEN firstrow.r->>'voice_length' ELSE NULL
    END AS voice_length_text,
    CASE
      WHEN firstrow.r->>'possibility_of_sale_ai' ~ '^[0-9]{1,3}$'
       AND (firstrow.r->>'possibility_of_sale_ai')::integer BETWEEN 0 AND 100
       AND NOT EXISTS (
          SELECT 1 FROM jsonb_array_elements(envelope.rows) AS variant(r)
          WHERE variant.r->'possibility_of_sale_ai' IS DISTINCT FROM firstrow.r->'possibility_of_sale_ai'
       )
      THEN (firstrow.r->>'possibility_of_sale_ai')::integer ELSE NULL
    END AS ai_sales_score
FROM panadan_ingest.source_records AS s
JOIN panadan_ingest.raw_revisions AS r
    ON r.source_key = s.source_key
   AND r.external_id = s.external_id
   AND r.revision_no = s.revision_no
CROSS JOIN LATERAL (
    SELECT CASE
      WHEN jsonb_typeof(r.payload->'source_rows') = 'array'
      THEN r.payload->'source_rows'
      ELSE '[]'::jsonb
    END AS rows
) AS envelope
CROSS JOIN LATERAL (
    SELECT envelope.rows->0 AS r
) AS firstrow
WHERE
    s.source_key = 'odoo_calls_full_v1'
    AND s.is_deleted = false
    AND r.operation = 'upsert'
    AND r.payload->>'source_schema' = 'odoo_view_37_v1'
    AND s.external_id ~ '^[1-9][0-9]{0,8}$'
    AND r.payload->>'id' = s.external_id
    AND jsonb_array_length(envelope.rows) BETWEEN 1 AND 100
    AND jsonb_typeof(firstrow.r) = 'object'
    AND firstrow.r->>'CALLDATE' ~ '^\\d{4}-\\d{2}-\\d{2}$'
    AND firstrow.r->>'vw_danix_base_info_users' ~ '^[1-9][0-9]{0,8}$'
    AND NOT EXISTS (
        SELECT 1 FROM jsonb_array_elements(envelope.rows) AS variant(r)
        WHERE jsonb_typeof(variant.r) IS DISTINCT FROM 'object'
           OR variant.r->>'id' IS DISTINCT FROM s.external_id
           OR variant.r->'CALLDATE' IS DISTINCT FROM firstrow.r->'CALLDATE'
           OR variant.r->'vw_danix_base_info_users'
              IS DISTINCT FROM firstrow.r->'vw_danix_base_info_users'
    );

REVOKE ALL ON panadan_ingest.safe_mirror_call_listing_v1
    FROM PUBLIC, panadan_ingest_writer, panadan_report_reader;
GRANT SELECT ON panadan_ingest.safe_mirror_call_listing_v1 TO panadan_report_reader;
