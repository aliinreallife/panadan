# Panadan Odoo `write_date` synchronization — guarded pilot (2026-11-03)

**Status: Code ready for isolated tests; NO production synchronization, automatic
schedule, live source copying, or dashboard/API/MCP cutover has been enabled.**

## What is verified, and what is not

- Actual source: `public.vw_danix_call_info_report` in Odoo, accessible through
  Panadan's read-only VPN connection.
- Source columns observed in production: `id integer`, `write_date timestamp
  without time zone`. Three 100-row samples (offset 0, 1000, 5000) had
  100/100 non-null IDs, unique IDs within each sample, 100/100 populated
  `write_date`, and no `write_date < create_date`.
- Source owner said `write_date` changes when records change. A controlled
  before/after demonstration that **joined operator/team/stage edits** update
  the *view row's marker* is still required, along with global ID uniqueness
  and the convention that a naive timestamp represents UTC.
- Prior planning-only view estimate: 93,396 rows at 3,049 bytes/row, ~272 MiB
  emitted row width; **not measured storage size** or current row count.
  Full source includes potentially large transcripts; pilot never fetches
  them, customer phone numbers, names, or arbitrary AI text.
- Deletion detection is NOT implemented: disappearing rows do not produce
  tombstones. Define bounded source-ID reconciliation and privacy purge
  contract before treating the local copy as authoritative.
- No benchmark establishes safe full-load throughput/cadence yet. The
  source has a 12-second statement timeout and an intermittently failing VPN.

## Implemented

- An explicit `write_date` SQL column **allowlist** (lower priority than
  `sync_updated_at` and `updated_at`), UTC-naive timestamp handling,
  keyset ID pagination and `(write_date,id)` update pagination.
- Transactional local ingest, idempotent replay, persisted page cursors,
  60-second source-time settling delay and 5-minute overlap.
- Operator-only `server.odoo_sync_pilot` with read-only `preview`,
  local `status`, explicit `seed` (must precede backfill), bounded
  `backfill`, `updates` and combined serial `sync-once`.
- Local target must be Panadan-owned PG18, `panadan` database, restricted
  `panadan_ingest_writer` role and `panadan-auth-postgres:5432` alias.
  An absolute small, private 0600 DSN file is read **inside the process**;
  no database DSN/password or customer row is accepted as CLI args or printed.
  Hostaddr, service, libpq option overrides and wrong target names are refused.
- Every mutation requires all three `--ack-source-contract`,
  `--ack-retention` and `--ack-copy` flags. Existing owner-side
  `panadan_ingest.sources.enabled` must have been explicitly set true;
  this CLI cannot register or enable it. A session-scoped advisory lock
  serializes backfill and updates across processes.
- No automatic retry storm, auto-deploy or autonomous schedule. Errors
  leave last committed page checkpoint in place. Code is a supervised pilot.

## Test safely, without source VPN or production

On a checkout containing this PR, with uv/Python 3.13 installed:

```bash
cd ~/panadan
./panadan.sh test tests/test_odoo_sync_adapter.py tests/test_odoo_write_date_pilot.py
```

CI also runs the PG18 synthetic integration suite against a **disposable**
`panadan_ci` database, with no actual source rows. Verify those CI jobs PASS
before merging. Test read-only source metadata/preview **only after a reviewed
image deployment into the approved service namespace**:

```bash
# Runs in the Panadan Web container which already has Odoo readonly credentials:
sudo docker exec panadan-web-1 python -m server.odoo_sync_pilot preview \
  --mode utc_naive --batch-size 100
```

Expected: `PREVIEW: {'marker': 'write_date', 'rows_examined': ...,
'target_unchanged': True, ...}`. This operation reads no more than 100
allowlisted rows, prints only aggregate numbers and writes nothing.
**Do not deploy by bare `panadan.sh up/down`**, `docker compose up` with a
partial overlay, or manually restarting Plane, VPN, Caddy or PG18.
Use the reviewed production release controller and maintenance approval.

## Requirements BEFORE ANY real source copy

1. Operator/DBA verifies old-row **and joined-table** update propagation,
   source timestamp UTC-naive semantics, global stable ID, deletion policy,
   and acceptable source-query load. Do not treat a verbal "yes" alone as
   complete proof. If a required joined edit does not advance the marker,
   add a source-maintained `sync_updated_at` before the pilot.
