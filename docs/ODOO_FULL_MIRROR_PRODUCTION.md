# Production contract — full-fidelity, update-only Odoo reporting mirror

**Decision captured: 2026-11-04. Status: design contract / implementation required; NOT enabled in production.**

## Goal

Panadan will maintain its own durable PostgreSQL 18 copy of **every field exposed by the one authorized, read-only** Odoo reporting view, `public.vw_danix_call_info_report`. After validated synchronization and authorization, the dashboard, API and MCP should be able to read locally without an Odoo round trip for each request.

This **replaces the earlier proposed seven-day/limited-field production target**. The existing 100-record, eight-field code is a connectivity/safety pilot only; it is NOT a full mirror and MUST NOT be presented as production-complete.

## Required semantics

| Source situation | Target behavior |
| --- | --- |
| New stable call ID | Insert one current record and its initial revision. |
| Existing ID, source payload changed | Update the current record and append a new revision with provenance. |
| Existing ID, payload unchanged | Do nothing to current data or revision history; idempotent replay. |
| Record disappears from source view | **Do not automatically delete or tombstone** the last-known Panadan record. Preserve it as historical local data; mark provenance/freshness separately if reconciliation supports it. |
| Same ID reused, ambiguous joins, timestamp regressions, schema drift | Fail closed and alert; do not overwrite potentially unrelated data. |
| Source changes while VPN unavailable | Preserve local data, retain last committed cursors, report lag and resume safely. |

- No scheduled time-based removal of source records, payloads or history. **Seven-day retention is not the production policy.**
- Do not turn off deletion protections for legal/privacy erasure: exceptional authorized erasure and statutory retention restrictions must remain possible through an audited privileged process, **not** via ordinary source synchronization. Obtain organizational/legal authorization for the chosen retention policy before storing sensitive fields.
- Retain only the data the view actually exposes and for which Panadan has approved access: **all view columns** is not the same as every Odoo table or database.
- Keep Odoo access **strictly SELECT-only**. Do not create triggers, indexes, logical replication slots, tables or grants on Odoo through Panadan.

## Full-field fidelity and schema handling

1. Audit the live view's exact column names, PostgreSQL types and nullability. Its previously observed set was approximately 36 columns, with `write_date` subsequently verified; do **not** rely on that count as a permanent contract.
2. Create a reviewed, versioned **explicit full-column allowlist** and schema fingerprint. Never use unchecked runtime `SELECT *` to silently accept unexpected new columns. A source schema change should stop the job and require a deliberate review/migration before resuming.
3. Preserve raw values of customer name/phone, operator/team/stage metadata, full transcription, AI summary/recommendation/outcome, JSON/structured values, source identifiers and dates. Preserve null versus empty values and timestamp interpretation; do not round or summarize as part of raw ingestion.
4. Implement type-aware, lossless serialization for `date`, `timestamp`, `Decimal`, `jsonb`, arrays and any other observed source types. Test edge cases and field-by-field parity without logging customer contents.
5. The current ingestion serializer enforces a **2,000,000-byte per-record JSON limit**. For production transcripts, measure size distribution with privacy-safe aggregates and support oversized records through a reviewed strategy. **Never silently truncate or skip long transcripts.**
6. Maintain a restricted current-state projection for efficient local reporting plus immutable-by-default source revisions. The raw-revision store alone is not an authorization-safe dashboard interface.
7. Build indexes for local access patterns only on Panadan-owned PostgreSQL; changes to the upstream reporting view belong to its DBA.

## Reliable new and changed record detection

- Require proof that `id` is stable, unique across the complete reporting view and not reused (short 100-row samples are not proof).
- Require an observed before/after test that `write_date` advances for **all relevant changes**, including joined call/operator/team/stage data, plus confirmation that naive timestamps are UTC. If it does not cover these changes, the owner must supply a whole-view `sync_updated_at` or a bounded reconciliation design. Never label an incomplete timestamp poll as exact.
- Preserve the implemented **seed-updates-before-backfill** rule and use bounded keyset ID pages, timestamp+ID change pages, overlap windows and atomic checkpoints. A fresh install or resumption must not rewind/skip history.
- Use content digests to avoid duplicate revisions; distinguish legitimate timestamp-only changes from actual payload differences according to the reviewed fidelity policy.
- Do not infer deletes from absence in a page. If a complete periodic reconciliation is later added, it may mark `missing_at_source` without deleting the stored record.
- Use a single non-overlapping worker, bounded timeouts, retry/backoff, drift detection, alerting and resume-safe checkpoints. **Five minutes** is a candidate schedule, not a production promise until measured on the real view and VPN.

## Privacy, permissions and operational safety

