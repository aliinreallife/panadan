# Panadan MCP + Stytch authorization acceptance

**Status:** Draft PR #104. No Panadan production cutover. All test tokens,
accounts, and reports below are synthetic. This document describes the code
and tests on the PR branch; do not interpret them as live production evidence.

## Why Stytch stays the authorization server

Panadan's OAuth design intentionally separates:

1. **Stytch**: OAuth discovery, DCR/CIMD, login, PKCE, client ID, signed
   access-token issuance, expiry, issuer and JWKS.
2. **Panadan**: verified JWT -> explicit (issuer, subject) to local-user
   mapping -> active local account -> per-client consent -> least-privilege
   capability and field intersection -> MCP read-only tool.
3. **Transport**: a 401/WWW-Authenticate challenge for unauthenticated,
   malformed, unlinked or expired access tokens; per-tool permission denial
   for a valid, linked, but unconsented client.

LIRO's private analytics MCP, inspected as an architectural reference, issues
opaque tokens in-app and stores token hashes, grants and refresh-token rotation
locally. Panadan should reuse its **operational controls** (consent, audit,
immediate local revocation), not copy its self-hosted token issuer or opaque
token storage. Panadan already has matching permission primitives in
`server/security.py` and `server/security_pg.py`.

**Do not treat successful Stytch consent as Panadan reporting consent.**
A Stytch Test client may register dynamically and obtain a signed JWT but
still have no local reporting field permission.

## Verified and unverified evidence

| Boundary | Evidence and status |
| --- | --- |
| Stytch Test CIMD-initiated PKCE and exact MCP audience | **PASS**, manually configured Test client and 60-minute signed token |
| Stytch Test -> isolated synthetic MCP tool with approved client | **PASS**, live HTTP 200 after stricter allowlist deployment |
| Synthetic MCP without valid bearer | **PASS**, live HTTP 401 |
| Different DCR Inspector client | **Observed HTTP 401**, but concurrent re-registration and the older default token audience/lifetime prevent attributing the denial to the allowlist without a verified fresh token |
| Production-code signed JWT to local user + capability/field controls | **Automated test** with offline-generated RS256 signatures and synthetic rows; not a live Stytch-to-production result |
| Revoking consent, narrowing fields, unlinking subject, disabling account | **Offline HTTP regression tests** on the same MCP tool path; CI result must be checked on the PR revision |
| Arbitrary DCR/CIMD automatically receives correct resource audience | **Unproven**; Test currently required per-client audience configuration |
| Refresh/revocation/JWKS rollover under Stytch, production account migration | **Unproven** |

The synthetic Vercel resource at
`https://panadan-mcp-oauth-staging.vercel.app/mcp/` is **not** wired to
the production Panadan database or reporting tools. It must stay that way.

## Automated acceptance test

`tests/test_oauth.py::test_real_signed_oauth_clients_are_isolated_on_mcp_http`
runs the **real Panadan FastAPI/MCP request handlers** with a temporary
local SQLite auth store, synthetic reporting rows and locally minted,
RS256-signed JWTs. It has no Stytch, Odoo, VPN or production dependencies.

Its lifecycle covers:

- A valid, scoped, signed but unlinked subject is denied by the bearer gate.
- A bound subject without signed client identity, wrong audience or
  mismatched signed `azp`/`client_id` is denied.
- A linked but unapproved client can discover safe empty access metadata;
  it cannot retrieve reporting data or another application's grants.
- Two explicitly approved clients see **different, intersected** field and
  capability sets; customer-like sensitive synthetic sentinel never leaks.
- Revoking client consent blocks data access for that client without
  revoking another approved client.
- Reapproving with *fewer fields* immediately redacts existing,
  still-unexpired signed JWT requests.
- Unlinking a Stytch-like subject immediately results in **401** for
  each issued client token; rebinding cannot approve an unknown client.
- Disabling a local user removes the identity binding and consent, and
  existing signed tokens are denied.

