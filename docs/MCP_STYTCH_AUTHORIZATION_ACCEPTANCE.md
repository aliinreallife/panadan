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
