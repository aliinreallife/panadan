# Isolated Panadan Stytch Test MCP resource

This independent FastAPI/MCP SDK app is for cryptographically verifying Stytch Test
access tokens and exercising synthetic MCP tools. It contains **no** customer data,
Panadan production database connection, Legacy bearer tokens, external proxy,
or Odoo code.

Canonical resource: `https://panadan-mcp-oauth-staging.vercel.app/mcp/`.

* Test issuer: `https://viridian-faucet-2753.customers.stytch.dev`
* JWKS: `https://viridian-faucet-2753.customers.stytch.dev/.well-known/jwks.json`
* Scope: `panadan:mcp:read`
* Signed client ID + explicitly pinned SHA-256 of Stytch Test `sub` both required.
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
