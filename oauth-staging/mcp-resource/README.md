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
