# WorkOS OAuth for Panadan — production readiness and rollback

**State as of 2026-11-22:** IMPLEMENTED BEHIND DISABLED FEATURE SWITCH; **NOT PRODUCTION DEPLOYED**. Do not merge this draft PR or enable OAuth on `dan.panafor.com` until the go/no-go gates below pass. The production authentication boundary is still legacy MCP bearer tokens.

## Contract

The aim is: **enter MCP URL → OAuth discovery → automatic client identity (CIMD preferred; DCR fallback) → existing Panadan login → WorkOS consent → verified JWT → Panadan user and client permissions → read-only tools**.

- Existing Panadan usernames, password hashes, browser sessions, roles, REST routes, reporting store, and MCP tools are authoritative and unchanged.
- WorkOS handles authorization codes, PKCE, OAuth consent, JWT signing, JWKS and refresh token lifecycle. It is not a replacement for Panadan's account database.
- A signed OAuth JWT alone **cannot grant report access**. Panadan requires an active linked account and per-client delegated capabilities and fields; revocation and role changes are enforced locally per call.
- The WorkOS user email required by Standalone Connect must be **independently verified** and explicitly attested by a Panadan administrator. No guessed email aliases or automatic matching by email.

## Implemented on the feature branch

- `server/workos_standalone.py`: opt-in existing-login bridge. Validates WorkOS `external_auth_id` syntax, signs a short-lived HttpOnly cookie, preserves the flow across the **existing** `/login` page, performs a server-to-server WorkOS completion with a stable `panadan-user-{id}` subject, and strictly validates the redirect origin. No new login screen or password system.
- `server/main.py`: `/oauth/workos/login`, `/oauth/workos/continue` and two administrator-only contact-attestation routes. All disabled unless `PANADAN_WORKOS_STANDALONE_ENABLED=true`. CSRF origin checks apply to admin changes. No production `env` setting was changed by this PR.
- `server/security.py`: separate SQLite tables `oauth_verified_emails` (explicit admin attestation and evidence reference, not a users-table rewrite) and `mcp_client_requests` (client IDs observed **only after JWT verification**, never automatic grants). Existing permission updates revoke linked contact attestation, bindings and grants.
- `templates/oauth.html`: administrator-only verified-email enrollment and revocation.
- `templates/mcp_apps.html`: already verified OAuth clients appear as pending approvals. The user selects scopes/columns without copying a Client ID; all are denied by default.
- `server/mcp_tools.py`: published existing Panadan logo as MCP `serverInfo.icons`, plus correct product title and website. Icon display remains the MCP **client's decision** and ChatGPT may still request a separately uploaded plugin icon.
- WorkOS **Staging** branding now uses the existing Panadan `static/favicon.svg` for light/dark logo/icon/favicon. **WorkOS Production branding was not changed.**

## Current WorkOS account findings (verified via WorkOS MCP)

Staging issuer: `https://artistic-environment-06-staging.authkit.app`

The existing **pre-registered public OAuth client** with `panadan:mcp:read` has passed a real ChatGPT → WorkOS Staging → *synthetic-only* MCP authenticated `get_synthetic_access` call. This proves the protocol for an **already registered client**, NOT CIMD/DCR and NOT Panadan's existing login handoff.

WorkOS Staging currently has:
- `isAuthkitClientIdMetadataDocumentEnabled=false`
- `isAuthkitDynamicClientRegistrationEnabled=false`
- custom scope `panadan:mcp:read` exists, but `isDefaultDynamicRegistrationOauthScope=false`
- `externalLoginUri=null` (uses WorkOS-hosted login)
- isolated WorkOS synthetic-only MCP resource, not Panadan real data.

WorkOS Production in the connected account was **Inactive** with `canUseProduction=false`, `hasActiveBilling=false`. WorkOS documentation says Production requires billing information even when usage is free. Do not activate or deploy before production user verification and local security gates.

These CIMD/DCR toggles, default scope and external Login URI are **not exposed as editable WorkOS Management MCP operations** in the current connector. They must be configured in WorkOS Dashboard / support, and verified using discovery, MCP and issued tokens—not inferred from settings labels.

## Required WorkOS configuration (STAGING FIRST)