- Full customer phone, name, transcript and AI free text are sensitive. Apply least-privilege, per-user/per-operator scope checks to **every** dashboard detail/list/aggregate, REST, MCP and WebMCP access path. A UI filter is not an authorization boundary.
- Keep raw credentials and payloads out of CLI output, logs, CI artifacts, tickets and PRs. Preserve separate Odoo read-only and Panadan ingest-writer roles.
- Audit read access to sensitive local fields; use an appropriately restricted local reporting role/view rather than broad raw-table access. Encryption/storage isolation and encrypted recovery material are required for an appropriate production threat model.
- The current local PG dump is **not** off-host recovery. Source Odoo backups cannot restore Panadan-only changes, account data, cursor state or revision history. The operator currently accepts the off-host recovery risk, but the risk must be documented; practice a restore before changing the dashboard read path.
- The server has an operator-owned untracked `prodctl.sh` and hardened Plane/Caddy/VPN networks. **Do not** replace it or invoke a bare Compose up/down. Keep the live Web/VPN/Plane stack unchanged until a reviewed, reversible deployment is approved.

## New release blocker — real Odoo view has duplicate ID (2026-11-04)

The operator ran a full-view, read-only count against `public.vw_danix_call_info_report`:

- `COUNT(*) = 95,495`
- `COUNT(id) = 95,495` (no NULL IDs)
- `COUNT(DISTINCT id) = 95,494`
- `COUNT(*) FILTER (WHERE write_date IS NULL) = 0`

**Exactly one ID has two occurrences.** This invalidates the global unique-ID assumption for both the eight-field pilot and new 37-field mirror. The current keyset `WHERE id > checkpoint` pagination can skip one duplicate at a page boundary, and per-ID ingestion may coalesce two distinct rows or miss changes. The timestamp+ID cursor also cannot uniquely distinguish rows with the same ID and timestamp.

**Block all production imports, even a 100-record pilot, until the duplicate's root cause is understood and a stable unique row identity or upstream view fix is approved and tested.** Do not silently `DISTINCT`/deduplicate, trust `call_id` without a full uniqueness/stability audit, overwrite both under the same `id`, or increase page size as a substitute.

Next read-only diagnostic: identify the duplicate ID internally without printing it, fetch only its two rows, and output *column names that differ* plus whether the rows are byte-for-byte equivalent at the Python field-value level. Never output any source ID, name, phone number, transcript or raw field values. If they differ, investigate JOIN/cardinality and request a unique, stable source key or view fix from the Odoo DBA. If they are identical, determine why the source emits duplicate rows before selecting a source-side canonicalization strategy. Prove the final uniqueness guarantee globally and regress pagination across a duplicate page boundary before approval.

## Read-only duplicate investigation result — 2026-11-04

The operator used a forward-only, read-only ID scan of the active view and found:

- **95,510 rows scanned** at that later point in time (the earlier aggregate saw 95,495; source is live and snapshots were taken at different times).
- **Exactly one duplicate ID** observed in that scan.
- Two rows returned for that ID; **the rows are not identical**.
- The two rows share the same `call_id` and, because only two fields differ, the same `write_date`.
- Only `possibility_of_sale_ai` and `tell_state_desc` differ between them.

This rules out treating the two occurrences as byte-identical duplicates. Neither `id` nor `call_id` nor `(write_date,id)` can uniquely represent these view rows. The likely explanation is view join multiplicity or multiple source detail rows, **not proven** without the view's owner examining join cardinality.

**Decision: keep all production sync disabled; do not silently choose the first row, MAX(), DISTINCT ON, or merge conflicting fields.** Ask the Odoo DBA/view owner to identify which relation creates this fan-out and either (a) correct the view to return exactly one authoritative row per call with deterministic, documented AI-field aggregation, or (b) expose a stable per-row unique key and an update marker that covers joined-row changes. Confirm that resolution never discards genuinely independent records. After the fix, rerun a global identity audit and verify incremental pagination under same-timestamp ties.

## Staged delivery / acceptance criteria

1. **Audit + test-first implementation:** Collect live metadata and safe size statistics; verify source IDs and update semantics; add full-field adapter, schema-drift guard, type preservation, >2MB handling and tests with synthetic sensitive data.
2. **Isolated integration:** In disposable PG18, test first insert, exact replay (zero revisions), changed old ID (one new revision), source-absent ID (retained), timestamp ties, cursor restart, large transcripts, malformed source types and denied unauthenticated/unauthorized sensitive reads.
3. **Explicitly approved 100-record full-field pilot:** Read-only source, restricted writer target, captured source schema version, verified local restore plan. Seed updates before backfill; import at most 100 rows; verify field-level parity without printing raw fields. No timer, no UI/API/MCP cutover.
4. **Measured backfill:** Import the complete view in bounded pages with progress and checkpoints; document throughput, VPN load, row size/DB growth and failures. Validate sampled historical updates and source-missing retention.
5. **Controlled continuous sync:** Enable a supervised, serialized incremental job at a validated cadence; monitor lag, schema drift, source errors, record/revision counts, disk and backup/restore health.
6. **Shadow-read parity and secure cutover:** Compare local reporting with Odoo without user-visible changes; verify all user scopes and query features; cut over one surface at a time with documented rollback. Keep Odoo as a read-only fallback until proven safe.