2. Data owner signs off legal purpose, allowlisted fields, retention period,
   copied-data backups, incident/audit handling and what happens when source
   records are deleted. Original Odoo reporting role remains READ ONLY.
3. Verify private owned PG18 backup/recovery, least-privilege writer role,
   auth/ingest isolation, source registry default-disable and the
   `panadan-auth-db` network from `./panadan.sh owned-pg verify`.
   Never use `panadan_owner`, `report_user`, Odoo credentials, or `.env.db`
   as the target DSN.
4. Using the **reviewed production deployment controller**, deliberately
   mount a new separate file readable only inside the authorized pilot
   runtime, containing a *single* libpq DSN for
   `panadan_ingest_writer@panadan-auth-postgres:5432/panadan`
   (private credentials, 0600; do not paste into chats, logs, shell history,
   command arguments, or issues). Set `PANADAN_SYNC_OWNED_DSN_FILE` to its
   **in-container absolute path only**. Do not mount privileged credentials,
   Odoo configuration files or Docker sockets. Test the file is private.
   **This mount/setup is NOT made by this PR.**
5. The DB owner, in a separate reviewed operation, registers
   `source_key='odoo_calls'`, `kind='database'`, and explicitly enables
   it *only after* approvals, backups and safe runtime config are verified.
   Registration alone remains disabled and a writer cannot enable sources.

Do NOT run the steps below on production just to try the feature. They are
operator procedures for a later explicitly approved and staged pilot.

## Operator-driven sequence (inside already-approved Web/VPN namespace)

```bash
# Environment must already contain PANADAN_SYNC_OWNED_DSN_FILE and a valid
# private restricted-writer file. No credentials are passed in argv.
python -m server.odoo_sync_pilot status

# Seed update cursor BEFORE any backfill; seed is one-time only.
python -m server.odoo_sync_pilot seed --mode utc_naive \
  --ack-source-contract --ack-retention --ack-copy

# Copy 100 non-sensitive calls once, then manually inspect status:
python -m server.odoo_sync_pilot backfill --mode utc_naive \
  --batch-size 100 --max-pages 1 \
  --ack-source-contract --ack-retention --ack-copy

python -m server.odoo_sync_pilot status

# Only after the first 100 records match the original with approved checks:
# Up to 5 x 100 ID rows per invocation (resumes from last ID).
python -m server.odoo_sync_pilot backfill --mode utc_naive \
  --batch-size 100 --max-pages 5 \
  --ack-source-contract --ack-retention --ack-copy

# One manually approved, serial new-ID and changed-old-ID cycle:
python -m server.odoo_sync_pilot sync-once --mode utc_naive \
  --batch-size 100 --max-pages 2 \
  --ack-source-contract --ack-retention --ack-copy
```

Each output is counts only: `examined`, `changed`, `unchanged`, `more`.
`more=true` means another bounded invocation may be needed. A failed or
interrupted page does NOT advance its local cursor. Ingest repeats with the
same digest do not create duplicate revisions. Never manually reset a
checkpoint, disable a source mid-pilot, or run two workers concurrently.

## Suggested future cadence (NOT ACTIVE)

After a 100-record pilot, proof of update coverage, a full bounded
backfill, measured DB impact, failover rehearsal, and deletion/retention
policy approval, schedule one `sync-once` process every **5 minutes**.
Use a single non-overlapping systemd timer with a lock; keep per-cycle
pages limited to avoid overloading Odoo. The timer must stay **disabled**
until approved. Log only summarized counts/health, not payloads or credentials.
Compare source count by approved, timeout-bounded aggregates and local
counts. Alert on sync lag, failed runs, timestamp drift, schema changes,
VPN downtime and sample parity mismatch.

## Not yet done: dashboard cutover

`database.list_calls`, detail, stats, REST and MCP still read the Odoo view.
This first-stage storage only includes the eight previously approved
non-sensitive columns plus `write_date`; it **cannot** reproduce all
source fields, especially call details, transcripts and operator metadata.
No production dashboard cutover is safe without a deliberate field-level
approval, sanitized per-user reporting SQL, data parity checks, scoped
authorization on **every** access surface and tested rollback.

**To verify live state:** check a real production `SELECT 1` over the VPN;
run `preview` without target DSN; run local `status` only when the private
target role is mounted; review CI synthetic tests. Do not confuse local PG
availability with actual imported customer records.
