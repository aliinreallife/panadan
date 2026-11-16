# ChatGPT Stytch Test compatibility — private, synthetic only

This is the exact reproducible source of the private Panadan ChatGPT OAuth
Test plugin. It is **NOT** Stytch Management MCP or the real Panadan MCP.
The MCP endpoint is a dedicated Vercel staging project with **synthetic**
call 73104 and no customer, Odoo, production auth, or VPN connections.

## Connection under test

- MCP resource: `https://panadan-authz-integration-staging.vercel.app/mcp/`
- OAuth issuer (discovered): `https://viridian-faucet-2753.customers.stytch.dev`
- Authorization endpoint (Test-only compatibility UI):
  `https://panadan-stytch-oauth-staging.vercel.app/oauth/authorize-compat`
- Token endpoint: `https://viridian-faucet-2753.customers.stytch.dev/v1/oauth2/token`
- Client mode: **ChatGPT CIMD**; one canonical ID
  `https://chatgpt.com/oauth/client.json`, NOT the Inspector DCR Test ID
- Scopes: `openid panadan:mcp:read`; exact signed token audience must be
  `https://panadan-authz-integration-staging.vercel.app/mcp/`

The synthetic MCP fixture provisions a local grant ONLY if signed Stytch
Test JWT issuer, RS256 signature/JWKS, scope, audience, TTL and exact pinned
disposable Test member all validate, AND the signed client ID equals the
canonical ChatGPT CIMD URL or the existing approved Inspector DCR Test ID.
All other client IDs remain unapproved. Revocation is in-instance only:
the disposable /tmp SQLite state is NOT durable across Vercel workers.

## Safe test checklist

1. In ChatGPT Plugins, install this PRIVATE test plugin and connect it
   using Stytch **Test**, the same disposable Test member from Inspector.
   Never use real accounts or production Panadan.
2. Test the OAuth authorization response issuer matches the *discovered*
   Stytch Test issuer. No token, code, state, PKCE verifier, or session
   value should be shared in logs or screenshots.
3. After connecting, run `get_my_access`: only `id` and `CALLDATE`.
4. Run `list_recent_calls`: synthetic record `73104`, those two fields.
5. Run `get_call_metrics`: must be `permission_denied`.
6. If connection fails, collect only error **category**, stage
   (discovery, client registration, login, callback, token, MCP), HTTP
   status, and any sanitized issuer strings. Never paste tokens.

## Validation performed before human ChatGPT sign-in

- GitHub CI with locally signed RS256 test JWTs: exact ChatGPT CIMD
  signed client ID admitted for the pinned Test member; unknown,
  lookalike or callback-specific IDs get no reporting grant; local
  revocation does not impact Inspector and vice versa.
- Browser smoke with a fabricated, non-authenticating ChatGPT-shaped
  OAuth request: the authorization frontend accepted the new resource
  indicator and redirected to `/login` rather than invalid request.
- The dedicated Vercel staging MCP continued returning 200 on health and
  protected-resource metadata, while production-style REST/dashboard
  endpoints remained unavailable.

**No successful ChatGPT token exchange or MCP tool call is claimed yet.**
Production migration must stay blocked until ChatGPT itself completes
authorization and the permission matrix passes. PR #104 stays draft.
