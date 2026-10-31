-- Panadan multi-source data platform, migration v1.
-- Applies only to Panadan's OWN PostgreSQL, never the source Odoo database.
-- No credentials, source connectors, retention policy, or live ingestion.
CREATE SCHEMA IF NOT EXISTS panadan_ingest;

CREATE TABLE IF NOT EXISTS panadan_ingest.sources (
    source_key TEXT PRIMARY KEY
        CHECK (source_key ~ '^[a-z][a-z0-9_-]{1,62}$'),
    kind TEXT NOT NULL CHECK (kind IN ('database', 'api', 'file', 'event', 'manual')),
    label TEXT NOT NULL CHECK (char_length(label) BETWEEN 1 AND 120),
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Current state/canonical key is separate from immutable-history-by-convention.
-- Uniqueness here is per source; numeric source IDs are NOT assumed global.
CREATE TABLE IF NOT EXISTS panadan_ingest.source_records (
    source_key TEXT NOT NULL REFERENCES panadan_ingest.sources(source_key),
    external_id TEXT NOT NULL CHECK (char_length(external_id) BETWEEN 1 AND 512),
    revision_no BIGINT NOT NULL DEFAULT 0 CHECK (revision_no >= 0),
    current_digest TEXT CHECK (current_digest ~ '^[0-9a-f]{64}$'),
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    first_observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (source_key, external_id)
);

CREATE TABLE IF NOT EXISTS panadan_ingest.raw_revisions (
    revision_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_key TEXT NOT NULL,
    external_id TEXT NOT NULL,
    revision_no BIGINT NOT NULL CHECK (revision_no > 0),
    operation TEXT NOT NULL CHECK (operation IN ('upsert', 'delete')),
    payload JSONB,
    digest TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_key, external_id, revision_no),
    FOREIGN KEY (source_key, external_id)
        REFERENCES panadan_ingest.source_records(source_key, external_id),
    CHECK (
        (operation = 'upsert' AND payload IS NOT NULL AND digest ~ '^[0-9a-f]{64}$')
        OR (operation = 'delete' AND payload IS NULL AND digest IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS raw_revisions_by_source
    ON panadan_ingest.raw_revisions(source_key, ingested_at, revision_id);

-- One durable job per revision, processor and pipeline version; payload is NOT logged.
CREATE TABLE IF NOT EXISTS panadan_ingest.processing_jobs (
    job_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    revision_id BIGINT NOT NULL REFERENCES panadan_ingest.raw_revisions(revision_id),
    processor TEXT NOT NULL CHECK (char_length(processor) BETWEEN 1 AND 80),
    processor_version TEXT NOT NULL CHECK (char_length(processor_version) BETWEEN 1 AND 80),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'succeeded', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    last_error_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    UNIQUE (revision_id, processor, processor_version)
);
CREATE INDEX IF NOT EXISTS processing_jobs_queued
    ON panadan_ingest.processing_jobs(status, job_id);

-- Extracted normalized values ALWAYS retain the exact raw revision/provenance.
CREATE TABLE IF NOT EXISTS panadan_ingest.derived_facts (
    fact_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    revision_id BIGINT NOT NULL REFERENCES panadan_ingest.raw_revisions(revision_id),
    processor TEXT NOT NULL,
    processor_version TEXT NOT NULL,
    fact_key TEXT NOT NULL,
    value JSONB NOT NULL,
    confidence NUMERIC(5,4) CHECK (confidence BETWEEN 0 AND 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (revision_id, processor, processor_version, fact_key)
);

-- Cursor and raw upserts must commit in ONE transaction. A source stream may
-- be append-only, timestamp-based or a true source change feed.
CREATE TABLE IF NOT EXISTS panadan_ingest.sync_checkpoints (
    source_key TEXT NOT NULL REFERENCES panadan_ingest.sources(source_key),
    stream TEXT NOT NULL CHECK (char_length(stream) BETWEEN 1 AND 80),
    cursor JSONB,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (source_key, stream)
);

CREATE TABLE IF NOT EXISTS panadan_ingest.sync_runs (
    run_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_key TEXT NOT NULL REFERENCES panadan_ingest.sources(source_key),
    stream TEXT NOT NULL,
    examined INTEGER NOT NULL DEFAULT 0 CHECK (examined >= 0),
    changed INTEGER NOT NULL DEFAULT 0 CHECK (changed >= 0),
    deleted INTEGER NOT NULL DEFAULT 0 CHECK (deleted >= 0),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (changed + deleted <= examined)
);

-- No tables in this schema are connected to /dashboard, REST or MCP today.


-- A restricted writer must lock source enablement for the full ingest batch.
-- PostgreSQL FOR SHARE requires UPDATE privilege on the underlying table;
-- never give runtime ingestion UPDATE on the source registry merely to lock it.
-- This narrowly scoped, owner-executed function performs only the row lock.
-- It returns NULL for an unregistered source; callers reject NULL/FALSE.
CREATE OR REPLACE FUNCTION panadan_ingest.lock_source_for_ingest(p_source_key TEXT)
RETURNS BOOLEAN
LANGUAGE SQL
SECURITY DEFINER
SET search_path = pg_catalog
AS $source_lock$
    SELECT enabled
    FROM panadan_ingest.sources
    WHERE source_key = p_source_key
    FOR SHARE;
$source_lock$;
-- PostgreSQL otherwise defaults new FUNCTION EXECUTE privileges to PUBLIC.
-- The separate restricted-role migration explicitly grants only the writer.
REVOKE ALL ON FUNCTION panadan_ingest.lock_source_for_ingest(TEXT) FROM PUBLIC;
