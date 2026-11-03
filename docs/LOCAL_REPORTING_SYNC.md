# Panadan local reporting store: migration and synchronization plan

> **2026-11-03 update:** Production catalog inspection confirmed
> `write_date timestamp without time zone`, and 300 sampled records across
> three ID offsets had non-null dates/unique IDs within each sample.
> The source owner reports that `write_date` advances with edits; controlled
> verification of joined-table updates, UTC-naive semantics and global stable
> IDs is still required. The adapter now allows fixed `write_date` marker
> selection **for supervised, explicitly approved pilot runs only**.
> See [ODOO_WRITE_DATE_PILOT.md](ODOO_WRITE_DATE_PILOT.md) for the complete
> no-secrets procedure. No source data has been copied and production
> dashboard/API/MCP still query Odoo directly.
>

**Status:** proposed architecture, **not deployed**. The authorized source
is `public.vw_danix_call_info_report`, accessible through the private
read-only VPN relay. Do **not** treat existing local SQLite user/auth storage
as the reporting database. Do not migrate, copy customer records, or change
source PostgreSQL grants automatically.

## The question we must answer first

`create_date` is almost certainly **record creation**, not "last modified".
A newly added row can often be found using `id` / `create_date`, but an
existing row may have changes to transcription, AI status, operator,
`deal_value`, or joined details without changing either field.

**A last-ID or last-create-date cursor does not capture updates or deletes.**
Checking the latest 100 rows periodically is not an exact solution: an old
call could be changed today and never appear in those 100 rows.

Odoo normally has `write_date` on underlying model tables when access logs
are enabled. That does not mean the current joined reporting **view** exposes
that column or that one model's `write_date` detects *all* changes affecting
the rendered view row. PostgreSQL native logical replication publishes
**tables**, not regular views, and requires source owner/DBA involvement.
Do not propose turning on logical replication with the existing reporting
account.

## Preflight: read-only VPN audit

```bash
cd ~/panadan
git pull --ff-only
./panadan.sh audit-sync --sample 100
```

The command reports the view kind, count of visible columns, presence of
identity/update/delete marker candidates, *aggregate* distinct-ID behavior
in the newest 100 rows, creation-time ordering inversions, and optional
non-executing PostgreSQL planner estimates for row count/width.

It does **not** return raw IDs, names, customer phone numbers, transcripts,
view SQL definition, or source connection details. It does not execute a full
`COUNT(*)` or `EXPLAIN ANALYZE` and never changes the source. Its estimates
are **not** accurate full table counts or realistic storage budgets. It does
not prove uniqueness over the full view or historical edit detection.

If the VPN is flaky or planning is slow, try:

```bash
./panadan.sh audit-sync --sample 0 --no-explain
./panadan.sh diagnose-db
```

If the source view has no reliable update marker or delete feed, record that
as a source-contract limitation and ask its owner for an improved sync source.

## Observed live audit — 2026-10-31

The source operator successfully ran `./panadan.sh audit-sync --sample 100`
over the existing read-only VPN. Python 162/162 and Node 51/51 tests passed
on that checkout. These are source-observed metadata results, not a
production migration or a comprehensive census.

| Observation | Result | Decision |
| --- | --- | --- |
| Reporting object | Ordinary `view`, 36 columns | No native view-level logical publication or change history |
| Candidate key | Integer `id`; 100/100 sampled IDs populated and distinct | Test **global** stable uniqueness before relying on this as UPSERT key |
| Creation marker | `create_date`, present in all 100 sampled rows | May support initial import/inserts; **not** reliable for updates |
| ID vs creation time | 0 creation-order inversions in the newest 100 rows | Encouraging sample, **not** proof of monotonic history |
| Update markers | None of the audit's recognized names appeared | Exact incremental edits **not available** via observed view |
| Deletion markers | None of the audit's recognized names appeared | Exact delete propagation **not available** via observed view |
| PostgreSQL planner | Estimated 93,396 rows, 3,049 bytes/row | Rough sizing input only, not a measured row count or disk footprint |

Multiplying those two **planner estimates** yields about 285 million bytes
(approximately 272 MiB) for estimated emitted row bytes. This is **not a
storage budget** or a guarantee of on-disk footprint: real text and
transcript sizes, PostgreSQL row/index overhead, TOAST, WAL, backups,
compression and replication can change actual storage substantially.
Do not claim the full history occupies 272 MiB without a measured sample.

**Decision:** The history appears potentially practical to migrate in
small batches, but no live mirror or scheduled ingestion may be called
fully correct until source-owner guarantees address edits and deletes.
A keyset backfill is a reasonable *pilot*, starting with about 100 rows
per batch; measure runtime and failure rate before loading all history.
Keep the existing dashboard source-read path until a local read-path
parity/security test is complete.

**Source owner questions requiring explicit answers:**

1. Is the view's integer `id` globally unique, immutable and never reused?
   Can joins produce multiple rows for one ID?
2. Can a separate sync view or change feed expose a stable change sequence
   or comprehensive `sync_updated_at` for **any field affecting the final
   view row**, including changes to joined models?
3. Can hard deletions, archival and disappearance from the view be emitted
   as tombstone events with the stable ID?
4. What is the approved data-retention scope, particularly phone numbers,
   customer names, transcripts and derived AI text? May these be stored
   in Panadan's own PostgreSQL, and how should source deletions be honored?
5. Are there source rate/batch limits? May Panadan run one read-only
   incremental job at an agreed cadence without overloading production?

If the source owner cannot provide those change semantics, choose a
**best-effort** refresh/reconciliation model with clearly bounded
staleness and explicitly acknowledged inability to detect arbitrary
old-row edits or deletes immediately.