**Release gate:** No production source enablement, cursor seeding, full-field copy, automatic scheduling, auth migration or dashboard cutover from merging this document alone. Obtain explicit approvals for source semantics, full-field sensitive-data storage, retention/erasure governance, approved rollout/rollback and production runtime changes. Record any consciously accepted backup risk.

## Implemented on draft PR #97 (not deployed)

- New isolated `server/odoo_full_mirror_adapter.py` explicitly describes **all 37 observed view fields** and performs strict schema/order/type checks before any full-field read.
- It supports bounded keyset ID pages, `(write_date,id)` update pages, raw call metadata including sensitive names, phones and transcripts, JSONB, date, timestamp and float types. Unrecognized types fail closed; it **does not truncate** transcripts or propagate source disappearance as deletion.
- New `tests/test_odoo_full_mirror_adapter.py` uses synthetic data only. The full repository CI passed for the draft's adapter and pilot test commit, and the new disposable-PG18 integration test passed, but live-data parity, full backfill, sensitive access controls and recovery rehearsal are still required.
- **Crucially, this remains an isolated, disabled-by-default draft pilot**, not a production-ready worker. A separate operator-only CLI has been added, but no existing live Web, scheduler, database source, read path or restricted eight-field pilot is wired to it.
- Production readiness still requires audited large-payload handling if needed (existing `server/platform_ingest.py` limit: 2,000,000 JSON bytes/record), broader source-ID/update coverage proof, disposable-PG18 parity/recovery tests, authorization, and approved deployment.

## Verified live size samples — 2026-11-04

The operator queried the authorized production view in **read-only** mode and reported:

| Source ID sample | Rows | Largest transcript | Largest JSONB full record | Over 2,000,000 bytes |
| --- | ---: | ---: | ---: | ---: |
| Lowest IDs (ASC) | 100 | 0 bytes | 4,523 bytes | 0 |
| Highest IDs (DESC) | 100 | 25,300 bytes | 30,748 bytes | 0 |
| Offset 1,000 (ASC) | 100 | 0 bytes | 4,196 bytes | 0 |
| Offset 5,000 (ASC) | 100 | 0 bytes | 4,166 bytes | 0 |
| Offset 10,000 (ASC) | 100 | 0 bytes | 4,063 bytes | 0 |

A total of **500 sample rows** showed no over-limit records. This measures PostgreSQL `octet_length(to_jsonb(view_row)::text)`, **not** exactly the Python serialized payload; it is a reassuring size estimate, not a whole-dataset maximum. The current **2 MB writer cap remains unchanged**, and any oversized record must fail visibly without truncation until a reviewed large-payload implementation exists.

## Isolated full-field pilot code (draft only)

- `server/odoo_full_mirror_pilot.py` provides manually invoked `status`, `preview`, `verify`, `seed`, `backfill` and `updates` commands with a separate `odoo_calls_full_v1` source key, so the full-field cursors never mix with the existing `odoo_calls` eight-field pilot.
- No scheduler, no auto-registration, no automatic source activation, no Odoo write and no deletion operation. Runtime uses the restricted `panadan_ingest_writer` target via the already validated private DSN. `seed` still runs before backfill and all writes go through the existing atomic checkpoint/revision store.
- Full-field pilot writes require all four explicit flags `--ack-source-contract --ack-retention --ack-copy --ack-sensitive-data`, an **owner-registered/enabled** dedicated source, one page of at most 100 records, and secure source/data-owner approvals. These flags do **not** override the independent production deployment/recovery approvals.
- The CLI currently fails closed for a JSON payload exceeding 2 MB; it does not silently drop or truncate a long transcript.
- Synthetic tests cover fail-closed approvals, bounded previews, source-disabled refusal and upsert-only behavior. **CI quality, Docker builds and platform-integration passed at commit `8150dd2`**, including a new disposable-PG18 synthetic test for full-field insert/update/replay and retention of an upstream-missing record. The live source and production owned PostgreSQL have not been used for that integration test.
- The full-field pilot module is **not part of the live Web runtime deployment**, and the dedicated source has not been registered or enabled on production. Do not run its write commands on the VPS now.

## Existing implementation gaps (reviewed 2026-11-04)

