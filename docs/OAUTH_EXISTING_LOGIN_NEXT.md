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
