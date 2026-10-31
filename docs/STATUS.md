# Panadan v0.6 status

## Delivered and merged to main

- [x] FastAPI reporting dashboard, REST API and MCP Streamable HTTP server
- [x] uv-managed Python 3.12 with committed `uv.lock`
- [x] WSL-native development with isolated Docker VPN and loopback-only PostgreSQL relay
- [x] Private GitHub repository and GitHub Actions CI
- [x] Prebuilt GHCR VPN/web images (confirm package visibility independently)
- [x] Vazirmatn Persian RTL dashboard and Doran Jalali date/time controls
- [x] Admin-managed users, capability-based read access, revocable API/MCP tokens
- [x] Explicit PostgreSQL read-only reporting transactions
- [x] Panadan formatted transcripts and unchanged raw source view
- [x] CI tests and Docker image builds pass after v0.4 merge
- [x] Installation instructions use `$HOME`, not a developer-specific directory
- [x] CI checks executable script modes

## Still to verify or implement

- [ ] Real WSL browser/UX smoke-test of v0.4 with live VPN and user permissions
- [ ] Confirm actual GHCR package visibility is Private for both web and vpn packages
- [ ] Full production image deployment on a target host, backup/restore validation
- [ ] OAuth 2.1 authorization-code/PKCE and remote MCP interoperability
- [ ] Public domain, TLS, proxy/Origin/Host security and rate limiting before public exposure
- [ ] PostgreSQL administrator revokes unnecessary CREATE privilege for reporting user
- [ ] Clarify `SoldOut` and `deal_value` semantics with the source owner; `voice_length` was confirmed as seconds on 2026-10-31

The dashboard/API/MCP must remain read-only against the source reporting database. Only Panadan's separate local authentication store may write user and token records.

## v0.5 dashboard improvements

- [x] Call-type labels and source-state translations retain original raw values
- [x] Type filter uses parameterized reporting queries and values discovered by a read-only endpoint
- [x] Call detail opens with summary/analysis, keeps metadata separate and makes the long transcript last and collapsed by default
- [x] Original transcript remains available under the Raw tab once expanded
- [x] Admin-only REST API guide added to sidebar with authenticated Swagger/OpenAPI links and curl examples
- [x] Removed backend vendor branding from user-facing dashboard status text
- [ ] Browser visual QA of long Persian transcripts and the mobile layout in the live environment

## v0.6 OAuth integration

- [x] Opt-in MCP resource-server mode with RFC 9728 discovery and WWW-Authenticate challenges
- [x] Strict external RS256 access-JWT checks for signature, issuer, audience, expiry, issuance and scope
- [x] Provider subject → Panadan account binding managed by admin; roles checked on every request
- [x] Manual MCP tokens denied in OAuth mode; REST API token behavior unchanged
- [x] Account role changes revoke OAuth bindings
- [x] Offline security tests and a provider setup guide without real secrets
- [ ] Choose/configure a production identity provider supporting OAuth 2.1 PKCE and CIMD/DCR/static client
- [ ] Expose secure HTTPS identity and resource endpoints/tunnel with Host/Origin hardening
- [ ] Verify real ChatGPT OAuth consent, code exchange, callback, refresh and MCP tool discovery
- [ ] Review production auditing, rate limits, backups and key rotation before public access

## Reporting-database read-only audit

- [x] Source reporting methods issue only parameterized SELECT queries within explicit READ ONLY transactions.
- [x] Dashboard and REST reporting endpoints expose GET, and MCP exposes only the four reviewed read-only tools.
- [x] Add a non-mutating local permissions checker: `./panadan.sh audit-db`.
- [x] Add automated regression tests for read-only queries, HTTP route methods, MCP tools and simulated effective write privileges.
- [x] 2026-10-31: inspected the live `report_user` grants via read-only audit; effective `CREATE` on schema `public` was traced to a `PUBLIC` grant. **Not PASS** for strict least-privilege.
- [ ] DBA resolves unnecessary effective CREATE/write grants and verifies the account independently, preferably with a dedicated least-privilege reader.

## Experimental WebMCP browser tools