- `server/odoo_sync_adapter.py` only selects eight restricted fields plus one update marker; it excludes names, phones, transcripts and most reporting metadata.
- `server/platform_ingest.py` currently rejects JSON payloads larger than 2MB; unlimited transcript support has **not** been demonstrated.
- `server/odoo_sync_pilot.py` implements one-shot bounded, guarded pilot commands, not an active scheduler or full production mirror.
- The production Web DSN mount/scheduler is **not** integrated into the reviewed production release controller. A temporary restricted container has successfully performed local read-only `status`; no source has been enabled.
- `panadan_ingest.sources` already has `odoo_calls` registered but disabled. At the last verified live check: zero source records, revisions, committed pages, or cursors.
- The live dashboard/API/MCP still read the source view over VPN, and production account authorization still uses SQLite. Neither read-path nor auth cutover is part of the mirror preparation.


## Draft alternative with restricted-view access — snapshot reconciliation (2026-11-04)

**Status: code + synthetic tests only; not production approved, deployed, or exercised with sensitive data.** The operator has only the SELECT privilege on the 37-field reporting view. Inspection established that `possibility_of_sale_ai` and `tell_state_desc` originate from a joined analysis table; the exposed `write_date` comes only from the parent call table. A joined-record edit can therefore remain invisible to the parent timestamp. The view also emits different rows under one call ID.

Rather than claim the current `(write_date,id)` change cursor is reliable, the draft standalone manual full-mirror CLI now offers **`snapshot`**, which performs one **bounded, forward-only ID page** per invocation. The old `seed`, `backfill` and `updates` commands are no longer accepted by this full-mirror CLI. The legacy eight-field adapter is unchanged and must not be used as a reliable production change feed.

- Read only the reviewed 37 columns from `public.vw_danix_call_info_report`. Query `id > last_id ORDER BY id LIMIT (N+1)` with one look-ahead row. If the look-ahead row shares the final page ID, defer the **entire** ID group to the next page instead of checkpointing an incomplete call. A group larger than the per-page bound fails closed.
- Store one raw event per **call ID**, with an explicit `source_schema: odoo_view_37_v1`, `id` and `source_rows` array containing **every full 37-field view row**, including duplicate identical rows. Canonically sort variant payloads to make their digest independent of unstable JOIN tie ordering. No guessed authoritative analysis or transcription is chosen.
- Check stable anchors `(call_id, create_date)` across grouped rows and before overwriting an existing Panadan record. If an existing ID changes these anchors or the stored payload uses a conflicting older shape, refuse the entire page. This is a conservative guard, not proof that Odoo will never reuse an ID.
- Commit events and the `view_reconciliation_v1` cursor atomically in the existing revision store, with a distinct stream checkpoint. On the end of a pass, advance `pass` and reset `last_id=0`. A subsequent **manual** invocation begins the next pass; unchanged groups create no new revision. A changed joined field is detected by the complete payload digest even if the exposed `write_date` did not advance.
- Never emit tombstones based on absence. Removed view rows remain in Panadan as last-known historical data; automatic freshness or missing-state classification is **not** implemented.
- Keep all four write acknowledgments, the owner-enabled source requirement, the private restricted writer DSN, one page per invocation, and the 2,000,000-byte per-event ceiling. The envelope and duplicates consume additional bytes. Any oversized group fails closed and requires separate review.
- Do **not** treat these calls as globally consistent database snapshots. Every page is a separate SELECT and the source can change between pages. Under ongoing updates, results can be temporarily inconsistent and intermediate revisions are **not** guaranteed; repeat full scans converge only when the source eventually stabilizes. A complete scan of ~95k rows is not proven fast or low-impact under the source query timeout. No scheduler, automatic catch-up, dashboard cutover, or production deployment is introduced.

### Manual staging-only interface (after isolated integration tests)

```bash
python -m server.odoo_full_mirror_pilot status
python -m server.odoo_full_mirror_pilot preview --batch-size 100
python -m server.odoo_full_mirror_pilot verify --batch-size 100
# snapshot performs a target WRITE and is forbidden on production until
# separate source/retention/privacy/deployment approvals, verified backup,
# source ID stability assessment and measured query performance.
python -m server.odoo_full_mirror_pilot snapshot --batch-size 100 \
  --ack-source-contract --ack-retention --ack-copy --ack-sensitive-data
```

**Open gates:** Run disposable-PG18 integration tests, ensure per-user RBAC and sensitive storage/recovery, verify stable call IDs over time, assess source load and full-pass rate, handle exceptionally large fan-out and payloads, add robust monitoring of failed/unfinished passes, and obtain explicit authorization for production data copying. View-only access limits certainty: it cannot reveal an upstream authoritative analysis, intermediate edits between passes, or deletions that should trigger erasure.

**No VPS commands or production writes are authorized by this section.**


## Safe facts from ambiguous source rows (draft)

