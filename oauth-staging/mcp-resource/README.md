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

## Live test checkpoint — 2026-11-22

- WorkOS **Staging** OAuth resource was registered as the canonical **branch preview alias** above (resource ID `authkit_oauth_resource_01M839GVSH01Z71PM200EK7FSN`). Existing WorkOS Production was not modified.
- WorkOS Staging user with the already verified account email existed in the end-user store before this test; no duplicate user was created.
- Private ChatGPT plugin **Panadan OAuth Sandbox**, ID `plugins_6b03bcfe4dd481918524028df5c5f5d2`, release 0.1.0, created as PRIVATE personal plugin; manifest source saved in `oauth-staging/chatgpt-plugin/`. Install link: https://chatgpt.com/plugins/plugins_6b03bcfe4dd481918524028df5c5f5d2
- Branch-specific encrypted Vercel preview configuration `PANADAN_SANDBOX_WORKOS_SUB` is now set to the verified WorkOS Staging user's stable ID, not their email.
- Rebuilt preview reports HTTP **200** on `/healthz` with `data=synthetic-only` and `pilot_authorization=configured`.
- Both RFC 9728 resource-metadata routes return HTTP **200**, exact branch-preview resource URI, matching WorkOS staging issuer and required scope.
- Authless JSON-RPC `POST /mcp/` initialization returns HTTP **401**, with matching `WWW-Authenticate` realm, `resource_metadata`, and `scope`.
- The project's **canonical** `panadan-mcp-oauth-staging.vercel.app` alias still serves an older **Stytch test**. It was **not overwritten**; WorkOS uses the separate branch-preview alias.

**Pending interactive step:** Install/Connect the PRIVATE plugin in ChatGPT, sign in using the existing verified WorkOS *Staging* identity, and check whether WorkOS emits `iss`, signed `client_id`, exact `aud`, `scope`, `sub`, and `exp` that pass the untouched `OAuthVerifier`. Then attempt the only `get_synthetic_access` tool. No real Panadan data, accounts, database, DNS, API tokens, or production auth mode may be touched. Do not share OAuth callback codes or access/refresh tokens in chat.

## ChatGPT end-to-end OAuth success — 2026-11-22

The **user-installed** custom ChatGPT plugin `panadan-oauth-sandbox` (connected app ID `asdk_app_6b03c46c3c3081918da3c4be6425c494`) is callable through the ChatGPT plugin connector. Direct invocation of `mcp__Panadan_OAuth_Sandbox__get_synthetic_access({})` returned:

```json
{
  "environment": "workos-staging",
  "data": "synthetic-only",
  "authorized": true,
  "capabilities": ["synthetic:read"]
}
```

**PROVEN:** ChatGPT successfully authenticated and executed a real, read-only synthetic tool through the WorkOS Staging OAuth integration. The synthetic service's fail-closed gate calls the unchanged Panadan `OAuthVerifier.verify_details()`, requiring RSA-signed JWT, exact issuer/resource/audience/scope, valid expiry, signed client identity, and matching approved staging user subject. No credentials, tokens, user email, production records, or private data are included in the result.

**NOT PROVEN / NOT BUILT:** reuse of Panadan's existing username/password browser login through WorkOS Standalone Connect; production user-to-WorkOS binding or consent; production MCP rollout, real tool access, revocation checks and hardening. Keep the WorkOS-hosted staging sign-in distinct from Panadan login. Do not enable OAuth in `dan.panafor.com` or merge this staging-only code into production without separate review and test gates. Stytch archive branches remain available as fallback.
