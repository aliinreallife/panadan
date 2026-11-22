# Panadan -> ChatGPT: OAuth only, reuse Panadan login

**Decision:** 2026-11-21. **Status:** implementation direction, **not implemented or deployed**.

## The actual requirement

ChatGPT needs a standards-compliant OAuth authorization server. Panadan already has the user and permission system, including:

- `/login`, `panadan_session`, active users and session/CSRF checks.
- `mcp:use`, `calls:read`, `metrics:read` and scoped user-owned grants.
- `/dashboard/mcp-apps` user-managed client approvals (independent of OAuth protocol).
- `/mcp/` and its legacy bearer gate, plus optional resource-server `oauth` mode.
- Verification of signed OAuth access JWTs via `server/oauth_mcp.py` and local `(iss, sub)` account mapping.

Panadan **does not** yet mint OAuth authorization codes, manage OAuth client registration (CIMD/DCR), enforce PKCE, provide OAuth issuer metadata, issue access/refresh tokens or implement an OAuth authorization-server consent flow. Those are the only missing protocol features. Existing login cookies MUST NOT directly authenticate remote MCP calls.

**Non-goals:** rebuilding registration, login, account identity, permissions, reporting queries, MCP tools or introducing a replacement user database. Cloudflare Tunnel is not needed for Panadan's public HTTPS service. Do not rework the existing Stytch code; it is archived.

## Stytch is parked, not destroyed

The observed Stytch Live issuer-mismatch failure is documented in [the original decision record](MCP_OAUTH_DECISION_2026-11-21.md) and issue #57. No further Stytch debugging is required for this branch.