- [x] Browser-native `document.modelContext.registerTool()` feature detection and abort-on-navigation lifecycle
- [x] Read-only, same-origin, session-authenticated metrics, filtered calls and metadata-only single call overview
- [x] Permission-scoped tools with capped pages and input validation; no customer identifiers/transcripts
- [x] Dedicated `/dashboard/overview/{id}` returns nonsensitive data **without querying** sensitive columns
- [x] Node mock WebMCP tests and Python session/permission tests
- [ ] Manual smoke test with supported Chrome WebMCP build and a browser agent
- [ ] Separate permission-scoped transcript tool with explicit AI disclosure and audit logging

## Activity analytics and transcript UX (v0.7 draft)

- [x] Admin-only Persian RTL Activity dashboard with charts, filters, recent events and human-readable tool labels
- [x] Log successful and unsuccessful sign-in attempts and sign-outs
- [x] Log dashboard/API request metadata and allowlisted MCP tool names, never payloads or access tokens
- [x] 90-day activity log retention in local SQLite; filter by user, API/MCP channel and errors
- [x] Separate AI transcript capability and read-only chunk retrieval for long conversations
- [x] No arbitrary request-count or overall transcript length cap; each chunk remains bounded
- [x] Best-effort identifier masking and independent transcript access audit
- [x] Human-friendly Persian role and permission badges in user management
- [ ] Confirm real MCP SDK request context propagation with an authenticated live tool call
- [ ] Review browser responsiveness and Jalali date formatting with realistic data
- [ ] Configure full OAuth authorization-code/PKCE consent and external HTTPS provider (separate future milestone)

## v0.7.1 transcript security follow-up

- [x] Redact across consecutive transcript page boundaries using bounded
  overlapping context and original-character-offset-preserving replacement.
- [x] Real MCP Streamable HTTP protocol test with denied/allowed transcript
  access, local account attribution, and revocation.
- [x] Handle offsets beyond the end of a conversation.
- [ ] Exercise the flow against a live authorized test call in WSL and review
  masking quality on realistic Persian/English transcripts.
- [ ] Verify PostgreSQL role permissions with `./panadan.sh audit-db`.

## v0.7.2 dropdown and mobile UX

- [x] Reusable progressive enhancement for native selects, preserving exact
  original form values and backend permission checks
- [x] Consistent Persian RTL dropdown styling with focus, hover, selected,
  disabled and empty-search states
- [x] Search by Persian display text or original source value for larger lists;
  Persian/Arabic letter forms and digit shapes normalized
- [x] Escape, Enter, Arrow, Home/End, click-outside, scroll placement and
  selection clearing support
- [x] Option lists are rendered above overflow-hidden panels and table scrollers,
  without clipping; Doran Jalali datepicker remains unchanged
- [x] Apply controls to reporting filters, Activity, token ownership,
  OAuth identity binding and user role management
- [x] Mobile navigation shows all sections in horizontally scrollable tabs and
  retains the sign-out action
- [x] Unit tests of filtering, raw value preservation and keyboard movement
- [ ] Real browser visual QA including keyboard, screen-reader and mobile touch

## Operator profiles, directory and conversation/date UX

- [x] Operator name filter across dashboard calls and aggregate statistics
- [x] One-click operator profile with that operator's stats, calls and source detail
- [x] Admin-managed local destination/team assignment and filtering, with
  missing values consistently labeled `نامشخص`
- [x] Read-only operator/team/destination filters in REST, MCP and WebMCP
- [x] Redesign the conversation expand/collapse card and long-analysis controls
- [x] Apply self-hosted Vazirmatn font to Doran inputs/calendar including
  open shadow roots where supported
- [x] Synthetic tests for report query filters, admin authorization and metadata
- [ ] Manually verify the Doran popup font, keyboard focus, mobile transcript
  disclosure and real operator name values against a live deployment
- [ ] Add **real** operator/team/destination RBAC after confirming a stable
  operator ID in source data and enforcing the scope in every API/MCP path
  (see docs/OPERATOR_SCOPES.md).

## v0.8 preproduction stack modernization