For isolated development only:
```bash
uv run --locked python -m pytest -q tests/test_oauth.py
```
The GitHub CI `quality` job runs these tests automatically on PRs.

## Live next gate: production-code integration, without production data

Do **not** change `PANADAN_MCP_AUTH_MODE` on production.

1. Deploy the *real Panadan MCP authorization and permission code* in a
   **separate disposable environment** with synthetic reporting data and
   a disposable auth store; pin Stytch **Test** issuer, JWKS and canonical
   staging resource.
2. Provision a temporary local Panadan user with only `mcp:use` plus
   one read capability. Admin-bind a dedicated Stytch Test `sub` to that
   user. Approve the exact Stytch Test client and **one non-sensitive
   reporting field**.
3. From an approved client, verify that only the delegated field appears,
   then remove the field/client grant and ensure the *same unexpired*
   signed JWT no longer obtains reporting data.
4. Unlink the Test subject and disable the account independently; the
   request must fail even while the JWT signature, `aud`, scope and
   expiration remain valid.
5. Reproduce an **unapproved** DCR client with a fresh token whose issuer,
   canonical `aud`, scope and TTL are independently confirmed. It must
   get no data. Do not add that client ID to the allowlist or assume any
   HTTP 401 alone proves the client policy.
6. Test token expiry, provider-side revocation semantics, replay,
   refresh-token behavior (if enabled), JWKS rotation and clean rollback
   before any production migration.

**Release policy:** Keep PR #104 draft and legacy bearer mode intact until
a separately approved acceptance plan covers real user mapping, client
consent, reporting-field restrictions, incident rollback and operational
monitoring. Avoid raw tokens, PII, source call rows or client secrets in
logs, screenshots or reports.


## Disposable real-authorization staging: deployed and negative checks PASS

**Deployment:** Dedicated Vercel project `panadan-authz-integration-staging`
(`prj_vQH5KZpXcSXuU2uxm6uzxJuchaJO`), source snapshot from tested
PR commit `099bfc91447739e39e90ee4135f7efa628429f09`.
Deployment `dpl_EoddUMx8N2umXQdrsQ6NREPjfmUz` is **READY** at:

`https://panadan-authz-integration-staging.vercel.app/mcp/`

The new service was uploaded as **ten explicitly reviewed source files**
through Vercel's source-file API because Git-backed deployment failed
under GitHub's API rate limit. No Panadan production project or production
configuration was deployed. All four GitHub workflows passed on the source
commit, including the isolated real-authorization integration tests.

**Public smoke, independent of real credentials:**
- `GET /healthz` = 200, `synthetic-only`,
  `authorization=panadan-real-policy`.
- `GET /.well-known/oauth-protected-resource` = 200, exact
  canonical staging resource and Stytch **Test** issuer.
- Unauthenticated and invalid-bearer `POST /mcp/` = 401, correct
  WWW-Authenticate protected-resource metadata challenge.
- `GET /dashboard`, `GET /api/v1/calls`, `GET /docs` = 404.
- No runtime errors found in the examined Vercel window.
- Project has **zero Odoo/VPN/PostgreSQL/production Stytch env vars**.
  Its approved subject hash is stored as an encrypted Vercel env var.
  The synthetic auth DB is ephemeral SQLite in a /tmp function instance;
  no cross-instance revocation persistence is claimed.

**The Test client configured for this new isolated project** is the
existing, previously registered **MCP Inspector DCR** Connected App,
`connected-app-test-2d48e426-3f1c-4aa9-b30b-27f7ee5780e1`.
It is NOT approved on the older synthetic resource.
The disposable Test member's SHA-256 identity is pinned; no user profile
or raw JWT is stored in this documentation.

### Human steps needed for real Stytch Test JWT acceptance

1. In Stytch **Test → Connected Apps → Apps**, edit only the above
   **MCP Inspector** client. Change **Custom JWT Audience** to the exact
   `https://panadan-authz-integration-staging.vercel.app/mcp/`.
   Keep **Access Token Expiry = 60 minutes**. Do not edit the existing
   CIMD Test client or Stytch Live configuration.
