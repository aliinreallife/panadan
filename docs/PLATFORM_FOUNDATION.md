# Panadan platform foundation (v1, opt-in; not deployed)

The new data layer is **separate from the existing source Odoo PostgreSQL**
and from Panadan's existing authentication SQLite. It is designed for
future connectors (Odoo, API, files, event feeds), raw version history,
repeatable processing jobs, and locally served reports.

**Nothing in this feature connects to Odoo, copies actual customer data,
starts a background worker, serves new endpoints, changes authentication,
or switches the dashboard's read path.** The current Odoo report view remains
read-only and the original 503/relay behavior is unchanged.

## Current objects

Apply `database/migrations/001_multisource_foundation.sql` to a **new, owned**
PostgreSQL database. Never apply it to Odoo or to the reporting view.

| Table | Purpose |
| --- | --- |
| `sources` | Registered source connector identity/kind; all new sources are disabled |
| `source_records` | One current state per (`source_key`, `external_id`) |
| `raw_revisions` | Versioned original JSONB snapshots and explicit deletion tombstones |
| `processing_jobs` | Durable versioned per-revision processing queue, processing state |
| `derived_facts` | Structured output with provenance to raw revision and processor version |
| `sync_checkpoints` | Per-source/per-stream JSON cursor, guarded against stale workers |
| `sync_runs` | Aggregate counts and timestamps (never source payloads or credentials) |

The migration is an additive version-1 schema. There is no automated
migration runner, backup/retention/purge procedure, or production DB user
provisioning yet. Design user/role grants for the owned database before any
deployment. Original raw revisions are retained by default: that is **not**
a finalized legal retention or deletion policy. Build retention-aware
purges and privileged maintenance procedures before ingesting personal data.

## Code contracts

- `server/platform_ingest.py` exposes `register_source`,
  `ingest_batch` and `checkpoint`. Registration is **disabled by
  default**; activation is intentionally outside the library, requiring
  explicit owner approval. The library expects a connection to Panadan's
  **own** PostgreSQL with `autocommit=True`, not the source read-only
  `database.connect()` context.
- Inputs are bounded: <=500 events per batch, <=2 MiB per JSON event, <=4 KiB
  JSON cursor; invalid events fail before any database writes.
- Payloads are hashed deterministically. Sending the same unchanged record
  again does not create an additional revision or processing job. A change
  creates a new revision. A delete requires an explicit source tombstone;
  absence from an incomplete page is **never** interpreted as deletion.
- A batch locks its checkpoint row, verifies `expected_cursor`, applies
  revisions, creates processing jobs, records aggregate counts and advances
  the checkpoint in **one transaction**. Stale workers fail rather than
  overwrite the cursor. The connector must use an authoritative ordered
  change feed if multiple streams can update the same source ID.
- `server/platform_processing.py` provides a manual, transactional
  `process_next` worker. Its v1 transformation only extracts a small
  allowlist of public call metadata: direction (`IntoOut` = outgoing,
  `OutToIn` = incoming), call type, AI call status, duration and AI
  estimated sales score. It does **not** copy transcripts, customer names,
  phone numbers or free-text AI recommendations into derived facts. It
  does not claim an AI score proves a completed sale.
- This prototype is intentionally NOT an AI extraction service; model
  settings, human review, quality thresholds, retry/dead-letter strategy,
  processor registries and lineage UIs come later. Future processors can
  produce new versions of derived facts without rewriting raw revisions.
- Current user capabilities, scopes, REST/MCP and WebMCP **are not wired
  to these tables**. The reporting store cannot be exposed until identical
  permission checks—including transcript and direct-call access—are proven.

## How to validate safely

GitHub CI runs a dedicated `platform-integration` job with a disposable
PostgreSQL 18.6 container using **synthetic data only**, and tests:
disabled sources, per-source identity, stable replay, edit revisions,
tombstones, resurrection, stale checkpoint, crash rollback, queue
processing and omission of sensitive fields.

On WSL, existing tests remain unchanged:

```bash
cd ~/panadan
git pull --ff-only
./panadan.sh test
npm test
```

For an **optional** local integration test, create a separate, empty
`panadan_ci` PostgreSQL database on loopback, then explicitly set
`PANADAN_PLATFORM_TEST_DSN` and
`PANADAN_PLATFORM_TEST_ALLOW_RESET=YES` and run
`uv run --locked python -m pytest -q tests/test_platform_ingest.py`.
The integration fixture refuses any other database name or non-loopback host.
**It drops/recreates the `panadan_ingest` schema in that disposable test
database.** Do not run it against a real reporting or identity database.

When ready to provision an owned **empty** reporting database:

```bash
# The DSN must reference a separate authorized Panadan-owned database.
# Avoid putting passwords directly in shell history.
psql "$PANADAN_PLATFORM_DSN" -v ON_ERROR_STOP=1 \
  -f database/migrations/001_multisource_foundation.sql
```

Do not configure source PostgreSQL `PGHOST`/`PGDATABASE` as the target.
Only apply after setting up backup, storage encryption, least-privilege
database roles and source/retention approvals. There is no need to run
this now; the migration is still a preproduction opt-in foundation.

## Next milestones

1. Confirm stable source IDs, view-wide update tracking, tombstone/delete
   feed and legally approved personal-data retention from the Odoo owner
   (see `docs/LOCAL_REPORTING_SYNC.md`). Without them there is **no exact**
   incremental edit/delete sync.
2. Agree on a source onboarding policy: allowed columns, sensitivity
   classification, provenance, consent/retention and connectivity/rate limits.
3. Implement the **read-only Odoo adapter** with a bounded keyset backfill
   and source contract tests. No live copying until permissions are approved.
4. Add controlled worker scheduling, bounded retry/backoff, reconciliation,
   observability and a retention-safe process for raw history purges.
5. Verify locally indexed queries, aggregate parity and **cross-surface
   authorization** before pointing dashboard, REST or MCP at this store.
6. Evaluate Redis/ClickHouse/DuckDB only after real query/worker benchmarks.

This foundation is source-agnostic and forward-compatible, but it is
**not** a completed data warehouse or a running production pipeline.