## Recommended source contract (preferred)

Ask the Odoo reporting-view owner for one of:

1. **Best:** a source-maintained, ordered **change feed** with monotonically
   increasing change sequence, stable call ID, change operation (upsert/delete),
   source update version/time, and enough information to fetch the current
   reporting row. Include changes to all underlying tables joined into the
   view, not just the primary Odoo model.
2. **Acceptable for upserts:** a sync view with stable unique ID and reliable
   `sync_updated_at` that changes when *any represented field changes*,
   indexed/supporting bounded keyset polling. Also provide a deletion/tombstone
   feed to detect records that no longer appear.
3. **Best-effort fallback only:** repeat bounded recent-date partitions and
   periodically reconcile older date ranges using keys and hashes. This
   incurs extra source load and **cannot guarantee** capturing arbitrary old
   updates/deletions between reconciliations. If the source cannot provide a
   change signal, honestly document freshness and deletion limitations.

A single `create_date` cursor is **not** option 1 or 2.

## Proposed design

```text
Odoo reporting view / owner-provided change feed
             | READ ONLY, VPN, bounded pages
             v
single dedicated sync worker (backoff + rate limit)
             | transactional UPSERT and checkpoint
             v
Panadan PostgreSQL (source_calls, sync_state, sync_runs)
             |
             +-- dashboard / REST / MCP / WebMCP
             +-- local aggregate tables or indexed queries
             +-- optional Redis only after profiling
```

The source PostgreSQL connection must remain **read-only**; the local
Panadan reporting PostgreSQL is separately authorized to write ingested
data. Keep existing local SQLite authentication/audit records initially;
do not accidentally conflate local reporting and identity databases.

### Initial history import

- Confirm legal/data-owner permission, columns to retain (including whether
  transcripts, names and phone numbers may be copied), retention period and
  whether deleted source records must be purged locally.
- Verify source `id` is **globally unique and stable**. Audit a bounded
  sample first; request full-history guarantees from the owner.
- **Backfill in keyset batches**, e.g. `WHERE id > :last_id ORDER BY id
  LIMIT :batch_size`, starting around **100 records** because the source has
  a 12-second statement timeout and intermittent connectivity. Tune using
  actual measured latency, not an invented full row count.
- Do not use huge `OFFSET` pagination for the backfill. Make batches
  resumable with a durable local cursor. Upsert by stable source ID; write
  the last processed checkpoint **in the same local transaction**.
- Define a finite initial ID upper bound or a source snapshot strategy;
  catch inserts/changes arriving during the backfill through the incremental
  feed. If only the view is exposed, guarantee of snapshot consistency across
  disconnected batches is not available.
- Validate sample source vs local counts and non-sensitive per-batch checksums.
  Never embed customer content in sync logs, alert payloads or GitHub CI.
- Size the local DB by *actual* average record and transcript sizes and
  retention before committing to a storage budget. Planner estimates alone
  are not enough to decide whether the entire view will fit.

### Ongoing sync

- A **single worker** (systemd timer or containerized job) executes a
  bounded run every **2–5 minutes initially**; cadence is a proposed pilot,
  to tune with the source owner and observed DB load. No dashboard request
  should directly initiate a source query after cutover.
- Maintain `last_successful_change_cursor`, high-water mark and run status
  in the local PostgreSQL DB; use a stable compound key such as
  `(sync_updated_at, id)` when that contract is guaranteed, with a
  **small overlap window**, idempotent upserts, and correct keyset ordering.
  Do not advance the checkpoint before the local write commits.
- For a sequence-number feed, acknowledge/delete event checkpoints
  transactionally; for a timestamp watermark, re-read overlapping intervals
  and verify monotonic consistency.
- Process deletes as tombstones or validated change-feed operations;
  apply a retention/deletion policy locally. Never assume a missing row
  in an arbitrary partial query proves deletion.
- Retry transient VPN/source failures with **exponential backoff and jitter**
  while leaving the last successfully ingested local data available. Expose
  `last_successful_sync`, lag in minutes, failed runs, rows processed,
  backlog and duplicate/invalid records. Alert on sustained failures.
- Run scheduled reconciliation within defined date/ID partitions. Monitor
  source schema drift; new columns must not be silently ingested.

### Local read path and Redis

- Serve the **same** local PostgreSQL view/repository to dashboard, REST,
  MCP, WebMCP and metrics. Reapply strict permission checks on every surface,
  including direct call-by-ID and transcript access. Team/destination
  directory tags are **not currently RBAC**.
- Use Postgres indexes on date, stable operator key, source status/direction
  and the sync cursor based on real query plans; validate OR-filter plans.
  Consider local aggregate tables for KPI queries. Keep data access
  parameterized; separate sensitive transcripts/phones from list metadata.
- Prefer **PostgreSQL only for the first release**. Redis may later cache
  public-safe derived metric responses by filter, authorization scope,
  sync generation and short TTL; never accidentally share customer data
  between users or use Redis as the only durable checkpoint store.
- Use atomic cutover + rollback toggle after side-by-side parity checks.
  Stale data must be clearly timestamped; no connection failures during sync
  should hide the last successful local report.

## Stop conditions before implementing live mirror

1. Evidence for exact view size, ID stability, query latency and column
   change semantics is insufficient until the local read-only audit runs.
2. We **cannot promise accurate edit/deletion propagation** with only the
   currently documented view.
3. Approval is needed for retaining customer-identifying/transcript data and
   for source owner cooperation on a sync marker or change feed.
4. RBAC must be enforced consistently before exposing broader cached local
   results. Do not launch this as a second, less restricted reporting API.