- [x] Migrate the official Python MCP SDK from FastMCP v1 to MCPServer v2.3.0
- [x] Keep the authenticated stateless `/mcp/` transport and read-only tools
- [x] Upgrade the runtime to Python 3.13 and Node 24 LTS
- [x] Refresh `uv.lock` and add npm `package-lock.json` with `npm ci`
- [x] Upgrade compatible FastAPI, psycopg, Pydantic, esbuild and other dependencies through lockfile resolution
- [x] Add explicit MCP transport Host/Origin allowlists and v2-native protocol tests
- [x] Build both Docker images in PR CI without publishing them
- [ ] Verify on the user's local WSL/VPN installation, and complete one-click OAuth login/consent

## Reporting display clarification (2026-10-31)

- [x] Display `voice_length` (seconds confirmed by source owner) as human-readable Persian durations in call details and the average-audio-duration metric, without changing API values.
- [x] Mark the raw `deal_value` display as unverified; 3,000 sampled calls contained zeros, which must not be construed as confirmed zero sales or revenue.
- [x] Add a self-hosted SVG favicon linked from all dashboard and login templates.
- [ ] Verify exact upstream definition, currency and population of `deal_value` before treating it as financial reporting.


## AI-estimated likelihood score audit (2026-10-31)

- Source column: `possibility_of_sale_ai` (AI-estimated likelihood of a sale). Treat it as an **estimated source score**, not a calibrated probability or confirmed sale.
- A read-only sample of the 1,000 highest call IDs had 817 non-null scores, 183 missing, min 0, max 100, average 59.19 **among non-null scores**, 21 distinct values, and 14 scores exactly equal to 100. These observations apply only to that sample.
- [x] Label the estimate clearly in the UI; show missing scores as absent rather than zero.
- [x] Return `scored_calls` from the server's aggregate query so the dashboard can show score coverage for its **current filters**, without hardcoding historical samples. `AVG` continues to ignore NULL scores.
- Other sampled fields: `call_time` 993/1000, `tellnum` 1000/1000, acquisition-source name 0/1000, follow-up-stage name 0/1000, and `invoiced_target` 0/1000. Do not expose unknown/sensitive fields before verifying meaning and access policies.
- [ ] Confirm source model calibration/score scale, and define whether `call_time` is a clock time or duration before adding further UI fields.


## Sensitive customer phone click-to-call (2026-10-31)

- [x] Add a user-triggered `tel:` link next to `customertell` in the authorized call detail drawer, with an accessible call label and LTR digits. No automatic call or third-party dialing integration.
- [x] Preserve source formatting for display; normalize Persian/Arabic numerals and presentation separators only for the dialable URL. Malformed, ambiguous, non-text, multi-number or too-short values remain plain text without a call button.
- [x] Reuse the existing `calls:sensitive` server-side permission boundary. Do not add phone numbers to public list, metrics, WebMCP, MCP summary, or unauthenticated responses.
- [ ] Verify the meaning and representation of `tellnum` from source data before using it. It is `double precision` and can discard leading zeroes; do not treat it as an authoritative customer phone number or use it as a fallback.
- [ ] Visual / keyboard smoke test on mobile and desktop; `tel:` opens the device's dialer if one is configured. No call is placed by Panadan itself.

## Source correctness + privacy audit (2026-10-31)

- [x] Document all 36 known view fields and distinguish confirmed values, plausible hypotheses, and unknown source semantics in `docs/DATA_DICTIONARY.md`.
- [x] Add `./panadan.sh audit-fields --limit 300 --offsets 0,1000,5000`, a bounded SQL SELECT-only, aggregated, PII-free source audit for date/time formats, caller-number comparisons, enum coverage, operator ID collisions and incomplete CRM/financial data.
- [x] Include synthetic tests for fixed queries, input bounds, source view restrictions and non-leaking error output.
- [x] Correct the MCP tool count in `docs/READ_ONLY.md`: four summary tools and a fifth separately permissioned redacted-transcript tool.
- [x] Update operator-scope documentation to acknowledge numeric source operator IDs observed in 3,000 sampled rows without claiming that historical stability or user-level authorization is verified.
- [x] The user successfully ran `audit-fields` via WSL/VPN against 3 disjoint 300-row samples; the 900-row aggregate and confirmed field types are documented in `docs/DATA_DICTIONARY.md`.
- [ ] Confirm `call_time`, `tellnum`, `tellside`, `CALLDATE` and `create_date` semantics with source owner. Do not change time conversion or introduce raw phone numbers before verification.
- [ ] Implement numeric-ID operator directory migration and **fail-closed, cross-surface row-level RBAC** only after source identity validation; name filters remain visual filters.
- [ ] DBA-reviewed least-privilege PostgreSQL account; live encrypted MCP/OAuth end-to-end validation; device/browser UX and redaction review.