- [Live auth/consent UI snapshot](https://github.com/aliinreallife/panadan/tree/archive/stytch-live-auth-ui-20261121): `archive/stytch-live-auth-ui-20261121`
- [Live synthetic MCP snapshot](https://github.com/aliinreallife/panadan/tree/archive/stytch-live-mcp-synthetic-20261121): `archive/stytch-live-mcp-synthetic-20261121`
- Original staging branches and PRs #104, #107, #109 and #110 are retained.

These are **source snapshots**, not backups of Stytch dashboard projects, Vercel settings, domain routing or secret environment values. Keep those deployments/configuration intact separately if future rollback is desired. Do not commit secrets to Git.

## Minimum-dependency provider decision

We will not spend implementation effort on a provider solely because it advertises OAuth. The provider must support our *exact* ChatGPT login and MCP token contract.

| Candidate | Additional components | Compatibility concern | Current decision |
| --- | --- | --- | --- |
| WorkOS **Standalone Connect** | One managed OAuth service plus a small completion handler on Panadan's existing login | Check custom `panadan:mcp:read` scope with CIMD/DCR: WorkOS documentation says dynamically registered clients get only standard scopes by default, with custom scopes requiring support. Also verify signed JWT issuer/audience/client identity and pricing. | **First candidate to validate; not selected/deployed** |
| Cloudflare **Managed OAuth** | Access login + gateway to adapt its token and identity to Panadan | Not a drop-in for the RS256 access JWT verifier or Panadan's current user login. | Avoid unless requirements change |
| Cloudflare **Workers OAuth Provider** | Cloudflare Worker + KV and Panadan login/consent integration; possible new validation/proxy boundary | Worker-native token validation and deployment require an explicit design to secure the existing Python MCP resource server. | Fallback if managed bridge fails |
| Self-host OAuth authorization server inside Panadan (mature protocol library) | Server-side code, secure code/token persistence, signing keys and operational responsibility | No proven drop-in FastAPI authorization-server extension identified; must not hand-roll PKCE/CIMD/refresh/revocation. | Last resort |
| Stytch | Existing external user/authorization service | Confirmed RFC 9207 callback issuer mismatch | **Archived fallback only** |

Sources: https://workos.com/docs/authkit/connect/standalone ; https://workos.com/docs/authkit/connect/token-claims ; https://github.com/cloudflare/workers-oauth-provider ; https://developers.openai.com/plugins/build/auth .

## Start with a 0-deployment compatibility gate

1. Use `docs/MCP_CLIENTS.md` and `tools/check_mcp_oauth.py` as the existing acceptance/preflight definition; **do not rebuild** them.
2. For a candidate provider, verify that ChatGPT can identify/register itself through CIMD/DCR or a supported pre-registration, and that the provider supports PKCE S256, RFC 9207 issuer consistency, resource indicator `https://<staging>/mcp/`, and the approved `panadan:mcp:read` scope.
3. Verify a real signed access JWT has exact `iss`, `aud`, `sub`, `iat`, `exp`, `scope` and cryptographically verifiable `client_id` or `azp` compatible with `OAuthVerifier.verify_details()`. If not, identify the **smallest safe adapter change** before provider selection. A marketing claim is not a passing test.
4. **Only after passing these gates**, implement the Panadan login handoff in a staging-only feature branch: retain the signed-in Panadan account across the OAuth request, bind callback/transaction to a specific client and resource, perform per-client consent, and keep the Panadan authorization checks on every MCP request.
5. Test with a separate synthetic-only resource using a test account: wrong issuer/audience/client, expired token, missing scopes, denied/revoked consent, disabled Panadan user and transcript permission must fail closed. Test actual ChatGPT `initialize`, `tools/list`, `tools/call`.
6. Separate production approval and reversible rollout on `dan.panafor.com` only after these pass, with backups and rollback; never silently flip `PANADAN_MCP_AUTH_MODE` or break existing manual MCP tokens.

## Next actionable development step

**Prove the OAuth provider contract without coding or deploying a second user system.** WorkOS Standalone Connect appears aligned with Panadan's existing sessions but has a documented custom-scope/CIMD caveat; resolve that feasibility check before writing a WorkOS adapter. If the constraint is incompatible, evaluate Cloudflare Workers OAuth Provider specifically for a secure *external Python resource server*, not a Cloudflare-hosted demo. Then implement only the missing protocol glue on this feature branch.

The Stytch archives must remain untouched. Production must remain unchanged until explicit separately reviewed cutover.

## 2026-11-21 evidence update: use a pre-registered public client as first test

Verified docs:
- WorkOS supports **Public OAuth Applications** with mandatory PKCE: https://workos.com/docs/authkit/connect/oauth
- ChatGPT plugin config supports **pre-registered/provided** OAuth clients, including `tokenEndpointAuthMethod: none`: https://developers.openai.com/plugins/build/plugins
- WorkOS documents that **CIMD/DCR clients** only get the standard OIDC scopes by default; custom `panadan:mcp:read` needs support-assisted environment-wide defaults: https://workos.com/docs/authkit/connect/token-claims
- WorkOS Standalone Connect explicitly reuses external application sessions via an HTTPS Login URI receiving `external_auth_id` and a server-side completion call; it handles OAuth consent and token issuance: https://workos.com/docs/authkit/connect/standalone

**Lowest-friction next experiment:** use a **WorkOS staging environment**, make one **pre-registered Public OAuth Application** for ChatGPT, assign `panadan:mcp:read` if the WorkOS dashboard permits it, and use ChatGPT's **provided-client / none + PKCE** option. This may avoid the dynamic-client default-scope limitation without contacting support. Whether WorkOS permits assigning the precise custom scope to that public client and whether ChatGPT accepts its callback/issuer/token claims **have not yet been demonstrated**. If the assignment is unavailable or the trial fails, stop rather than weakening Panadan's verifier.

**User action only after this contract check:** create a **staging** WorkOS project/environment; share only public AuthKit issuer/domain and non-secret project identifiers. Never post the WorkOS secret API key or OAuth codes in a chat, PR, or log. No need to migrate Panadan's accounts or deploy anything to the VPS. WorkOS staging connections are documented as free (https://workos.com/docs/authkit/environments); verify service limits/charges in the account.

## 2026-11-22: verified WorkOS sandbox pilot

**WorkOS connected workspace:** existing project `mine's Project`, **Staging** sandbox environment `environment_01JX739KQ289Y3GRQP5CHTD5XB`. Production environment `environment_01JX739M6SZY9DVMDTYZM2GCMD` was **not changed**.

**Actions completed and independently read back through official WorkOS MCP:**
- Created sandbox **Public OAuth** app `Panadan ChatGPT OAuth Compatibility Pilot`, app ID `app_01M8165V9WE1NV4ZD0CDVFTKVQ`, public OAuth client ID `client_01M8165V9W1G296975A3X3CACM` (not a secret).
- Configured the stable ChatGPT redirect `https://chatgpt.com/connector_platform_oauth_redirect`; WorkOS dry run passed before saving. This redirect is appropriate **only if** actual WorkOS metadata and callback preserve RFC 9207 `iss` consistency (documented support, not yet exercised).
- Created exact sandbox permission `panadan:mcp:read` (ID `permission_01M8167BXSVRYTHJPCCGKJWTKF`) and assigned it to the OAuth app. Re-read app details: Public client, one redirect, one exact permission. **Important:** these are OAuth scope permissions in WorkOS only, not Panadan grants.
- Verified staging Connect applications and OAuth resources were initially empty. No resource URL, external login URI, WorkOS end users, or AuthKit replacement app was configured. No code exchange, access token or ChatGPT MCP connection yet.

**Critical new integration constraint:** Panadan's current `server/security.py` `users` table stores `id`, `username`, `password_hash`, grants, roles and activity status but **no email**. WorkOS Standalone Connect completion creates/updates an external WorkOS user with both `id` and `email` (https://workos.com/docs/reference/workos-connect/standalone). Do **not** invent email addresses, map usernames to emails, silently bulk-create users, or migrate Panadan login. A verified email-attribution plan or a different OAuth-only bridge is needed before implementing that handoff. The WorkOS sandbox app alone has zero bearing on live user access.

**Documented interoperability support:** WorkOS Connect's authorization metadata advertises RFC 9207 `authorization_response_iss_parameter_supported: true`; its auth callback documents an `iss` field (https://workos.com/docs/reference/workos-connect/authorize). ChatGPT requires an exact callback `iss` match and correct JWT `aud`, PKCE and OAuth scope (https://developers.openai.com/plugins/build/auth). These are **documented contracts**, not a passing end-to-end test.

**Next blocking steps:** determine whether WorkOS Standalone Connect can safely reuse Panadan's real verified user email **without adding a new identity/login system**; find a separate synthetic MCP resource URL and configure it as an allowed OAuth resource; verify exact issuer JWKS/token claims and end-to-end ChatGPT authorization; then only staging-code integration. If no viable identity/email binding exists, **stop WorkOS rather than add an unwanted identity migration**. Stytch archive branches remain untouched. Do not use `dan.panafor.com/mcp/` as the experimental audience.

## 2026-11-22: verified WorkOS public protocol and blocker

**Actual Staging issuer:** `https://artistic-environment-06-staging.authkit.app`. Public GET of both RFC 8414 and OIDC discovery returned 200 and a matching `issuer`, PKCE `S256`, `authorization_response_iss_parameter_supported: true`, authorization-code flow and token endpoint client method `none`. JWKS returned HTTP 200 with an RS256 RSA public signing key. **This does not verify any issued access JWT.**

**Scope caveat:** both metadata documents advertised `openid`, `profile`, `email` and `offline_access`, **not** `panadan:mcp:read`. But the *pre-registered* Public client in staging has the exact custom scope assigned, confirmed via WorkOS management. A no-credentials authorization request with PKCE and `panadan:mcp:read` progressed to the WorkOS hosted sign-in page, not an immediate scope rejection. **Token exchange and the actual signed `scope`, `aud`, `client_id` remain unverified.**

For this **pre-registered client only**, a **diagnostics-only opt-in** was added on this feature branch:
```bash
uv run --locked python -m tools.check_mcp_oauth --issuer https://artistic-environment-06-staging.authkit.app --allow-unadvertised-scope
```
It explicitly warns about missing public scope advertisement. It does not waive the strict scope/audience/signature checks in `server/oauth_mcp.py`, does not enable production OAuth, and is not allowed for CIMD/DCR or the full MCP resource check. The default preflight remains strict. New negative tests cover this distinction.

**Actual login blocker:** Staging WorkOS `externalLoginUri` is unset and authorization currently redirects to WorkOS's own hosted login. Standalone Connect requires `external_auth_id` and a stable external user ID **plus an email**. Panadan's current `users` table has username but no verified email. No WorkOS users have been created, and no Panadan user records have been migrated. The sandbox pilot is currently **first-party**; do not treat it as proven third-party consent.

**Staging deployment context:** Git-linked Vercel project `panadan-mcp-oauth-staging` exists, but docs-only branch pushes caused failed preview builds. This is a build configuration issue, not evidence of failed WorkOS OAuth. Do not alter production or resurrect Stytch components to fix it.

**Next required proof:** a distinct synthetic-only MCP resource, a real signed sandbox access JWT with exact audience/custom scope/client ID and a staging-only existing-login handoff using one explicitly verified test email. Until then, do not change live login/permissions/MCP.

References: https://workos.com/docs/authkit/connect/standalone ; https://workos.com/docs/reference/workos-connect/standalone ; https://workos.com/docs/authkit/connect/token-claims ; https://developers.openai.com/plugins/build/auth .