1. In **WorkOS → Connect → Configuration** enable **Client ID Metadata Document (CIMD)**; retain **Dynamic Client Registration (DCR)** only as a compatibility fallback. Verify both settings with WorkOS admin and public OAuth discovery: `client_id_metadata_document_supported=true` for CIMD and `registration_endpoint` for DCR when enabled.
2. Assign `panadan:mcp:read` to the default permission set for CIMD/DCR clients. WorkOS says custom scopes can require support-assisted configuration; do not try to pass `openid` alone, strip missing-scope checks, or weaken token verification. Confirm `isDefaultDynamicRegistrationOauthScope=true` and a real signed access JWT containing `panadan:mcp:read`.
3. Configure an **isolated, HTTPS Panadan staging backend** with the bridge enabled and a real Panadan test account whose email is independently verified and attested. Set that deployment as the WorkOS Staging **External Login URI**: `https://<your-staging-panadan-host>/oauth/workos/login`. Do **not** set Staging Login URI to the production `dan.panafor.com`.
4. Register `https://<your-staging-panadan-host>/mcp/` as the WorkOS **Staging OAuth protected resource**. The resource must match the JWT `aud` exactly. Preserve the working synthetic-only resource separately until the actual Panadan staging flow passes.
5. Use the *real* ChatGPT **automatic client identification flow** (no hand-entered client ID); test ChatGPT, another compatible MCP client, and normal consent. Preserve the existing manually registered client as rollback.

**Operational caveat:** WorkOS Standalone Connect `POST /authkit/oauth2/complete` creates/updates a WorkOS profile from `user.id` + `user.email` and can reject an email already associated with a different `external_id` in the same environment. The currently verified Staging account has previously signed in to WorkOS directly. Use a properly provisioned **distinct staging Panadan test account** or resolve its WorkOS external ID mapping explicitly and safely. Do not rewrite an existing profile's ownership or silently merge users.

## Environment contract for future isolated Panadan OAuth staging

```ini
PANADAN_AUTH_BACKEND=sqlite
PANADAN_MCP_AUTH_MODE=oauth
PANADAN_PUBLIC_ORIGIN=https://YOUR-PANADAN-STAGING-HOST
PANADAN_COOKIE_SECURE=true
PANADAN_OAUTH_ISSUER=https://artistic-environment-06-staging.authkit.app
PANADAN_OAUTH_JWKS_URL=https://artistic-environment-06-staging.authkit.app/oauth2/jwks
PANADAN_OAUTH_RESOURCE=https://YOUR-PANADAN-STAGING-HOST/mcp/
PANADAN_OAUTH_SCOPE=panadan:mcp:read
PANADAN_WORKOS_STANDALONE_ENABLED=true
WORKOS_API_KEY=<YOUR_STAGING_WORKOS_API_KEY>
PANADAN_WORKOS_PENDING_SECRET=<GENERATE_UNIQUE_RANDOM_SECRET_AT_LEAST_32_CHARS>
PANADAN_MCP_ALLOWED_HOSTS=YOUR-PANADAN-STAGING-HOST
PANADAN_MCP_ALLOWED_ORIGINS=https://YOUR-PANADAN-STAGING-HOST,https://chatgpt.com
```

Only values under the target environment's secure secret manager. No API secrets, user addresses, OAuth codes, tokens, private certificate keys, session cookies or passwords belong in Git, PR comments or ChatGPT messages.

In Production, the `PANADAN_PUBLIC_ORIGIN` and `PANADAN_OAUTH_RESOURCE` would use `https://dan.panafor.com` and `https://dan.panafor.com/mcp/`, respectively, *only after* Production WorkOS is activated and the Production issuer/JWKS is verified separately. Staging and Production keys, issuer, audience and account bindings must never be mixed.

## Release gates (all mandatory; currently incomplete)