## WSL PostgreSQL relay timeout diagnosis (2026-10-31)

- [x] Add `./panadan.sh diagnose-db` to isolate VPN route, VPN->PostgreSQL TCP reachability, local relay socket and end-to-end read-only SQL connection without exposing credentials or customer data.
- [x] Improve relay logging to distinguish remote DB connect failures from forwarding failures by exception **type only**, not message/addresses/credentials.
- [x] Add synthetic diagnostic unit tests and a README troubleshooting decision tree.
- [ ] Live user run of `./panadan.sh audit-fields` failed with `ConnectionTimeout` using both 300x3 and 100x1 sample scopes, despite a healthy VPN container and running pgrelay. This suggests a transport/handshake issue; not yet proven which network stage.
- [x] WSL `diagnose-db` passed twice after relay recreation; `audit-fields` then returned complete aggregate JSON for all 900 selected records.


## Docker Desktop/WSL stale relay bind-mount fix (2026-10-31)

- [x] Diagnose an OCI runtime mount failure for the old single-file `./tools/pgrelay.py:/relay/pgrelay.py:ro` after `git pull`; Docker Desktop's preexisting source reference was no longer resolvable.
- [x] Change to a read-only directory mount `./tools:/relay:ro`, preserving the relay's isolated `network_mode: service:vpn` and localhost-only proxy port.
- [x] Replace brittle `docker compose restart pgrelay` recovery advice with `./panadan.sh relay-recreate`, which forces creation of a fresh **relay-only** container and bind reference, leaving the VPN running.
- [x] Add offline regression tests for mount stability and safe operator commands.
- [ ] Confirm the new Compose mount and relay-only recreation work in the user's Windows/WSL Docker Desktop environment. The underlying VPN-to-PostgreSQL no-response issue #26 is independent.

## Source semantic follow-up (2026-10-31)

- [x] The 900-row live audit found `call_time` 893/900, 28,457–67,116, all valid seconds-since-midnight values and 0 audio-duration matches. Time-of-day interpretation remains a **hypothesis**.
- [x] `tellnum` 900/900 and `customertell` 900/900; the basic normalized match was 0/900. Neither this nor the double-precision type establishes `tellnum` as a phone; only `customertell` is used for authorized click-to-call.
- [x] Source dates matched both tested naive and UTC→Tehran interpretations for 899/900, so timezone is **not** resolved by the original audit.
- [x] All observed `deal_value` amounts zero; team/stage/source/target fields remain empty throughout these slices. Keep revenue and team RBAC blocked pending source verification.
- [x] Implement `audit-semantics` with bounded, fixed-query aggregates comparing `call_time` to `create_date` under two timezone interpretations and checking `tellnum` shapes without exposing individual numbers.
- [x] `audit-semantics --limit 100 --offsets 0,1000,5000` returned three 100-row aggregate samples after earlier `ConnectionTimeout` attempts at limit 300. 297/297 comparable clock values align within one hour under UTC→Tehran, 249/297 within five minutes; none within five minutes unadjusted. Median Tehran-adjusted creation lags were 110–134 seconds. All 300 `tellnum` values had 1–4 digits, none matched a customer phone suffix.
- [ ] Confirm upstream definitions of `call_time`, `tellnum`, `CALLDATE`, `create_date`, `tellside`, `tellstate`, `aicallinfostate` and financial fields before changing labels or security boundaries.

## Follow-up interpretation safeguards (2026-10-31)

