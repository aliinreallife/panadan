# Isolated Panadan Stytch Test MCP resource

This independent FastAPI/MCP SDK app is for cryptographically verifying Stytch Test
access tokens and exercising synthetic MCP tools. It contains **no** customer data,
Panadan production database connection, Legacy bearer tokens, external proxy,
or Odoo code.

Canonical resource: `https://panadan-mcp-oauth-staging.vercel.app/mcp/`.

* Test issuer: `https://viridian-faucet-2753.customers.stytch.dev`
* JWKS: `https://viridian-faucet-2753.customers.stytch.dev/.well-known/jwks.json`
* Scope: `panadan:mcp:read`
* Signed Stytch **Test** client ID + explicitly pinned SHA-256 of Test `sub` required.
* Default policy is a single pinned client; a narrowly scoped opt-in
  `any-test-client` policy is available for synthetic-only DCR/CIMD validation.
  Stytch handles registration; this resource never trusts client-supplied
  metadata/headers or JWTs without full RS256 verification.
* A valid access token alone is **not** enough.
* `oauth_mcp.py` is a verbatim copy of `server/oauth_mcp.py` from the
  same Panadan PR branch; do not weaken the shared verifier.

## Required Vercel environment values

The dedicated **staging-only** project must have:
```text
PANADAN_MCP_AUTH_MODE=oauth
PANADAN_OAUTH_ISSUER=https://viridian-faucet-2753.customers.stytch.dev
PANADAN_OAUTH_JWKS_URL=https://viridian-faucet-2753.customers.stytch.dev/.well-known/jwks.json
PANADAN_OAUTH_RESOURCE=https://panadan-mcp-oauth-staging.vercel.app/mcp/
PANADAN_OAUTH_SCOPE=panadan:mcp:read
PANADAN_STAGING_CLIENT_ID=connected-app-test-e2f5508f-e63e-4a7a-8fab-207276bda582
PANADAN_STAGING_CLIENT_MODE=pinned
PANADAN_STAGING_SUBJECT_SHA256=<64-hex-value-for-disposable-Stytch-Test-member>
```

Until a real subject hash is explicitly configured the staging MCP must deny
all bearer access. A placeholder of 64 zeros deliberately denies all members.

## Smoke test

```bash
uv run --locked python tools/check_mcp_oauth.py \
  https://panadan-mcp-oauth-staging.vercel.app/mcp/
```

The preflight validates public discovery and the unauthenticated 401 challenge,
**not** a successful signed token or a real MCP tool call.

## Mandatory gates before any integration

1. Configure Stytch **Test** Connected App's audience to match the canonical
   staging resource and check the next token's `aud` claim.
2. Confirm the resource indicator is forwarded at authorize and token exchange
   for clients that send it; do not assume static per-client audience suffices.
3. Obtain the disposable member's SHA-256 subject binding without displaying
   or persisting the raw JWT.
4. Confirm real RS256 signature, exact audience, issuer, scope, lifetime and
   signed client, then successful synthetic tool access.
5. Deny wrong user/client/audience, revoked access, malformed and expired JWTs.
6. Keep all Panadan production services in Legacy bearer mode.

Never copy Test keys to the production project. Never set the production MCP
audience on Stytch Test tokens.


## DCR/CIMD interoperability test (isolated synthetic staging ONLY)

**Stytch Test already has DCR and CIMD enabled.** They are client
registration mechanisms, not permission to consume the MCP resource. In
particular a dynamically registered client's JWT `client_id` may be a
Stytch internal `connected-app-test-...` value even when the OAuth client
identified itself with a CIMD metadata URL. JWT `client_id` alone cannot
prove which registration method was used.

The resource has two deliberate client authorization modes:

| `PANADAN_STAGING_CLIENT_MODE` | Policy |
| --- | --- |
| `pinned` (default) | Require exact approved Test Connected App `client_id` plus pinned Test member |
| `any-test-client` | Accept a **signed Stytch Test Connected App client ID** for that same approved Test member, only if the normal verifier has already validated RS256, pinned Test issuer/JWKS, **exact `/mcp/` audience**, `panadan:mcp:read`, expiry/TTL, and token purpose |

Both modes still require a well-formed, explicitly configured
`PANADAN_STAGING_CLIENT_ID` and 64-hex
`PANADAN_STAGING_SUBJECT_SHA256`; missing or invalid values deny all.
An unknown mode fails application startup. No production service imports this
staging policy; it only serves a fixed synthetic `get_staging_access` tool.

**DO NOT set `any-test-client` in a service with Panadan customer data,
production accounts, or real reporting tools.** A dynamic client may be
self-registered, so Test consent + JWT client identity is not a production
client trust/approval mechanism. Turn it back to `pinned` after testing.

### Manual live validation

1. Create a new Inspector server config pointing to the canonical MCP
   `/mcp/` resource. Clear saved credentials and leave **Client ID blank**
   so the client must discover and register. Set only
   `openid panadan:mcp:read` scopes; do not disable RFC 9207 validation.
2. Inspect **Connection Info** and auth network records to determine whether
   Inspector used CIMD (HTTPS metadata URL as OAuth `client_id`) or DCR
   (registration POST and opaque `connected-app-test-...` ID). An already
   listed DCR registration is proof of registration, not tool access.
3. Complete Test-member login/consent and attempt `get_staging_access`
   with `any-test-client` enabled **only on the isolated staging project**.
4. The tool must return only the expected synthetic response. If the attempt
   fails with 401, check the sanitized token audience in a secure Test-only
   diagnostic flow; **do not weaken the required audience to the Stytch
   project ID**, and do not share access tokens, codes or PKCE verifiers.