2. In MCP Inspector, create/select a **separate** Streamable HTTP
   connection to that new /mcp/ URL. Set Client ID explicitly to the
   DCR client ID above, Client Secret empty, scopes
   `openid panadan:mcp:read`, Authorization URL override
   `https://panadan-stytch-oauth-staging.vercel.app/oauth/authorize-compat`,
   Token URL override empty, refresh token request OFF. The expected
   redirect is `http://127.0.0.1:6274/oauth/callback`.
   **Do not clear the stored client registration**, or a new DCR client
   may be created.
3. Re-authorize using the SAME disposable Stytch Test member as the
   successful CIMD Test run. Open MCP tools and call:
   - `get_my_access`: only `id` and `CALLDATE` are delegated;
   - `list_recent_calls`: only synthetic call `73104` with
     `id` and `CALLDATE`, no confidential sentinel;
   - `get_call_metrics`: `permission_denied`.
4. Share **only sanitized tool output and HTTP status**, never the JWT,
   auth code, PKCE verifier, session cookies, or user subject.

A real Test JWT/tool invocation on this new service is **PENDING** until
the browser steps above complete. Durable permission-revocation semantics
require an isolated, persistent auth store; the current /tmp SQLite
fixture tests in-instance revocation and is not a production architecture.

Keep PR #104 draft/unmerged and the real Panadan server in legacy bearer
mode. Do not merge or cut over production from this result.


## Stytch Test authorization-request compatibility fix — 2026-11-15

**Root cause:** The Stytch Test authorization frontend's
`src/lib/flow.ts::validateAuthorizationParams` previously accepted only the
older synthetic MCP `resource` URI. MCP Inspector correctly sent the
**separate integration staging** resource, so the frontend showed
"Invalid authorization request" *before* Stytch Test consent. This was
not a JWT, issuer, member, or scope failure.

**Change:** The exact two trusted Stytch Test resources are now explicitly
allowlisted. Arbitrary resource URLs, altered paths, duplicates and empty
resource values still fail closed. No PKCE, callback, issuer, or signed
access-token checks were weakened.

**GitHub:** PR #104 remains draft/unmerged. All four CI workflows passed on
commit `40062f61f978abbfb49f8495f4f871f025b108f6`.

**Vercel:** The existing dedicated Test authorization UI project
`panadan-stytch-oauth-staging` deployed commit `40062f6` as
`dpl_6QYQb5j5XUVk5PSshAGQ9d9tCpAi`, READY with the canonical
`https://panadan-stytch-oauth-staging.vercel.app` alias.

**Browser smoke without credentials:** A synthetic well-formed request
containing `resource=https://panadan-authz-integration-staging.vercel.app/mcp/`
reached `/login` rather than the invalid-request screen. An otherwise
identical request with an untrusted resource URL was rejected on
`/oauth/authorize-compat` with "Invalid authorization request".
These checks do **not** prove Stytch Test login/consent, token exchange,
or signed JWT acceptance on the new integration service.

**Remaining manual gate:** In MCP Inspector, start **new** authorization
against `https://panadan-authz-integration-staging.vercel.app/mcp/`
with the **existing** approved Stytch Test DCR client
`connected-app-test-2d48e426-3f1c-4aa9-b30b-27f7ee5780e1`.
Keep its Stytch Test audience set to this exact integration resource,
60-minute token expiration, and redirect
`http://127.0.0.1:6274/oauth/callback`. Do not clear stored client
registration, add new client approvals, or touch Stytch Live.

Expected successful synthetic outputs: only `id` and `CALLDATE` in
`get_my_access`; one synthetic call `73104` in `list_recent_calls`;
`permission_denied` for `get_call_metrics`. Preserve screenshots
without JWTs, auth codes, PKCE verifiers, cookies, or local Inspector API
tokens.
