# Odoo sync: initial backfill + new rows + existing-row updates

**Implementation status:** read-only adapter + page coordinator + synthetic
PostgreSQL integration tests. **No live connector, cron, background worker,
Odoo migration, customer-data copy or dashboard cutover is enabled.**

Panadan may proceed using **only** a reliable `updated_at` (or
`sync_updated_at`) field and a stable integer `id`. A delete feed is
*optional for a best-effort pilot*, but its absence means no real-time
detection of deleted/disappeared records.

## Required source contract

1. Keep `id` stable, globally unique and monotonically increasing for new
   calls. Historical duplicates or backfilled older IDs require
   reconciliation outside the append-only ID poller.
2. Add **either** `updated_at` **or** `sync_updated_at` to
   `public.vw_danix_call_info_report` as a PostgreSQL timestamp. The
   marker must become newer whenever **any field returned by the view
   changes** (including joined tables), including edits to *old* calls.
   This cannot be proved by column presence alone.
3. Specify whether it is `timestamp without time zone` containing
   UTC-naive values (`utc_naive`), or real `timestamptz`
   (`timestamptz`). The adapter **requires explicit mode** and fails
   closed on missing/wrong type or null per-row timestamps.
4. The reported timestamp must not be arbitrarily backdated. The default
   60-second settling delay and 5-minute overlap improve resilience
   against late commits but **do not mathematically guarantee** no missed
   out-of-order changes. A sequence-based feed would be stronger.
5. Obtain permission to retain the selected source fields; this prototype
   reads **only non-sensitive allowlisted fields**. It never selects
   customer names, phone numbers, transcripts or AI prose.

## Three flows — all required

- **Initial ID backfill:** bounded `WHERE id > last_id ORDER BY id LIMIT
  100` pages. Checkpoints and raw revisions commit atomically on Panadan's
  own PostgreSQL. No massive OFFSET/full-table transfer.
- **New calls after backfill:** resume that **same saved ID cursor** on
  every scheduled run. This catches newly created calls with IDs above
  previous high water, even if their timestamps are unexpectedly old.
- **Updates to existing calls:** separately poll by
  `(updated_at, id)` using fixed windows, stable ordering, and bounded
  pages. A changed old ID becomes a new raw revision, not a new call
  identity. Timestamp ties are handled with the ID secondary cursor.

**Important ordering:** seed the update cursor from the source database
clock **before** beginning the initial ID backfill, then process the ID
backfill and update windows. All streams for one source should execute
**serially**, not concurrently, so their snapshots cannot overwrite
one another out of order. If one query fails, no local checkpoint advances.

The selected timestamp-column name is persisted with the cursor. If a
view deployment switches columns from `updated_at` to
`sync_updated_at`, the connector stops and requires explicit operator
review rather than silently continuing with incompatible state.

Default batch size is 100; a strict upper bound of 200 protects the
source view. Plan to benchmark and agree on a poll interval (for example
5 minutes) once the server owner verifies the source load.

## What does NOT work with updated_at alone

- **Hard deletion** of a row makes it disappear from the view. Its
  timestamp is no longer readable. We will need periodic, bounded,
  source-ID reconciliation (with a cautious grace period), or an eventual
  deletion/tombstone source. Do not infer deletion from one incomplete
  page or a transient VPN timeout.
- **Late commits past the overlap**, incorrect/non-monotonic timestamps,
  updates to joined tables that do not advance the marker, and insertion
  with reused/older IDs can evade the normal incremental cursors.
- A matching source ID is not inherently proof of source deletion or a
  lawful authorization to retain a historical raw revision. Define
  deletion/retention and privacy-purge handling before copying actual
  customer data.

## Code now in the repository

`server/odoo_sync_adapter.py` provides:

- `validate_schema` — read-only catalog validation, accepts only the
  two fixed timestamp column names, no dynamic untrusted SQL.
- `read_id_page` — keyset query for both history and new IDs.
- `read_change_page` — keyset query for updates in a source-time window,
  including ID tie-breaks.
- `initial_change_cursor`, `plan_change_window` and
  `change_next_cursor` — JSON-serializable durable cursor logic with
  window freezing across pages, bounded overlap and settling delay.
- Strict row normalization to a **fixed approved field allowlist**.

`server/odoo_sync_coordinator.py` provides:

- `seed_update_stream` (must be first),
- `poll_id_page` (initial import + ongoing new calls),
- `poll_update_page` (changed old calls).

They call the existing transactional `platform_ingest.ingest_batch`
on a **different** Panadan-owned PostgreSQL connection. All source SQL
is SELECT-only, parameterized, and uses the same read-only connection
conventions as `server/database.py`.

The coordinator **is not exposed through CLI, REST or MCP** and does
not create or enable a source by itself. The existing platform source
registry defaults to disabled. This deliberately prevents accidental
real data ingestion before approval.

## Safe next actions

1. Get `updated_at` or `sync_updated_at` added to the view; ask the
   owner to demonstrate edits to an *old call*, and a field joined from
   another table, both advance the timestamp. Verify source ID semantics.
2. Run the existing catalog audit (no row payloads):
   ```bash
   cd ~/panadan
   git pull --ff-only
   ./panadan.sh audit-sync --sample 100
   ```
   Check that `update_marker_candidates` now lists the new field.
3. Agree on which source fields can be copied, storage location, backup,
   retention and deletion policy. Build/approve a separate Panadan-owned
   PostgreSQL instance with least-privilege credentials.
4. Once approved, implement a carefully gated pilot runner using these
   libraries, starting with 100 records and verifying local vs source
   counts/IDs. Then add a supervised schedule and source reconciliation.
5. Only after parity, authorization and freshness testing, switch
   dashboard/REST/MCP read paths to the local database. Redis is still
   unnecessary at this stage.

### Local validation

```bash
./panadan.sh test
npm test
```

The normal WSL Python suite skips integration tests unless the safe
disposable `panadan_ci` PostgreSQL database and explicit guard
environment are configured. GitHub CI runs those integration tests using
synthetic data only, including old-row edits, new IDs, same-timestamp
pagination, overlap replay and source-marker-missing failure.