5. Restore `pinned` mode when done. Record DCR/CIMD separately; a successful
   DCR test does **not** establish CIMD compliance.

**Resource indicator limitation:** MCP clients should send the canonical
resource URI in both authorization and token requests. A custom audience
configured on the original manually registered Stytch Test client does
not prove that DCR/CIMD clients automatically get the resource audience.
If the new JWT contains only the Stytch Project ID, access MUST remain
denied until the issuer actually produces the exact canonical audience.


## Hosted Test CIMD client smoke (2026-11-12)

The independent Stytch Test authorization frontend hosts one static HTTPS
OAuth Client ID Metadata Document (CIMD):

`https://panadan-stytch-oauth-staging.vercel.app/.well-known/panadan-test-cimd.json`

It declares an exact owned HTTPS client ID and redirects only to
`https://panadan-stytch-oauth-staging.vercel.app/oauth/test-callback`.
No keys or client secrets are published or required.

When **and only when** the isolated synthetic MCP resource is explicitly in
`PANADAN_STAGING_CLIENT_MODE=any-test-client`, its policy recognizes a
Stytch-Test-signed `client_id` equal to that **exact** owned URL in
addition to Stytch's internal Test UUID client IDs. Other URL client IDs,
Stytch Live IDs, wrong members and tokens without the canonical `/mcp/`
audience are denied.

To test from a browser with an existing Stytch Test member session:

1. Open `https://panadan-stytch-oauth-staging.vercel.app/oauth/test-client`.
2. Select **CIMD: HTTPS metadata document (experimental)**.
3. Start authorization, sign into Stytch Test if prompted, and consent.
4. The custom PKCE callback now also requires the exact HTTPS RFC 9207
   authorization-response issuer; legacy issuer and duplicate `iss` deny.
5. Click **Exchange code & test synthetic MCP**. Only sanitized token
   metadata and a safe synthetic-probe verdict will appear.
6. Confirm the result's `aud` includes the exact canonical MCP URI.
   If the provider rejects the `resource` parameter or only issues a
   project-audience JWT, report the sanitized error but DO NOT weaken
   `OAuthVerifier` or grant actual Panadan data permissions.

**Important limitation:** This browser diagnostic emits the `resource`
parameter in the incoming authorization URL and at Stytch token exchange,
but Stytch's installed headless `idp.oauthAuthorizeSubmit` SDK currently
does not expose a typed `resource` field. Consequently this test alone
cannot prove the SDK forwarded the RFC 8707 resource at authorization-submit.
A compliant external MCP client's actual authorization and token requests
must be separately verified. DCR remains an independent test mode.


## CIMD 401 diagnosis and restricted client approval (2026-11-12)

A real Stytch Test **CIMD browser PKCE flow** completed code exchange,
but the live synthetic MCP probe correctly returned **HTTP 401**.
The token metadata was **decoded only** in the UI, not independently
signature-verified at that point. The observed signed-claim candidates:

- `aud` included only
  `project-test-5ce2a5ad-c6a8-4177-a6a4-a918c7add228`, **not**
  `https://panadan-mcp-oauth-staging.vercel.app/mcp/`.
- `exp - iat = 28800` seconds (8 hours), **above** Panadan's
  3600-second staging maximum.
- `scope` contained `panadan:mcp:read`; internal signed Stytch
  client ID was `connected-app-test-548c584f-4a24-4fab-9054-84e463e44acc`
  for this CIMD registration. The internal client ID is normal even when
  the OAuth client identifier sent in the request was an HTTPS CIMD URL.

Both wrong audience and excessive lifetime **independently** cause
the strict Python MCP resource verifier to return 401, irrespective of
client approval. Do not change the trusted resource audience, 1-hour TTL
gate, signature validation, or Stytch Test member binding.

**Safer rollout:** New `approved-test-clients` mode accepts ONLY the
existing pinned Test client and an explicit, bounded (max 8 unique IDs)
comma-separated `PANADAN_STAGING_APPROVED_CLIENT_IDS` allowlist of
Stytch `connected-app-test-UUID` IDs. All clients still need valid
signed Test JWTs, exact resource audience, scope, and pinned Test member.
An unknown/unconfigured allowlist fails startup; random DCR clients
do not gain access just by registering. The older `any-test-client`
experiment stays supported for historical tests, but the deployed
synthetic staging project should use `approved-test-clients` while
evaluating this specific CIMD registration.

**Next external issuer-side configuration (Stytch Test only):**
In **Management → Connected Apps → Apps**, open the new Test client by
its internal `connected-app-test-548c...` ID. Under its settings,
set **Custom JWT Audience** to the exact canonical `/mcp/` URL and
**Access Token Expiry** to **60 minutes**. Save, then generate a
**fresh authorization code and new token** via the owned CIMD test
page, choosing **Exchange code & test synthetic MCP**. Old tokens
retain their original aud and exp and will not become valid retroactively.

Stytch's Connected Apps Clients management API also exposes
`access_token_custom_audience` and `access_token_expiry_minutes`;
if the dynamically registered client cannot be edited in the Test
dashboard, verify this option in the Test-only Management API.
Do not send Stytch secrets or raw tokens in chat.

**Architectural limitation:** Per-client audience configuration is
sufficient only for this known client, not proof of automatic
RFC 8707 resource-specific audience issuance for arbitrary CIMD/DCR
clients. An issuer-level secure policy is still required before an
unrestricted production rollout. Current Panadan production is
unchanged and PR #104 stays draft.
