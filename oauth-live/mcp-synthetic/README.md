# Panadan Live synthetic MCP (isolated resource)

This app exercises verification of **Stytch Production/Live** access tokens
without connecting to Panadan, Odoo, the VPN, the real SQLite auth store,
or any customer reports. It is **not** a route to enable production OAuth.

Vercel project: `panadan-mcp-live-synthetic`, root directory:
`oauth-live/mcp-synthetic`. Canonical resource:
`https://panadan-mcp-live-synthetic.vercel.app/mcp/`.

## Required public deployment configuration

- `PANADAN_MCP_AUTH_MODE=oauth`
- `PANADAN_OAUTH_ISSUER=https://flame-calf-4073.customers.stytch.com`
- `PANADAN_OAUTH_JWKS_URL=https://flame-calf-4073.customers.stytch.com/.well-known/jwks.json`
- `PANADAN_OAUTH_RESOURCE=https://panadan-mcp-live-synthetic.vercel.app/mcp/`
- `PANADAN_OAUTH_SCOPE=panadan:mcp:read`
- `PANADAN_OAUTH_MAX_TOKEN_TTL=3600`

**No one is authorized by default.** After testing token issuance safely,
configure BOTH `PANADAN_LIVE_PILOT_CLIENT_ID` (exact *signed* JWT client ID)
and `PANADAN_LIVE_PILOT_SUBJECT_SHA256` (lowercase hex SHA-256 of the
immutable Stytch Live `sub`; calculate privately, never disclose raw
JWT, credentials, email, or subject). Do not treat a CIMD document URL or
ChatGPT connector ID as equivalent to the signed JWT client identity.

The Stytch Live authorization UI currently **rejects any explicit OAuth
resource other than** `https://dan.panafor.com/mcp/`. Do **not** weaken that
control, falsely claim full Live end-to-end ChatGPT acceptance, or reuse a
production-audience token on this distinct synthetic resource. A separate,
reviewed authorization request / audience policy and verification that Stytch
issues the exact synthetic JWT audience are prerequisites for an interactive
Live OAuth test. If Stytch cannot issue a token for this dedicated resource,
report the limitation rather than changing the verifier to accept a wrong
audience.

## Public smoke checks

- `GET /healthz` -> status ok; synthetic-only; pilot configured state
- `GET /.well-known/oauth-protected-resource` -> exact canonical resource,
  Live issuer, required scope
- `GET /.well-known/oauth-protected-resource/mcp` -> same metadata
- `POST /mcp/` without a valid Live JWT+explicit pilot binding -> 401,
  no tool discovery; `WWW-Authenticate` points to protected resource metadata
- `GET /openapi.json` -> 404 (API docs disabled)

Use an independently signed RS256 JWT fixture in offline tests to check
wrong issuer, audience, scope, client, member, expiry and token type are all
rejected. No secrets, tokens or user records should be written to logs.

Keep the original Stytch Test projects unchanged and leave
`dan.panafor.com` in its existing legacy mode until the independent
recovery and per-app grant gates are satisfied.