- [x] Document the 300-row semantic follow-up in `docs/DATA_DICTIONARY.md`. Strong evidence supports `call_time` as seconds after Tehran midnight and `create_date` as UTC-naive; neither is yet source-owner-confirmed.
- [x] Clarify the timezone assumption in the source filtering code, rather than silently changing actual date handling.
- [x] Use 100-row slices as the semantic audit's default to reduce query load; preserve upper bounds.
- [ ] Verify with source administrator whether `tellnum` is an operator extension/line number or another short internal code. Continue to exclude it from customer click-to-call.
- [ ] Confirm the event/timezone of `call_time` (call began, answered, ended, etc.) and `create_date` before exposing the clock field in the UI.
- [ ] Intermittent `ConnectionTimeout` recurred on two 300-row semantic runs before 100-row success; investigate the remote connectivity path if it continues (not proof of SQL statement-timeout).


## Call detail and UI/UX quality pass (2026-10-31)

- [x] Add the strongly supported but source-owner-unconfirmed `call_time` as detail-only source metadata. Format to readable HH:MM Persian digits with an explicit provisional meaning and Tehran-locality note; no claim of call start/end.
- [x] Hide zero `deal_value` from the detail UI (it is not verified revenue), retain any nonzero value as unverified, and preserve all existing raw API values.
- [x] Leave `tellnum` out of calling and reporting; continue using permission-gated `customertell`.
- [x] Improve call detail drawer's mobile/RTL layout, focus management, Escape/Tab navigation, background scroll and asynchronous close/open races.
- [x] Add source column-selection regression tests and Node unit tests for Persian clock formatting and source-zero filtering.
- [ ] Visual and assistive-tech smoke tests on desktop Chrome and an Android phone before production rollout. The current changes have code/CI tests but no actual device screenshots.
- [ ] Source owner to confirm the `call_time` event definition, `tellnum` short-code meaning, and `create_date` timezone contract before further reporting features.

## RTL timestamp presentation consistency (2026-10-31)

- [x] Standardized combined date/time displays so the **clock sits on the right** and the **date on the left**, including call detail overview, recorded creation timestamp, activity audit rows, and token expiry/last-use rows.
- [x] Isolate numeric clock and date fragments from the Persian text direction with RTL flex layout and LTR-isolated subparts; preserve missing values as em dashes.
- [x] Correct the Doran-backed Jalali formatter to honor time-only options (previously only options containing `year` were respected), leaving date-only input behavior unchanged.
- [x] Keep original timezone semantics: call/record/activity displays use Tehran when applicable, token expiry and use retain labeled UTC values, no database/API transformation.
- [x] Add Node locale/format/layout contract tests and a Python authenticated-token template smoke test for visual component order.
- [ ] Perform actual Chrome/Android browser visual checks, including narrow layouts and the third-party Doran input internal layout.

## Filter logic and responsive navigation/metrics polish (2026-10-31)

- [x] Replace optional creation-time datepicker section in dashboard with a more deliberate AND/OR report filter. Existing `created_after`/`created_before` REST/dashboard parameters remain backward-compatible, but controls are no longer shown.
- [x] Allow report filtering on source `tellside` direction codes as raw values without invented incoming/outgoing translations; operator, team, destination, type and status conditions can be combined via AND or OR, with date bounds always AND.
- [x] Apply identical categorical conditions to dashboard KPI aggregates and call-list results. The operator-profile page remains in all-conditions mode; all filters are reports only and **are not** user authorization.
- [x] Isolate Persian duration segments in RTL order instead of letting LTR metric typography reverse units (e.g., `۲ دقیقه و ۵۸ ثانیه`).
- [x] Make desktop sidebar sticky with a visible logout footer; mobile navigation becomes a compact sticky two-row header with horizontally scrollable labeled tabs and a persistent logout button on all authenticated pages.
- [x] Improve mobile report filters, activity error-only checkbox, touch targets, metric cards, and call-list presentation as small readable cards.
- [x] Add synthetic tests for parameterized AND/OR SQL, date constraints, source direction type, matching KPI filters, unsupported mode validation and no-sensitive bypass.
- [ ] Validate visually at 320/375/430px and desktop in actual Chrome/Android, including open searchable dropdowns and Doran datepickers; automated tests are not a replacement for device QA.

## Simplified reporting and mobile navigation, revised after UI feedback (2026-10-31)