- [ ] Code quality CI passes all tests, and the new OAuth module and templates have independent security review.
- [ ] Public discovery: PRM + issuer + RFC 9207 `iss` + PKCE S256 + JWKS + **CIMD** (or DCR) + custom-scope registration work end-to-end without manually entering client details.
- [ ] WorkOS Standalone Connect existing Panadan login completes for both signed-in and signed-out users; rejects expired/tampered pending cookie, wrong-domain redirect, unverified email, inactive user and mismatched existing identity.
- [ ] Verify access JWT `RS256`, exact signed `iss,aud,sub,client_id|azp,scope,iat,exp`; no opaque/unverified/id token is accepted.
- [ ] WorkOS consent plus separate **Panadan per-client capability/field consent** works from a pending signed client; no implicit grants, and immediate revocation/role reduction takes effect in local reports.
- [ ] `initialize`, `tools/list`, `tools/call` pass with one explicitly approved synthetic-only test user. Wrong client, unlinked subject, disabled user, missing field, wrong scope/audience and replayed/expired tokens fail closed.
- [ ] Observe read-only Odoo DB permissions and transcript redaction; restore/check production backup timers, test rollback and ensure existing API clients unaffected.
- [ ] Plan the **legacy MCP token migration**: switching `PANADAN_MCP_AUTH_MODE=oauth` rejects old `mcp:read` bearer tokens. Never switch silently or leave both modes enabled without review.
- [ ] WorkOS Production activated with billing, **separate production** branding, registered resource, external login URI, CIMD/default scope, correct production keys and secrets.
- [ ] Obtain explicit deployment approval after staging acceptance, then deploy to `dan.panafor.com` with monitoring, alerting, rollback and post-deploy checks.

## Rollback

**Source rollback:** revert the OAuth feature branch / draft PR to `main`. Stytch archive branches remain separate and preserved.

**Operational rollback:** restore `PANADAN_MCP_AUTH_MODE=legacy` and `PANADAN_WORKOS_STANDALONE_ENABLED=false` together through the existing production controller, after verifying legacy bearer token readiness and a reviewed restore plan. Rolling back code alone does not restore secrets, WorkOS Production settings, revocations, or prior WorkOS grants. Turn off WorkOS external Login URI and revoke authorizations separately after review. Do not roll out without working backups.

## Primary sources

- https://workos.com/docs/authkit/connect/standalone
- https://workos.com/docs/reference/workos-connect/standalone
- https://workos.com/docs/authkit/mcp
- https://workos.com/docs/authkit/connect/token-claims
- https://workos.com/docs/authkit/environments
- https://py.sdk.modelcontextprotocol.io/servers/media/
- https://developers.openai.com/plugins/build/auth

## Verified implementation checkpoint (2026-11-22)

The opt-in server-side handoff, existing login/session integration, admin attestation, pending client approvals, and MCP server brand metadata are committed to the feature branch. The WorkOS **Staging** logo/icon/favicon were read back and verified to match the existing Panadan SVG. **No user passwords, roles, production data, or production WorkOS settings were changed.**

**CI:** GitHub Actions workflow run `45115483815` completed **SUCCESS** on commit `eeef0170`: quality suite, platform integration and both web/VPN Docker builds green. Tests include mocked WorkOS Standalone completion, existing FastAPI login route handoff, signed cookie tampering and expiry, verified email requirement, origin/path allowlisting, and zero automatic client grants. This is *not* a successful standalone WorkOS **network** transaction for a real Panadan user.

**WorkOS actual API detail:** Completion endpoint is `POST https://api.workos.com/authkit/oauth2/complete`, but the **returned browser redirect** is on the issuer's `/oauth/authorize/complete?state=...` path, not `/oauth2/`. The implementation now pins the accepted continuation path to `/oauth/authorize/complete` and rejects unrelated paths. See https://workos.com/docs/reference/workos-connect/standalone .

**Standalone `sub` claim behavior:** WorkOS states that, with a configured Standalone Connect Login URI, it uses the **external ID** passed in completion (`panadan-user-{id}`) as the signed `sub` in the OAuth access token. The existing `oauth_identities` store binds that subject to the same signed-in Panadan user. This behavior must still be observed in a real staging token, not merely trusted from documentation. Source: https://workos.com/docs/authkit/connect/token-claims .

**Remaining user/admin actions:** Turn on CIMD (DCR optional) in **WorkOS Staging**, arrange `panadan:mcp:read` as an automatically registered client scope (support-assisted if unavailable), create a separately isolated **real Panadan staging deployment** with authenticated test account and verified email, and configure its WorkOS Staging external login URI. WorkOS Production activation/billing plus rollback/backup and independent security review are required before a production release. **Nothing is ready for promotion to `dan.panafor.com` yet.**