The full mirror's `source_rows` envelope is **not** equivalent to the legacy flat eight-field format. The v1 platform facts processor now recognizes the explicit `source_schema=odoo_view_37_v1` envelope and derives only the existing allowlisted **non-sensitive** fields for which every row variant agrees: `tellside`, `tellstate`, `aicallinfostate`, `voice_length`, and `possibility_of_sale_ai`. If two analyses produce conflicting scores, the safe `ai_sales_estimate` fact is **omitted**, not selected arbitrarily or averaged. Private names, phones, summaries, free-text AI descriptions and transcripts remain restricted to raw revisions. Invalid mirror envelopes fail closed. A synthetic PG18 permission test verifies that `panadan_report_reader` cannot directly SELECT the raw revision payload or obtain contradictory scores through `safe_call_facts_v1`.

This restricted v1 facts view is **not** a complete 37-field authorized local dashboard replacement. Additional operator-scoped sensitive projections, policy checks, traceability, and audit logging are required before any dashboard/API/MCP cutover. No source scheduler, owner enablement, or production import was added.


## Supervised multi-page reconciliation runner (draft)

The full mirror CLI now has `snapshot-run` for operator-supervised, **bounded** forward reconciliation against the existing read-only view. It processes up to **10 pages of at most 100 source view rows each** per invocation, stopping early when a scan pass completes. Each page is ingested with the same atomic source digest + cursor transaction used by `snapshot`. If the source times out or a later page fails, earlier pages remain committed and the next invocation resumes at the last good cursor; no delete or automatic scheduler is involved. Both commands require all four existing copy/retention/sensitive-data approvals and an explicitly owner-enabled target source.

**Testing:** A synthetic PG18 test exercises duplicate rows crossing page boundaries within a `snapshot-run`, including correct per-call digest revision behavior. Further integration/security/performance verification is required before real-record import.

```bash
# Example for an ALREADY APPROVED, isolated target ONLY, never default VPS:
# python -m server.odoo_full_mirror_pilot snapshot-run --batch-size 100 \
#   --max-pages 10 --ack-source-contract --ack-retention \
#   --ack-copy --ack-sensitive-data
```

**This does not solve:** an all-37-field scoped dashboard/API/MCP read path, a validated retention and erasure policy, full-view consistency guarantees (the source has no change feed), any role-appropriate staging DSN, source-side data-copy permission, or a verified production backup and rollback. The command must NOT be run on the live VPS until those gates are independently approved. The branch is still draft and no production release is approved.


## Staging-only operator-scoped local reporting (draft)

A new additive, **manually applied** Panadan-owned PostgreSQL migration,
`database/permissions/003_full_mirror_safe_reporting.sql`, creates
`panadan_ingest.safe_mirror_call_listing_v1`. It must be applied **after**
`001_multisource_foundation.sql` and `002_platform_runtime_roles.sql`
by a reviewed *Panadan-owning* database administrator, never on Odoo.
No production migration or deployment has been performed.

The view exposes one **sanitized current-state summary per call** only when
*all* joined variants agree on source ID, call date and numeric operator ID.
It omits any source record whose operator is missing or ambiguous and returns
NULL for conflicting AI score/state/direction/duration. It deliberately
excludes customer name, phone, transcription, summaries, raw payload and
arbitrary JSON. Only `panadan_report_reader` can SELECT this view; the
ingest writer and PUBLIC cannot. The existing safe facts view is unaffected.

`server/odoo_local_reporting.py` adds bounded list, by-ID lookup and count
using **required, explicit, trusted numeric operator IDs**. Empty scopes
deny access; direct ID and aggregate queries use the same restriction; the
connection must be the dedicated PG18 `panadan_report_reader` login.
The caller MUST derive those IDs from an authenticated server-side
authorization mapping, **never** from request filter parameters. Until the
organization confirms stable source operator IDs and implements/enforces
this mapping across dashboard, API, remote MCP and WebMCP, the module must
remain unconnected to live endpoints. A matching PG18 integration test proves
two disjoint operator scopes cannot cross-read, and ambiguous-operator
records cannot be read through either scope.

**This is not yet a full 37-column dashboard replacement.** Sensitive
data must go through a separately reviewed administrative/sensitive scope
and audit mechanism; never grant the normal reporting role raw revision
access merely to achieve full field parity. Access policy, retention and
erasure governance, real customer-data copy approval, source freshness and
restored offsite recovery remain independent release gates.

The `status` command additionally reports **counts only**: committed pages,
last commit age, pending/failed processing jobs and completed scan passes.
It does not reveal source IDs, names or payloads. This is an operator
diagnostic, not an automatic alerting or scheduling system.


## Verified local Panadan account -> Odoo operator grants (draft)

**Implemented, not yet exposed as a UI/API and not enabled for live cutover.**
Production Panadan currently authenticates browser sessions and service
tokens in SQLite. The source Odoo view exposes a candidate stable **numeric
operator ID** (`vw_danix_base_info_users`), but its authoritative meaning
still requires **source-owner confirmation**. Display-name directory filters
must **never** be interpreted as an access grant.

The local SQLite `Store` adds a `user_operator_scopes` table:
- **Default deny for everyone, even administrators**: empty grants return
  no local calls; there is no implicit all-operators wildcard.