- [x] Remove user-facing AND/OR switch and its large filter-logic panel. Implement searchable multi-select controls with checkboxes for operator, team, destination, call type, AI status and direction; selected values combine via OR, while dates and fixed operator-profile scope remain AND constraints.
- [x] Use parameterized `= ANY(%s)` comparisons and bounded lists (20 per filter); expose repeated parameters on the dashboard endpoints and keep lists and KPI values aligned. No changes to source Odoo rows or user authorization.
- [x] Confirm and translate source direction labels: `IntoOut` = `خروجی` (outgoing); `OutToIn` = `ورودی` (incoming). Preserve raw codes and show unknown values unchanged.
- [x] Replace the crowded mobile strip with up to four grouped, permission-aware button tabs: گزارش‌ها، کارشناسان، اتصالات، مدیریت. Add the Operators link across admin navigation.
- [x] Tighten vertical spacing and wasted grid space: four columns on desktop, two on mobile, compact actions, tighter header/metrics, and mobile bottom-sheet searchable selection lists.
- [x] Add unit/test contracts for multi-option request handling, OR predicate safety, fixed operator profile scope, mapping direction labels and four mobile groups.
- [ ] Validate actual Android/desktop screenshots for 320–430px and 700–800px viewport widths, Doran shadow DOM sizing, mobile dropdown keyboard, mobile menu overlay and screen-reader focus. Do not claim device QA from CI.

## Selection and navigation refinement (2026-10-31)

- [x] Replace multi-select checkboxes with full-width clickable choices that display an inline checkmark only when selected. Preserve the searchable list, selected count, bounded selection and native multi-select state.
- [x] Remove the unnecessary per-dropdown Clear and Confirm footer. Tapping a choice updates the selection immediately; the dropdown remains open for further choices, and closes on outside interaction or Escape. The main dashboard still has its usual report submit/reset actions.
- [x] Apply the four-tab ULTOR mobile navigation pattern: fixed safe-area-aware bottom bar of true buttons, active tab highlighting, compact grouped section chooser displayed **above** the bar, and logout available in a slim sticky top header. Show only authorized destinations.
- [x] Remove unwanted desktop sidebar **horizontal** scrolling by constraining links to sidebar width and allowing labels to wrap, without hiding vertical navigation or logout.
- [x] Add automated UI contract checks for buttons, checkmarks, no dropdown footer, max selection cap, bottom positioning and absence of desktop sidebar horizontal overflow.
- [ ] Test real Chrome/Android layouts at 320px, 375px, 430px, and desktop widths. Verify focus, on-screen keyboard, Android safe area, fixed bottom bar and long Persian navigation labels visually; CI alone is not visual QA.

## Dashboard data 503 observability (2026-10-31)

- [x] After a clean 141 Python + 47 Node test run and WSL FastAPI startup, the user observed `/dashboard/data`, `/dashboard/metrics`, and `/dashboard/filter-options` returning HTTP 503. Static assets and `/dashboard` itself responded normally.
- [x] Preserve the privacy-safe generic 503 to callers, but log **only** validated SQLSTATE and backend exception class server-side; never log SQL, parameters, connection strings, customer records or exception message.
- [x] Add tests covering all three reporting endpoints and invalid SQLSTATE scrubbing.
- [ ] On the user's local WSL/VPN, run `./panadan.sh diagnose-db` while FastAPI is running, and use sanitized new logs after FastAPI restart to determine whether the failure is transport, query/permission, or statement timeout. Container health is not sufficient evidence.
- [ ] Verify the dashboard loads actual reporting data on desktop and mobile. This was not checked against the private live DB from CI.

## Local reporting-store readiness audit — live result 2026-10-31

