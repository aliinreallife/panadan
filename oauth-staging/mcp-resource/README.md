# WorkOS OAuth staging-only MCP resource

This service exists **only** to prove the WorkOS OAuth -> ChatGPT -> MCP protocol.
It does not import Panadan's production database, accounts, report queries,
MCP tools, password/session infrastructure, or live credentials.

- Vercel project: `panadan-mcp-oauth-staging`
- GitHub branch: `feat/panadan-oauth-existing-login-20261121`
- Vercel root directory: `oauth-staging/mcp-resource`
- Canonical staging-only OAuth audience: `https://panadan-mcp-oauth-staging-git-feat-pan-f67052-ali121sniper-3106.vercel.app/mcp/`
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

## Verified WorkOS staging setup (2026-11-22)

- The WorkOS Staging environment has exactly one registered OAuth protected-resource URL: `https://panadan-mcp-oauth-staging-git-feat-pan-f67052-ali121sniper-3106.vercel.app/mcp/` (not the old Stytch-backed Vercel production alias).
- The staging account's existing, email-verified AuthKit end-user is the only approved pilot identity. The exact subject ID is stored in a **branch-scoped encrypted preview environment variable**, not in Git. It does not identify or authorize a production Panadan account.
- WorkOS public OAuth client has its matching custom scope `panadan:mcp:read` and ChatGPT stable redirect assigned.
- The GitHub-connected Vercel project uses this directory as its root. The synthetic-only ASGI app may be deployed on a preview URL, never as a live Panadan service.
- A Vercel preview deployment must be rebuilt *after* adding the branch-scoped user allowlist environment variable; older READY previews deliberately report `pilot_authorization: not-configured`.

**Not yet proven:** a successful user-interactive authorization-code + PKCE token exchange, actual WorkOS JWT audience/claims, or a ChatGPT synthetic tool call. Do not claim OAuth integration is complete until all pass.