- A new grant requires an **active administrator**, an **active target with
  calls:read**, a strictly positive bounded **numeric source operator ID**
  and an explicit `source_identity_verified=True` administrative
  assertion. This assertion records a **human process**, not independent
  proof in software. An organization/source owner must validate IDs before
  granting any real users. No HTTP handler exists to self-assign scopes.
- Revocation applies on the very next request. Any `update_user` role,
  capability, or active-status change deletes all previously approved
  numeric IDs and requires new review. Grant, explicit revoke and reset are
  recorded in an **append-only local audit table** containing only actor
  ID, account ID, operator ID, action and time.
- No automatic matching by username, display name, team, destination,
  historical login, OAuth subject or AI inference.

`server/odoo_local_reporting.py` adds session-bound and token-bound
listing, count and by-ID lookup. They **authenticate an existing valid,
active browser session** or verify a service token's *scope + calls:read
capability + active owner* before loading approved IDs. They then delegate
to the exact same restricted PG18 reader/view; caller filters are not
authorization. Both list and count are restricted; by-ID direct lookup
cannot cross operator boundaries. A missing/unverified user grants no rows,
and revoked/expired credentials fail closed. Only the default SQLite auth
backend currently implements the new grant persistence; isolated PG auth
backend adaptation requires a separate review before any auth migration.

Synthetic unit + disposable PG18 integration tests cover default denial,
non-admin grant rejection, invalid IDs, role-change revocation, audit trail,
two separate browser sessions, API tokens, cross-operator by-ID denial,
revoked tokens/scopes and no raw customer text in the returned projection.

**Still not authorized to deploy or cut over:** source-owner validation of
operator IDs, a reviewed administrative approval workflow, consistent
enforcement for *all* current dashboard/API/remote-MCP/WebMCP surfaces,
audited sensitive/full-field detail reader, privacy/retention and verified
staging real-copy/backups. These wrappers are library code, **not yet wired
to any public HTTP endpoint**. Never copy customer data or merge on the
strength of test fixtures alone.


## Separately privileged, audited full-field detail (draft)

The draft branch now has **library-only** sensitive detail access, separated
from the sanitized operator listing. **Not deployed, not enabled on any
dashboard/API/MCP/WebMCP endpoint, no live Odoo data imported.**

- `database/permissions/004_full_mirror_sensitive_detail.sql` is an
  owner-run, additive PG18 migration requiring the existing 001/002/003
  migrations and a deliberately provisioned unprivileged login role named
  `panadan_mirror_sensitive_reader`. It grants that role SELECT only on
  `sensitive_mirror_call_detail_v1`. The original
  `panadan_report_reader`, ingestion writer, and PUBLIC cannot SELECT the
  sensitive view. The detail role has no direct raw revisions, source
  records, normal listing, CREATE, or database administration privileges.
- The view returns only the **current full-mirror revision**, only for calls
  passing the existing unambiguous operator/ID/date guard in
  `safe_mirror_call_listing_v1`. It preserves *all* 37-field joined
  variants, including conflicting AI analyses; it never chooses one.
- `server/odoo_sensitive_detail.py` **requires** a dedicated PG18 reader
  connection, an *active* SQLite Panadan browser session **or** an
  `api:sensitive` token whose owner is active, all three capabilities
  (`calls:read`, `calls:sensitive`,
  `calls:transcript:read`), and an explicit previously verified numeric
  operator scope. It derives scopes exclusively from the trusted SQLite
  account store and performs a bounded, parameterized current-record lookup.
  No external operator ID list is accepted.
- `Store.authorize_sensitive_mirror_attempt` rechecks the active user's
  capabilities and source operator grants and **commits a separate SQLite
  audit row before** any PG SELECT. The row contains the local user ID,
  source call ID, surface and timestamp; no transcript, phone, name or token.
  If the audit fails, no sensitive read occurs. An authorized read attempt
  is logged even if the call does not exist or is assigned to another
  operator. This is an **attempt log**, not a proven response/delivery log.
- To fail closed on malformed source data, the library checks the returned
  identity/operator/count, exactly **37 recognized field names per row**,
  correct variant IDs, operator consistency, at most 100 variants, and
  a 2 MB detail response bound. Sensitive fields are returned only by this
  explicit sensitive path; the normal reporting view stays sanitized.
- MCP full-field detail is **not supported** yet; neither are public HTTP
  routes, a DSN/secret manager for the new role, a reviewed administrator
  grant UX, or PostgreSQL-auth-backend equivalent auditing.

**Important boundary:** a DB login role authorized to query a SQL VIEW can
query the entire view if its credentials are compromised; the per-user
source-operator authorization is enforced by the library, not by a
PostgreSQL per-user RLS policy. Secure distribution, storage and rotation
of this dedicated credential, audit retention/protection and trust-boundary
review are mandatory before deploying any sensitive read surface. Do not
distribute the role password to ordinary users, clients or MCP connections.