- [x] Source operator pulled `2f31e2c`; Python **162 passed** and Node **51 passed**.
- [x] `./panadan.sh audit-sync --sample 100` completed successfully over the VPN.
- [x] Live catalog: ordinary reporting **view** with 36 columns; `id` integer, `create_date` present, **no recognized update marker and no recognized deletion marker**.
- [x] All 100 sampled IDs non-null/distinct; all 100 `create_date` values present; zero sampled creation-order inversions. **This is not full-history uniqueness/monotonicity proof.**
- [x] EXPLAIN-only estimate: 93,396 rows × 3,049 bytes; do **not** treat it as actual count/storage. Findings and source-owner requirements recorded in `docs/LOCAL_REPORTING_SYNC.md`.
- [ ] Obtain stable-ID contract, view-wide update feed or guaranteed `sync_updated_at` semantics, deletion/tombstone feed and customer-data retention approval from source owner.
- [ ] Measure safe sample batch latency and actual record/transcript sizes before sizing database or scheduling full history backfill.
- [ ] After contract approval, implement isolated local PostgreSQL schema and resumable keyset backfill with transactional checkpoints, then incremental worker, parity checks and authorization-safe read cutover.
- [ ] Redis remains deferred pending measured need. No customer records have been copied by the audit.

## Multi-source data platform foundation (2026-10-31)

- [x] Add an **opt-in**, source-agnostic PostgreSQL schema for connector registry, disabled-by-default sources, current source records, versioned raw payloads, explicit deletion tombstones, versioned processing jobs/facts, per-stream checkpoints and aggregate sync runs.
- [x] Implement a synthetic-only ingestion library with bounded JSON batches, deterministic hashes, idempotent UPSERTs, revision history, per-stream checkpoint row locks and atomic checkpoint/jobs/revisions commits. A stale worker cannot overwrite an advanced checkpoint.
- [x] Implement a library-only public call metadata normalizer (`normalize:v1`) that reads allowlisted fields and never copies customer names, phone numbers, transcripts or AI prose to derived facts; retain exact raw revision provenance.
- [x] Add a dedicated disposable PostgreSQL integration CI job covering duplicate deliveries, updates, explicit tombstones, resurrection, stale checkpoint conflicts, transaction rollback, provenance, jobs and no-sensitive-field facts.
- [x] Document how to use the migration safely on a new Panadan-owned database and why the existing auth SQLite and source Odoo read path remain unchanged.
- [ ] Confirm source-owner stable IDs, full-view update events/timestamps, deletion tombstones and permission/retention for raw customer data **before any live copying**.
- [ ] Provision separate encrypted reporting PostgreSQL with least-privilege users, tested backups and a lawful retention/purge policy before ingesting real source payloads.
- [ ] Build the read-only Odoo adapter, bounded backfill, supervised job scheduler, authorized serving path, deletion/reconciliation, data-quality metrics, and cross-surface RBAC checks. No live mirror/cutover has occurred.

## Odoo new-row and updated-row sync readiness (2026-10-31)

- [x] Build a read-only Odoo adapter with a fixed, approved field allowlist and hardcoded SQL, supporting either `updated_at` or `sync_updated_at` (both strict, allowlisted identifiers) and an explicitly verified UTC-naive or timestamptz source contract.
- [x] Implement bounded ID keyset pages for both **historical backfill** and **subsequent new calls**. No OFFSET pagination, max 200 records/page (default 100), no full source scan on one request.
- [x] Implement modified-call polling in frozen, paginated timestamp+ID windows with a source-clock settling delay and a replay overlap; cursor persists marker name to fail closed on schema changes.
- [x] Seed the update stream before the ID backfill to capture edits that occur during import; ingestion writes raw revisions, processing jobs and checkpoints using the pre-existing one-transaction Panadan-owned PostgreSQL pipeline. Source remains READ ONLY.
- [x] Add synthetic PostgreSQL end-to-end tests for edited old calls, new calls, backdated new-row timestamps, same-timestamp ID ties, replay idempotence and incomplete source schema.
- [ ] Obtain source owner's global stable-ID guarantee, view-wide edit marker contract, timestamp storage mode, field retention approval and separate writable Panadan PostgreSQL environment.
- [ ] Enable an explicitly approved, supervised source adapter runner and verify a bounded 100-row pilot before any actual history import; no CLI/cron/live import is enabled by this PR.
- [ ] Build cautious periodic ID reconciliation for disappeared rows (do **not** infer deletion from an incomplete page or transient VPN failure) and implement purge/retention policies before sensitive payloads.
- [ ] Set up scheduling/health alerts and parity/authorization tests before dashboard/REST/MCP cutover. Redis remains deferred.
