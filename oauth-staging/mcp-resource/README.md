# WorkOS OAuth staging-only MCP resource

This service exists **only** to prove the WorkOS OAuth -> ChatGPT -> MCP protocol.
It does not import Panadan's production database, accounts, report queries,
MCP tools, password/session infrastructure, or live credentials.

- Vercel project: `panadan-mcp-oauth-staging`
- GitHub branch: `feat/panadan-oauth-existing-login-20261121`
- Vercel root directory: `oauth-staging/mcp-resource`
- Canonical future OAuth audience: `https://panadan-mcp-oauth-staging.vercel.app/mcp/`
- WorkOS **Staging only** issuer: `https://artistic-environment-06-staging.authkit.app`
- WorkOS pre-registered **public** OAuth client: `client_01M8165V9W1G296975A3X3CACM`
- Required scope: `panadan:mcp:read`

## Safety gates

The MCP **tool call** requires a signed RS256 access token verified against
pinned WorkOS Staging JWKS, exact issuer, audience/resource, scope, expiry,
signed client ID, and **one explicitly approved staging user ID** in
`PANADAN_SANDBOX_WORKOS_SUB`. Without the env value, all data-bearing calls
fail closed. Unauthenticated requests return 401 with RFC 9728 challenge.
Only `initialize`, `tools/list`, `ping` and notification handshake
may be handled after a valid signed token but before user binding.

`/healthz` and both /.well-known/oauth-protected-resource routes are public
and contain **no user information**. No OAuth tokens, auth codes, or private
keys should ever be committed or logged.

This endpoint does **not** integrate Panadan's existing username login. The
initial token test can use the already-verified WorkOS Staging end-user; a
separate, reviewed Standalone Connect bridge would eventually reuse Panadan
login and per-user permissions. No live OAuth mode switch is authorized.

For WorkOS user tokens `sub` is a WorkOS user ID until an external login
integration explicitly sets a stable `external_id`. Never auto-bind based
on email or dashboard display name. WorkOS production must remain unchanged.

See `docs/OAUTH_EXISTING_LOGIN_NEXT.md` for the broader rollout gates.