Synthetic PG18 role/RBAC tests include two distinct principals and operators,
37-field parity with two conflicting joined analyses, unauthorized cross-ID
reads, normal reader/writer/raw-table denial, revoked source grants,
invalid sessions, a read-only API token, and audit-storage failure.
The source-owner/operator-ID confirmation, copy/retention/legal approvals,
staging restore/backup and a reviewed complete product-surface cutover are
still outstanding. **Never run the migration against Odoo or deploy the
sensitive view to production simply because CI passes.**


## Isolated local-mirror API staging route (draft)

**Added an isolated REST API prototype, not deployed to the live Web service.**
`server/odoo_staging_api.py` exposes the new, non-legacy paths:
`/api/v1/local-mirror/calls`, `/api/v1/local-mirror/count`,
`/api/v1/local-mirror/calls/{call_id}`, and
`/api/v1/local-mirror/sensitive/calls/{call_id}` within a separately
constructed staging application. No existing `/api/v1/calls`, dashboard,
`/mcp` or WebMCP handler is modified.

Normal endpoints verify the current `api:read` token's `calls:read`
capability and derive operator IDs exclusively from the **active token
owner's approved numeric grants**. Sensitive endpoints require a valid
`api:sensitive` token and all `calls:read`, `calls:sensitive` and
`calls:transcript:read` capabilities, then commit a pre-read audit record
before a dedicated sensitive PG18 SELECT. The HTTP layer does NOT accept
operator ID lists or user IDs as filter parameters. An absent or wrong-scope
token is rejected before opening a PostgreSQL reader connection; a call
belonging to a different operator returns 404, and malformed records fail
closed. Both classes of successful response carry `Cache-Control: no-store`.
All backend failures return generic errors with no raw SQL/DSN/customer data.

`server/odoo_staging_app.py` supplies an **optional standalone staging
entrypoint**; it has no app object in the default import path. To construct
an app it requires both explicit `PANADAN_LOCAL_MIRROR_STAGING_ENABLE=YES`
and `PANADAN_LOCAL_MIRROR_STAGING_ISOLATED=YES`, a *separate existing
disposable* SQLite store under `/tmp/panadan-mirror-staging-*/...sqlite`,
absence of `PANADAN_PUBLIC_ORIGIN`, and two distinct private DSN files
for `panadan_report_reader` and
`panadan_mirror_sensitive_reader`. DSNs must point only at loopback
`127.0.0.1` **panadan_ci PG18** (never source Odoo or production Panadan);
file permissions must exclude group/other access and symlinks are refused.
A middleware rejects non-loopback TCP clients even if someone mistakenly
starts an ASGI server bound to all interfaces. TLS/public reverse-proxy
deployment is not supported; **never reverse-proxy this app publicly or
treat a localhost source IP from an on-host proxy as public authentication**.

Synthetic test coverage includes genuine FastAPI TestClient requests through
the local SQLite authority into disposable PG18, authorized and unauthorized
normal/sensitive service tokens, two disjoint operator scopes, ambiguous
analysis rows, 37-field detail, audits, revocations, malformed authentication,
wrong source credentials, public-origin rejection, and remote-client rejection.

Do **not** add this isolated router to `server.main` or the production
`dan.panafor.com` ingress as part of PR #97. A complete end-user
dashboard/API/MCP cutover still requires an independently reviewed source
operator mapping, migration/backup, data-copy/retention authorization,
freshness policy, and production-grade credential isolation. The main
production API still reads Odoo directly.


## Bounded supervised sync ticks and full-range parity (draft)

Added `server/odoo_mirror_scheduler.py` as an **operator-invoked**,
bounded reconciliation and freshness-policy entrypoint. It is **not**
started by importing Panadan Web, and contains no active service, cron,
systemd unit or live Docker schedule. An authorized operator may arrange
periodic external invocation **only after** the data owner has approved
copying personal and transcript data into Panadan-owned PostgreSQL, retention
and deletion rules have been approved, the Odoo read-only contract is
confirmed, and the target source `odoo_calls_full_v1` is deliberately
registered/enabled by a separate admin.

A single `tick` checks all **four explicit approval flags**, acquires
the existing exclusive pilot lock, verifies source enablement, processes
only the full-mirror normalization queue (not unrelated sources), and
continues the current ID-keyset scan in at most **10 pages of 100 source
rows**. The default tick has an additional **120-second wall-clock budget**,
a **1,200-job processing budget**, a **2,500-job backpressure threshold**,
and a **one-hour minimum gap** before starting a fresh completed scan.
The operator can lower those budgets but cannot exceed hard caps. No
delete/tombstone is inferred from source-view absence, no source Odoo write
is attempted, and no customer fields or IDs are logged. Per-page
revision/digest/checkpoint writes remain atomic. A failed later page leaves
earlier commits resumable; a processing failure returns a nonzero exit
rather than continuing silently.

