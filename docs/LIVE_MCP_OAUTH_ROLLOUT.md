# Live Panadan MCP OAuth rollout — staging-to-production gate

**Status: opt-in implementation prepared; production OAuth is NOT enabled.**
Target: `https://dan.panafor.com/mcp/` (always HTTPS, never the
`http://` URL). The live `/healthz` returned 200 and OAuth protected
resource routes returned `404 "OAuth MCP is not enabled"` on 2026-11-17.

## Scope and security boundaries

- The isolated Stytch **Test** + synthetic MCP demonstration has completed
  ChatGPT tool discovery and `get_my_access` / synthetic call retrieval.
  That does **not** authorize using the Test tenant/issuer, consent, member
  bindings, ephemeral `/tmp` database or test tokens on real Panadan data.
- This PR adds `VerifiedOAuthDiscovery` to the real app, but **only** when
  `PANADAN_MCP_AUTH_MODE=oauth`. It permits `initialize`, `tools/list`,
  `notifications/initialized`, and `ping` for an already fully verified
  Stytch/OIDC access token. It never allows reporting `tools/call` to
  bypass the existing MCP bearer gate or tool-specific authorization.
- The production app's authenticated user identity is still the persistent
  SQLite Panadan account. Stytch's `iss + sub` must be explicitly linked
  by an administrator; a browser login or email address is not sufficient.
- The signed OAuth client identity (`client_id` or `azp`) is distinct
  from a CIMD metadata URL and from ChatGPT's connector/link IDs. User
  consent must refer to the **signed internal client ID**.
- The current controller `tools/prodctl-production.sh` and
  `tools/validate_production_compose.py` deliberately reject OAuth mode
  during routine releases. This PR does not relax that protection and
  does not deploy anything to the VPS.

## Release blockers before connecting real calls

1. **Backup and rollback:** prove a current consistent production SQLite
   online backup, independently verify the off-site encrypted copy by
   checksum and an isolated restore, and record an exact web-image rollback.
   Do not change Plane's Caddy network, TLS volumes, VPN or Odoo source role.
2. **Production IdP:** configure a separate Stytch **Live** Connected Apps
   B2B project/organization and authorized members, with production HTTPS
   sign-in/consent UI. Never reuse the Stytch Test issuer, test member,
   private keys or test client ID. Validate issuer discovery, JWKS, PKCE
   S256, CIMD, signing algorithm RS256 and token endpoint from Live metadata.
3. **Exact token contract:** require `aud` to include exactly
   `https://dan.panafor.com/mcp/` as an authorized resource,
   `scope` to include `panadan:mcp:read`, a signed `client_id` or
   `azp`, matching issuer and valid iat/exp with max 3600s TTL.
   Disallow unsigned/opaque/ID tokens. Do not accept Test audience in Live.
4. **Data authorization:** pilot only with an explicitly admin-approved,
   narrowly scoped real Panadan account and one reviewed ChatGPT client.
   Verify `/dashboard/oauth` binds the immutable Live subject to the
   correct existing user, then have that logged-in user approve its signed
   client ID at `/dashboard/mcp-apps`. Start with only `id` and `CALLDATE`,
   no transcript grant. Revoke and verify immediately.
5. **Row-level isolation remains unresolved.** An operator's manual filters
   are not row/tenant authorization. Do not onboard general staff or expose
   cross-operator customer call data before row/team restrictions and the
   customer-data disclosure policy receive independent review.
6. **Release controller:** a separate reviewed, explicitly acknowledged
   OAuth cutover path with topology validation and a tested rollback is
   required. The routine web release continues to reject OAuth. Existing
   legacy MCP tokens stop being accepted on cutover; notify owners and
   provide a rollback window. Do not silently enable both token types.

## Future Live .env.app (template ONLY; do not commit secrets)

These settings are illustrative. Apply only through a separately approved
maintenance rollout after the above checks, **never** by editing the active
VPS configuration as a shortcut.

```dotenv
PANADAN_COOKIE_SECURE=true
PANADAN_PUBLIC_ORIGIN=https://dan.panafor.com
PANADAN_AUTH_BACKEND=sqlite
PANADAN_AUTH_DB=/data/auth.sqlite
PANADAN_MCP_AUTH_MODE=oauth
PANADAN_OAUTH_ISSUER=https://<verified-stytch-live-issuer>
PANADAN_OAUTH_JWKS_URL=https://<verified-stytch-live-issuer>/.well-known/jwks.json
PANADAN_OAUTH_RESOURCE=https://dan.panafor.com/mcp/
PANADAN_OAUTH_SCOPE=panadan:mcp:read
PANADAN_OAUTH_MAX_TOKEN_TTL=3600
PANADAN_MCP_ALLOWED_HOSTS=dan.panafor.com,dan.panafor.com:443
PANADAN_MCP_ALLOWED_ORIGINS=https://dan.panafor.com
```

No `PANADAN_INTEGRATION_STAGING_*`, `PANADAN_STAGING_*`,
`PANADAN_AUTH_STAGING_*`, `PANADAN_AUTH_STAGING_DSN`, test issuer,
disposable signing key or development database belongs in Live.

## Read-only public checks

```bash
curl -fsS https://dan.panafor.com/healthz
curl -i --max-time 10 https://dan.panafor.com/.well-known/oauth-protected-resource
curl -i --max-time 10 https://dan.panafor.com/.well-known/oauth-protected-resource/mcp
curl -i --max-time 10 -H 'Accept: application/json, text/event-stream' \
  https://dan.panafor.com/mcp/
```

**Expected now (legacy):** health 200; both discovery routes 404;
unauthenticated MCP 401 with no OAuth resource metadata.

**Expected after separately approved Live cutover:** health 200;
both discovery routes 200, matching exact resource+Live issuer;
unauthenticated MCP 401 with a `WWW-Authenticate` Bearer challenge
pointing to resource metadata and scope. No token is printed.

## Post-cutover acceptance — one restricted pilot

- ChatGPT connects to a **new private Live connector**, not the working
  `test-pana` staging plugin. Its MCP URL must be
  `https://dan.panafor.com/mcp/`, its OAuth authorization/token endpoints
  must be discovered/approved for the Stytch Live project and its resource
  exact. Do not paste OAuth codes or tokens in chat.
- Tool discovery works with a valid JWT even before local app consent;
  unapproved `tools/call` is denied. After admin subject binding and
  user app-specific approval, `get_my_access` shows only the approved
  pilot fields; `list_recent_calls` returns only those fields.
- Negative tests: wrong issuer, wrong audience, wrong scope, unsigned or
  expired token, missing/changed client ID, disabled user, revoked subject,
  revoked client grant and transcript request all fail closed.
- Assert no unintended report fields, sensitive transcript or customer
  identifiers appear, and the reporting DB remains read-only.
- Monitor 401, 403, 5xx and MCP tool response integrity, and perform
  rollback to pre-cutover pinned image/config if acceptance fails.

## Operational limits

The live VPS has private, partly untracked Compose/Plane/Caddy overlays and
a VPS-local `prodctl.sh`. No production SSH, VPS Docker state, Stytch Live
admin connection or authoritative backup verification is available in this
ChatGPT conversation. A GitHub CI pass is **not** permission to perform
production OAuth cutover. Keep all real data on the existing authenticated
Panadan/SQLite/readonly-source boundary until these steps pass.
