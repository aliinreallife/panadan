# Unified field permissions and MCP delegation — local testing / release gates

**Development branch:** feat/unified-field-access-mcp-20261109
**Base:** `main` (PR #99 permission groups and PR #98 mirror-health UI are merged).
**Status:** synthetic local and GitHub CI checks pass on the integration branch;
**security signoff and production deployment are NOT approved**.
This is an incremental security change; do not mix it with PR #97's Odoo
mirror cutover. The newly merged PR #98 web health panel is preserved.

## What is implemented in this branch

- A user has server-validated individual reporting field grants. Existing
  users without a field-grants row keep exactly their legacy capability-based
  reporting projection until an admin explicitly changes it.
- The admin user editor supports narrowing individual fields (and can choose
  a default group first).
- The browser dashboard and REST call list/details are projected down to
  the user's field selection. Per-record queries also require an explicit
  call ID field grant. Call-list ordering uses only permitted date/ID fields;
  status lists, filters and supported aggregates are gated by their inputs.
- **Raw transcription is excluded from generic call JSON**, including when
  calls:sensitive is granted. Transcripts require a separate explicitly
  authorized, audited, best-effort-redacted excerpt operation; no masking
  technique guarantees anonymization.
- Standard MCP tools recheck the current user, token or client grant, then
  enforce per-tool capabilities and project returned call fields. Metrics-only
  or calls-only MCP clients are supported by the new policy.
- Access discovery: MCP tools get_my_access and explain_access(field);
  REST GET /api/v1/me/access. No arbitrary user-id query or customer lookup.
- New manual MCP and REST API tokens snapshot the owner's allowed
  columns/capabilities. Later user grants cannot silently expand already
  issued token rights. Previously issued API tokens with NULL snapshots
  retain legacy dynamic grants until planned revocation/rotation; inventory
  these credentials before enabling a new permission model.
- OAuth MCP bearer ingress now requires a cryptographically verified, signed
  client identity (azp/client_id). Unconsented but properly identified
  clients can still discover how to request consent; data tools deny access.
- User-managed client-specific OAuth subset approvals at
  GET /dashboard/mcp-apps, POST /dashboard/mcp-apps/approve and /revoke.
  The new-client form preselects eligible user access, and existing clients
  retain their saved subset when edited. Actual MCP tools require a signed
  JWT containing a matching, validated azp/client_id.
- Existing audited, redacted transcript tool is separately gated by the
  transcript capability and delegated transcription field.

## What is NOT implemented or ready for production

1. The observed source view has **37 columns**, but production reporting
   currently exposes **19 hard-coded reporting fields**. This branch restricts
   those already available fields only. Never turn on mirror-only fields by
   widening the field registry before the production read-path/security
   contract and duplicate-join behavior have been reviewed.
2. No row-level/team-level authorization migration. Existing operator filters
   are NOT a security boundary. Do not promise that this prevents access to
   another employee's calls. This needs its own authorization design.
3. Panadan remains an OAuth **resource server**, not an IdP or authorization
   server. A trusted, real IdP must issue RS256-signed access tokens with a
   verified subject, scope, audience AND client identity (azp/client_id).
   This branch adds a **manual user approval screen for that client ID**,
   not an automatic IdP redirect into a Panadan consent screen.
   ChatGPT/Claude OAuth authorization is not yet end-to-end verified.
4. The experimental PostgreSQL authentication backend is **staging-only**.
   This version's new per-user field persistence is on the normal production
   SQLite auth backend. Staging PG auth tests must be revisited before
   enabling unified policies there. Missing support fails closed.
5. MCP tools/list may still advertise general tool names. Every data-bearing
   tools/call has independent request-time server enforcement, but filtering
   the discovery list to the caller's grants is a separate UI/privacy step.
6. No user-to-admin access-request workflow yet. explain_access instructs
   which kind of approval is missing but does not send a request.
7. GitHub Actions CI is now available. The four quality/integration/Docker
   checks passed on commit `26263ec` after the combined `main` merge.
   Passing CI is not approval to merge/deploy: complete the security and
   production recovery acceptance criteria below first.

## Run tests only on your development WSL computer

**Do not run this on your production VPS** with the nearly full root disk,
working VPN, Odoo credentials, staging mirror or Plane deployment.

~~~bash
set -euo pipefail
cd "$HOME/panadan"
git fetch origin refs/heads/feat/unified-field-access-mcp-20261109
git worktree add --detach "$HOME/panadan-unified-test" FETCH_HEAD
cd "$HOME/panadan-unified-test"

uv python install 3.13
uv sync --locked --dev --python 3.13

# Start with the narrow synthetic tests; no source DB access.
uv run --locked python -m pytest -q \
  tests/test_unified_field_access.py \
  tests/test_unified_http_access.py \
  tests/test_rbac.py \
  tests/test_permission_catalog.py \
  tests/test_mcp_http_integration.py \
  tests/test_oauth.py

# Then verify the entire existing application.
uv run --locked python -m pytest -q
uv run --locked python -m compileall -q server tests tools

node --check static/users.js
node --check static/fields.js
node --check static/mcp-apps.js
node --test tests/*.test.mjs

npm ci --no-audit --no-fund
npm run build
for script in panadan.sh tools/*.sh; do bash -n "$script"; done

echo "PASS: local quality tests completed"
~~~

These tests require project dependencies, not a live PostgreSQL mirror.
The full tests include synthetic PG-marked coverage that can require an
isolated disposable Docker/PostgreSQL fixture; follow its documented
instructions rather than connecting to any real reporting database.

## Additional security acceptance required before merging

- Verify actual MCP Streamable HTTP requests and SDK context injection.
  Context headers and token identity must be present on EVERY tool call.
  Test get_my_access, explain_access, calls-only, metrics-only, limited
  source-field projection, redacted transcript consent and revocation.
- Verify no forbidden fields leak via sorting, filtering, statuses,
  aggregate metrics, summaries, pagination, errors, front-end metadata,
  logs or model-facing tool descriptions.
- Repeat with a configured, isolated OAuth issuer, two different signed
  client IDs and one user. No client can borrow another client's consent.
  Tokens with missing/conflicting azp/client_id cannot read data.
- Confirm that changing user permissions revokes sessions/manual tokens/
  existing OAuth binding and client approvals according to the current
  conservative backend. Require a new user approval where appropriate.
- Review account administration, no-admin-grant bypass, CSRF, XSS, and
  a safe rollback with the existing SQLite volume preserved.
- Test local team/row boundaries before promising any subject-specific
  access restrictions.
- Run production controller read-only plan/check and reviewed pinned
  web-only release. **Never** run bare panadan.sh up/down on the hardened
  Panadan/Plane VPS. Don't deploy until there is a legitimate published
  image and explicit recovery review.

## User-visible access behavior

An AI may call get_my_access() for its current allowed columns, then
explain_access(field="customertell") to determine whether it needs an admin
grant or user consent. It must never claim another person's record exists.
An admin may enable a missing field in the user editor. The user can then
approve a smaller subset on /dashboard/mcp-apps for a signed OAuth client.
No AI tool can assign itself a new permission.