The bounded `health` command reads only Panadan-owned aggregate status
and returns nonzero (exit 3) for disabled, never-started, processing-failed
or stale states. The signal uses **time since the most recently committed
page**, which is *not equivalent* to guaranteed Odoo real-time freshness
or proof of a completed scan. Alerting/notification must be configured by
a reviewed external supervisor; no network notification action is hidden
in the runner.

After all deployment approvals and isolated network/credential preflight
are explicitly satisfied, the operator-facing syntax is:

```bash
# APPROVED ISOLATED ENVIRONMENT ONLY (not a current VPS instruction).
python -m server.odoo_mirror_scheduler tick \
  --ack-source-contract --ack-retention --ack-copy --ack-sensitive-data \
  --batch-size 100 --max-pages 10 --max-process-jobs 1200 \
  --max-tick-seconds 120 --min-pass-gap-seconds 3600

# Diagnostic only. Nonzero means alert/hold production cutover.
python -m server.odoo_mirror_scheduler health --max-stale-seconds 86400
```

**Important:** `tick` is a single bounded invocation. It is not a
self-executing daemon; do not create a production recurring timer without
the explicit operator/data-owner approvals, secured execution identity
and monitored nonzero exits. Because the source is a joined reporting
view without reliable CDC, repeated full scans can discover later source
changes but **cannot capture every intermediate history version**. The
current scanner never treats missing source rows as deletion.

Also added `verify-run` to
`server.odoo_full_mirror_pilot`: a **read-only** bounded parity walk,
comparing the current canonical digest of each complete duplicate-safe
source group to local `source_records` without modifying either source
or target. It returns aggregate matching/missing/different counts and
a resumable numeric `next_after_id`. Repeat from that cursor until
`complete=True`; no personal text, transcripts or phones are printed.
This is not a single consistent transaction spanning all source pages.
The numeric cursor is operational scan metadata, not a customer field.

```bash
# For an already-approved read-only source + owned PG reader connection.
python -m server.odoo_full_mirror_pilot verify-run \
  --after-id 0 --batch-size 100 --max-pages 10
# Continue with the returned next_after_id until complete=True.
```

A full scan can be compared only after sufficient reconciliation passes;
concurrent source changes may cause transient differences. Verify and
re-check bounded ranges rather than deleting records based on one pass.
Before enabling the production schedule: prove a complete *converged*
scan, check retained missing-record behavior, test recovery, verify all
operator assignments and sensitive audit rules, and record the
data owner's consent and retention/erasure decision. No activation or
production copy has happened through this PR.


## Operator grant admin page and safe staging MCP (draft)

An **explicitly gated** administrative page is now available in source code
at `/dashboard/operator-scopes` only when
`PANADAN_MIRROR_SCOPE_ADMIN_ENABLE=YES` and Panadan uses the current
SQLite authentication authority. Default: hidden/404, including if a
PostgreSQL-staging auth store is active. The page requires an authenticated
Panadan administrator and correct CSRF token to create/revoke a manually
verified numeric Odoo operator mapping; a required checkbox records the
administrator's assertion that the ID and user entitlement were checked
independently with the Odoo owner. All changes use the server-side Store's
existing grant rules, revoke immediately on the next read, and write
security audit metadata. Never interpret ticking the checkbox alone as
proof of an actual authorization agreement. A scoped listing of approved
IDs is available only to active admins. No Odoo write or copy is triggered.

The isolated `server/odoo_staging_app.py` additionally mounts
`/mcp/` behind a separate *loopback-only* transport with exact localhost
Host/Origin protection and `mcp:read` bearer-token authentication. The
three MCP tools in `server/odoo_mirror_mcp.py` expose only the
operator-scoped, sanitized PG18 call list, per-ID summary and aggregate
count. Each tool call revalidates token scope, active owner and effective
operator permissions before any PG read. There is NO arbitrary SQL,
sensitive customer detail, transcript reader, source Odoo query or automatic
token creation on this staging MCP surface. The public production
`/mcp` tools remain unchanged and still read their existing source.

Manual staging tests confirm the read-only API is independent. Synthetic
MCP JSON-RPC transport tests exercise initialization, list/call,
revocation, invalid token denial and no fallback to live Odoo on a missing
local DB. Do not proxy this loopback-only staging MCP publicly: a proxy
can appear as a localhost peer to the app. This is not the approved
production OAuth MCP cutover.

**Bottom line:** staged API and safe MCP tools are implemented, but full
product cutover, public ingress and customer copy are still gated on
validated Odoo source identity, legal/retention approvals and a reviewed
production authorization/backup/restore plan. See
`docs/ODOO_MIRROR_RELEASE_GATES.md` for the complete checklist.
