# MCP OAuth decision: preserve Stytch and take the minimum viable path

**Decision date:** 2026-11-21  
**Status:** Decision record / investigation; **not approved for production deployment**  
**Tracking:** [#57](https://github.com/aliinreallife/panadan/issues/57), [#58](https://github.com/aliinreallife/panadan/issues/58), [#23](https://github.com/aliinreallife/panadan/issues/23), [#64](https://github.com/aliinreallife/panadan/issues/64)

## Goal and hard constraints

Connect ChatGPT to the **existing** Panadan user identity, revocable grants, reporting permissions and read-only MCP tools with **the fewest new components**. Avoid introducing a second user/permissions database or an unnecessary hosting migration. **Keep all completed Stytch work** and use it if the provider resolves the specific interoperability issue.

- Do **not** change the production `https://dan.panafor.com/mcp/` mode, existing dashboard login, SQLite identity store, reporting DB, VPN, Plane/Caddy routing or real customer data for a provider experiment.
- Do **not** delete Stytch Test/Live projects, connected applications, Vercel synthetic deployment, branches or draft PRs.
- Do **not** bypass RFC 9207 issuer validation, accept unsigned/incompatible credentials, strip callback `iss`, disable real MCP authentication or use a public unauthenticated bridge to real reports.
- No Cloudflare Tunnel is required for the already-public Panadan HTTPS endpoint. Blender's local-device Tunnel is a separate use case.

## What Panadan already provides

The deployed application has users, authenticated dashboard sessions, capability-based permissions, revocable API/MCP bearer tokens, and reporting-side access checks. The optional `oauth` mode is a **resource server** with RS256/JWKS verification, fixed issuer/audience/scope and local `(issuer, subject)` account binding; it does **not** provide OAuth authorization-code + PKCE, consent, registration or refresh issuance. Dashboard cookies must not implicitly authorize MCP calls.

Relevant existing implementation/docs: `server/oauth_mcp.py`, `server/main.py`, `docs/MCP_CLIENTS.md`, `docs/MCP_SETUP.md`, `docs/SECURITY.md`. Existing plans for fine-grained field and team/row restrictions remain separate and are not assumed deployed; see `docs/UNIFIED_AUTHORIZATION_MCP.md` and `docs/OPERATOR_SCOPES.md`.

**Only missing integration layer:** a compatible OAuth authorization server/bridge that can connect a verified identity to a Panadan account and issue credentials ChatGPT can use. Adding this layer should not recreate Panadan's existing user system.

## Preserve current Stytch progress

- [#104](https://github.com/aliinreallife/panadan/pull/104), [#107](https://github.com/aliinreallife/panadan/pull/107): Stytch B2B consent/authorization UI work.
- [#109](https://github.com/aliinreallife/panadan/pull/109): isolated **Live synthetic-only** MCP resource and JWT/audience/client/subject gates. No real Panadan data.
- [#110](https://github.com/aliinreallife/panadan/pull/110): draft signed-out login-request recovery, not a fix for the issuer mismatch.
- Stytch **Test** discovery/tool calls were previously exercised; do not equate Test success with Live success.
- The **Live** ChatGPT authorization browser flow reached a callback with authorization `code` and `state`; Stytch session authentication returned HTTP 200. ChatGPT then failed issuer validation **before token exchange**:

| Field | Observed value |
| --- | --- |
| Stytch Live discovery `issuer` | `https://flame-calf-4073.customers.stytch.com` |
| Authorization redirect `iss` | `stytch.com/project-live-7cd47d4a-ef91-483f-b066-5668afb82325` |
| ChatGPT error | `OAuth authorization response issuer does not match the expected issuer` |

The issuer mismatch is specific evidence, **not** evidence that Panadan's local roles or JWT allowlist are wrong. Stytch support has been contacted; await a documented vendor fix or supported alternative. Never include full callback URLs, auth codes, state, tokens or cookies in issue comments.

## Options: make the replacement earn its complexity

| Path | What it adds | Fit / tradeoff | Decision |
| --- | --- | --- | --- |
| **Finish Stytch** | Existing separate Stytch B2B auth + OAuth | Lowest change if vendor makes callback `iss` match discovery; still a second identity layer | **First choice while awaiting fix** |
| **Cloudflare Access Managed OAuth** | Cloudflare Access login and managed MCP authorization | Existing Panadan RS256 access-JWT verifier cannot simply be pointed at an opaque token; may require gateway token/identity mapping | **Do not assume drop-in** |
| **Cloudflare Workers OAuth Provider** | OAuth protocol toolkit hosted on Workers | Can integrate Panadan login; we still own session/consent bridge, keys/token lifecycle, authorization and testing | **Self-hosted fallback candidate** |
| **WorkOS OAuth bridge** | Managed OAuth bridge potentially reusing existing Panadan login | Verify ChatGPT registration (CIMD/DCR), RFC 9207, resource/audience, JWT verification and price before commitment | **Managed fallback candidate** |
| **Build OAuth directly in Panadan** | Fully self-maintained authorization server | Greatest sensitive implementation burden; no need to rebuild user management | **Avoid unless other paths fail** |

Provider marketing claims are **not** proof of ChatGPT compatibility. A provider is viable only after an **end-to-end** isolated test with the actual ChatGPT plugin. Do not pay for or deploy a second provider before checking this matrix.

## Ordered next work (minimum necessary)

1. **Stytch fix path — zero deployment:** retain current settings; save sanitized `iss` mismatch evidence and support response in #57. If Stytch offers a supported fix, apply it first to the isolated Live synthetic flow and retry the same ChatGPT plugin.
2. **Prove only the missing step:** callback issuer equals discovery; then authorization-code/PKCE token exchange succeeds; inspect only sanitized claims for exact `iss`, `aud` (synthetic `/mcp/`), required scope, signed client ID, stable subject and expiry. Do not treat successful browser login as successful OAuth.
3. **Synthetic MCP smoke test:** ChatGPT `initialize` → `tools/list` → read-only `tools/call` using the approved Live subject/client. Test wrong issuer, audience, scope, revoked account, client, expired JWT and absent authorization. Preserve strict data isolation.
4. **Fallback decision gate:** only if the Stytch mismatch has no practical supported resolution, perform a **configuration/contract-only** evaluation of WorkOS bridge vs Cloudflare Workers OAuth Provider against Panadan's exact current verifier. Prefer the candidate requiring fewer code/auth changes. Pilot it against a **new isolated synthetic resource**, leaving Stytch intact.
5. **Production cutover: separate approval:** after successful real-client tests and security review, design signed account binding, per-app consent, existing user grant enforcement, revocation, audit, backups and rollback. Do not enable real data or flip `PANADAN_MCP_AUTH_MODE` as part of this decision record.

## Concrete acceptance gates before choosing any replacement

- HTTPS OAuth metadata with consistent issuer and RFC 9207 callback behavior (or standards-compliant supported equivalent).
- ChatGPT-compatible CIMD, DCR or actual supported pre-registration; PKCE S256.
- Resource indicator propagated into a **validated access token audience** or a reviewed equivalent architecture; compatible token signatures and key/validation rules.
- Trusted binding to an existing Panadan user, independently enforced current Panadan permissions and limited client grant; no new automatic privileges.
- End-to-end successful ChatGPT synthetic tool call **and negative tests**.
- No impact to live Panadan login, source database, prior MCP clients or Stytch rollback.

**Next actionable blocker:** Stytch support response or evidence from a supported Live callback-issuer fix. No provider migration has been authorized by this document.
