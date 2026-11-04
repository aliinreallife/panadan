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
- New `tests/test_odoo_full_mirror_adapter.py` uses synthetic data only. The full repository CI passed for the draft's adapter and pilot test commit, but live-data and disposable-PG18 end-to-end validation are still required.
- **Crucially, this remains an isolated, disabled-by-default draft pilot**, not a production-ready worker. A separate operator-only CLI has been added, but no existing live Web, scheduler, database source, read path or restricted eight-field pilot is wired to it.
- Production readiness still requires audited large-payload handling if needed (existing `server/platform_ingest.py` limit: 2,000,000 JSON bytes/record), broader source-ID/update coverage proof, disposable-PG18 parity/recovery tests, authorization, and approved deployment.

## Verified live size samples — 2026-11-04

The operator queried the authorized production view in **read-only** mode and reported:

| Source ID sample | Rows | Largest transcript | Largest JSONB full record | Over 2,000,000 bytes |
| --- | ---: | ---: | ---: | ---: |
| Lowest IDs (ASC) | 100 | 0 bytes | 4,523 bytes | 0 |
| Highest IDs (DESC) | 100 | 25,300 bytes | 30,748 bytes | 0 |

This measures PostgreSQL `octet_length(to_jsonb(view_row)::text)`, **not** exactly the Python serialized payload; it is a reassuring size estimate, not a whole-dataset maximum. The current **2 MB writer cap remains unchanged**, and any oversized record must fail visibly without truncation until a reviewed large-payload implementation exists.

## Isolated full-field pilot code (draft only)

- `server/odoo_full_mirror_pilot.py` provides manually invoked `status`, `preview`, `verify`, `seed`, `backfill` and `updates` commands with a separate `odoo_calls_full_v1` source key, so the full-field cursors never mix with the existing `odoo_calls` eight-field pilot.
- No scheduler, no auto-registration, no automatic source activation, no Odoo write and no deletion operation. Runtime uses the restricted `panadan_ingest_writer` target via the already validated private DSN. `seed` still runs before backfill and all writes go through the existing atomic checkpoint/revision store.
- Full-field pilot writes require all four explicit flags `--ack-source-contract --ack-retention --ack-copy --ack-sensitive-data`, an **owner-registered/enabled** dedicated source, one page of at most 100 records, and secure source/data-owner approvals. These flags do **not** override the independent production deployment/recovery approvals.
- The CLI currently fails closed for a JSON payload exceeding 2 MB; it does not silently drop or truncate a long transcript.
- Synthetic tests cover fail-closed approvals, bounded previews, source-disabled refusal and upsert-only behavior. Actual CI and disposable-PG18 integration results must be checked before any production invocation.
- The full-field pilot module is **not part of the live Web runtime deployment**, and the dedicated source has not been registered or enabled on production. Do not run its write commands on the VPS now.

## Existing implementation gaps (reviewed 2026-11-04)

- `server/odoo_sync_adapter.py` only selects eight restricted fields plus one update marker; it excludes names, phones, transcripts and most reporting metadata.
- `server/platform_ingest.py` currently rejects JSON payloads larger than 2MB; unlimited transcript support has **not** been demonstrated.
- `server/odoo_sync_pilot.py` implements one-shot bounded, guarded pilot commands, not an active scheduler or full production mirror.
- The production Web DSN mount/scheduler is **not** integrated into the reviewed production release controller. A temporary restricted container has successfully performed local read-only `status`; no source has been enabled.
- `panadan_ingest.sources` already has `odoo_calls` registered but disabled. At the last verified live check: zero source records, revisions, committed pages, or cursors.
- The live dashboard/API/MCP still read the source view over VPN, and production account authorization still uses SQLite. Neither read-path nor auth cutover is part of the mirror preparation.
