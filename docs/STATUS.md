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
- [ ] Run `./panadan.sh audit-db` with the actual VPN-connected PostgreSQL login; previous audit indicated CREATE on public.
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
