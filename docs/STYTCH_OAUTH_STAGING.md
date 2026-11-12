# Stytch B2B Connected Apps — isolated Panadan OAuth staging

**Status:** Test-environment authorization-UI prototype. Not an approved OAuth cutover or proven remote ChatGPT integration.

The source is under [oauth-staging/stytch-nextjs](../oauth-staging/stytch-nextjs). This app is completely separate from the existing FastAPI/VPN/SQLite production Web container and DOES NOT proxy Panadan reports, change token validation, or connect to Odoo.

## Stytch Test prerequisites

- Existing B2B **Test** organization: panadan-oauth-test.
- Active test member with explicit \`panadan_mcp_tester\` role.
- RBAC resource \`panadan\`, action \`mcp_read\`, scope \`panadan:mcp:read\` mapped to the action, and tester role bound to this permission. Verify the saved records in Stytch.
- Connected Apps: DCR and CIMD enabled **in Test only**. No need to create a fake client ID.
- Frontend SDK: enable **View members** and **Email OTP** for Test, authorize \`http://localhost:3000\`.
- No production Stytch credentials, billing changes, or Panadan production environment modifications.

## Run locally (Node.js 24 recommended)

\`\`\`bash
cd oauth-staging/stytch-nextjs
cp .env.example .env.local
# Edit .env.local and set NEXT_PUBLIC_STYTCH_PUBLIC_TOKEN to your Test Public Token.
npm install
npm test
npm run typecheck
npm run dev
\`\`\`

Visit http://localhost:3000/login and authenticate the existing Stytch **Test** member via email OTP. Email login may need a redirect/configuration adjustment in Stytch depending on its actual member discovery configuration. Do not paste secret keys into the browser app.

With the app working locally, Stytch Connected Apps → Settings → Authorization URL should eventually point to the URL hosting \`/oauth/authorize\` on **its deployed HTTPS Test staging hostname**, *not* to \`https://dan.panafor.com/mcp/\`. A localhost URL can be used for browser-driven local tests if accepted by Stytch, but not by externally hosted ChatGPT/Claude clients.

## How the page works

- Uses official \`@stytch/nextjs/b2b\` **B2BIdentityProvider**, not a homemade token issuer.
- Validates basic authorization-request shape; Stytch is responsible for the real OAuth client, grant and consent checks.
- If the member has no active Stytch session, saves a **same-origin** authorization return path, redirects to /login, and resumes consent after email OTP.
- Requires OAuth code response, PKCE S256, and \`panadan:mcp:read\` scope.
- Does not accept arbitrary external return URLs or store tokens in the application.

Reference: https://github.com/stytchauth/stytch-b2b-nextjs-connectedapps-example and https://github.com/stytchauth/mcp-examples/tree/main/b2b-integrated/sprintplanner-frontend

## IMPORTANT: OAuth compatibility is still unproven

Before declaring end-to-end success, inspect real Test issuer metadata and **signed access-token** claims without exposing the token value:

1. Confirm RFC8414/OIDC discovery and actual HTTPS \`issuer\` + JWKS.
2. Verify \`alg=RS256\`, expected \`iss\`, immutable \`sub\`, \`iat\`, \`exp\`, required \`scope\`, and signed \`client_id\` or \`azp\`.
3. **Critical:** Panadan's \`server/oauth_mcp.py\` currently requires \`aud\` to match the *exact MCP resource URL* (ending \`/mcp/\`); Stytch defaults may instead use a project identifier. Do not change audiences blindly or bypass verification.
4. Verify RFC8707 resource handling, protected-resource metadata and 401 challenge, successful login/consent/callback/refresh, and revoked-user/client failure.
5. Use disposable staging accounts and an independently deployed HTTPS **staging MCP** resource. Do NOT flip \`PANADAN_MCP_AUTH_MODE=oauth\` on the live \`dan.panafor.com\` Web service while experimenting.
6. Run \`python3 tools/check_mcp_oauth.py --issuer https://YOUR_TEST_ISSUER\` for a public metadata preflight. This does NOT validate user consent or actual token JWT claims.

## Deployment and operations

This app has **no production route**, no compose overlay, no Odoo access, no API keys, no database migrations and no automatic deployment from CI. If deployed, use a dedicated staging hostname and set its exact origin in Stytch Frontend SDK authorized domains. Configure the same exact staging authorization URL in Stytch Connected Apps. Keep source and staging secrets isolated from production.

CI may compile this app, but a successful compilation alone does not prove Stytch browser login or remote ChatGPT/Claude OAuth compatibility.

## Follow-up acceptance

- Stytch test member can sign in via Email OTP.
- Real Connected Apps authorization URL renders consent for a valid PKCE request.
- Browser redirects with authorization code to the registered client.
- Stytch access JWT meets Panadan's verifier contract (or documented migration required).
- Independent staging MCP resource accepts valid authorized user and rejects revoked/wrong user/audience/client.
- ChatGPT, Claude and MCP Inspector independently complete OAuth connection, renewal and revocation tests.

## Check actual Stytch member login in the browser

After entering the email OTP, open `http://localhost:3000/` in the **same browser origin** used to sign in. The app now shows either **Stytch Test member signed in** or **Not signed in**, based on the real `useStytchMemberSession` state. Next.js `GET /login 200` only proves page loading, not successful authentication. Avoid alternating `localhost` and `127.0.0.1`: browser sessions/cookies are origin-sensitive. A signed-in state proves the Test browser member session, **not** OAuth code issuance or Panadan MCP token acceptance.

A repeated `GET /sw.js 404` is generally an optional browser service worker probe; unrelated to the Stytch authentication state. The Next.js workspace-root multiple-lockfiles warning is non-blocking.

## Recovering from a Next.js `undefined.call` module error

If `HomePage` crashes with `Cannot read properties of undefined (reading 'call')` after a hot reload, stop the local dev server and remove the **generated** cache only:

```bash
cd ~/panadan-stytch-staging
# Pull the latest PR branch; Git should be clean for tracked files.
git pull --ff-only
cd oauth-staging/stytch-nextjs
rm -rf .next
npm run dev
```

Open the same hostname used for OTP (`localhost` or `127.0.0.1`) and force-refresh once. This does not delete `.env.local`, npm dependencies, or Stytch Test sessions. The home page uses a single client-component boundary for the session hook to avoid a separate server-to-client module reference.


## Development bundler and browser runtime regression

The isolated staging app now uses Next.js 15 Turbopack for `npm run dev`, bypassing the Webpack module-loading path that repeatedly crashed on `/`. Its Turbopack project root is explicitly pinned to the staging app. Production builds remain on the existing `next build` path.

For a clean local restart, stop the server and run:

```bash
cd ~/panadan-stytch-staging
git pull --ff-only
cd oauth-staging/stytch-nextjs
rm -rf .next
npm run dev
```

Try a private browser window on the same hostname used for OTP to exclude a stale service worker from another localhost app. CI runs headless Chromium against the *development server* with a syntactically valid nonproduction dummy Test public token and checks for client-side module-loader crashes on `/` and `/login`; it does not prove actual Stytch member login or the OAuth grant.


## Local Connected Apps PKCE consent test

Stytch Test member sign-in is confirmed in the browser. To test OAuth separately from MCP:

1. In Stytch **Test → Connected Apps → Settings**, set Authorization URL to `http://127.0.0.1:3000/oauth/authorize` for a browser currently on 127.0.0.1; if using localhost, use `http://localhost:3000/oauth/authorize`. Both must point to the same origin as the authenticated browser session. Stytch's example uses localhost.
2. In **Test → Connected Apps → Clients**, create a client named `Panadan Local PKCE Test` with type `Third Party Public`; register exact callback URI `http://127.0.0.1:3000/oauth/test-callback` (or localhost form matching your browser); allow the `panadan:mcp:read` scope. No confidential client secret is needed. Do not create in Live.
3. Go to `/oauth/test-client`, paste its public Client ID, and click `Start Authorization Code + PKCE`.
4. If Stytch displays consent, approve only the intended Panadan MCP read scope. The client then returns to `/oauth/test-callback` and checks that the authorization code and random `state` match its short-lived browser transaction.

This smoke test does NOT exchange codes for tokens or prove secure JWT validation. Token exchange, RS256 verification, exact `aud` equal to the *staging* MCP resource, issuer/JWKS discovery, signed client identity, authorization scope and expiry, and the real ChatGPT/Claude connection must be implemented/tested separately. The authorization code is not displayed or stored after callback.


## Exchange the OAuth code once, without displaying credentials

The local callback now retains the *validated* short-lived code and PKCE verifier only in the browser's component memory, removes code/query parameters from the visible URL, and provides **Exchange code once & inspect access token**.

Stytch's official Next.js Connected Apps example exchanges with the Test public endpoint:
`POST https://test.stytch.com/v1/public/{STYTCH_TEST_PROJECT_ID}/oauth2/token` using `grant_type=authorization_code`, `client_id`, `redirect_uri`, `code`, `code_verifier`. The isolated API proxy accepts only same-origin local Test clients and returns **sanitized metadata**, never raw access/refresh tokens.

Before starting a **fresh** authorization, append this to your existing local `.env.local` (preserve your configured public token):

```dotenv
STYTCH_TEST_PROJECT_ID=project-test-5ce2a5ad-c6a8-4177-a6a4-a918c7add228
```

This public Test Project ID was observed in the callback issuer parameter. Verify it against your Stytch **Test → Project Overview** before use. Restart Next.js to load the server-only environment setting, then return to `/oauth/test-client` and perform a **new** authorization. Previous codes were deliberately discarded and cannot be exchanged.

The results show `alg`, `iss`, `aud`, scope, client identity, timestamps and token format, but the JWT is only **decoded**, not signature-verified. Compare it with Panadan's strict `server/oauth_mcp.py` requirements; never treat decoded claims as authorization. In particular, Panadan requires an HTTPS issuer, exact staging resource `aud`, RS256, signed client identity, and `panadan:mcp:read`. No production OAuth cutover occurs here.

To avoid leaking authorization codes in the dev terminal, `next.config.ts` turns off incoming-request logging and adds a no-referrer policy for the callback. Other web-server reverse proxies, browser history, observability systems, and network tools may still see the initial OAuth callback request; never share those values.


## Local token inspector origin guard (WSL / Next.js)

If the local token inspection displayed `This diagnostic endpoint is restricted to the local test origin`, the Next.js runtime was comparing its internally normalized `request.nextUrl.origin` to the browser Origin. On Windows-to-WSL localhost forwarding these can differ. The inspector now permits **only** `http://127.0.0.1:3000` or `http://localhost:3000` and validates that the HTTP `Host` matches the submitted browser `Origin`, rather than trusting an internally rewritten request URL. The exact callback redirect must also match that browser origin. Browser CI tests exercise the accepted same-origin request and a blocked hostile origin.

**Any previously rejected callback has already discarded its one-time authorization code in the test UI.** Start a new flow from `/oauth/test-client` and approve consent again before clicking **Exchange code once & inspect access token**. Never send codes, PKCE verifiers or access tokens in chat.


## Diagnose token exchange HTTP 403 without leaking credentials

A successful Stytch authorization code plus matching state proves the front-channel consent step, **not** token issuance. If exchanging that code returns 403, the staging inspector now exposes only safe diagnostic identifiers: `provider_http_status`, `provider_error_type`, `oauth_error`, `provider_request_id`, and whether the upstream response was JSON or non-JSON. The provider's raw response, `error_message`, token strings, authorization codes, and PKCE verifiers are not displayed or logged.

- A structured Stytch `provider_error_type` and `provider_request_id` should help isolate the actual rejection and can be used in a Stytch support ticket.
- A non-JSON response with 403 may indicate an upstream network/proxy response rather than a structured Stytch rejection; investigate WSL proxy settings if so.
- The client configuration remains Test-only; no role, audience, token TTL or credential changes should be made until the error type is known.
- Authorization codes are one-time: after pulling this change, start a **new** PKCE authorization/consent flow before using the inspector.


## Project-domain Connected Apps token endpoint (2026 update)

The earlier staging token exchange used the shared public/M2M URL `https://test.stytch.com/v1/public/{PROJECT_ID}/oauth2/token`. For Stytch B2B Connected Apps, obtain the actual OAuth token endpoint from your Test Project Domain's `/.well-known/oauth-authorization-server` metadata instead. The expected project-domain token endpoint is `/v1/oauth2/token`.

In Stytch **Test → Project Overview → Project ID & API Keys**, locate **Project Domain** (usually shaped like `https://unique-name.customers.stytch.dev`). Copy the full HTTPS issuer into your local `.env.local`:

```dotenv
STYTCH_TEST_ISSUER_URL=https://YOUR-TEST-PROJECT.customers.stytch.dev
```

Keep the previously configured Public Token and Test Project ID. Do not use the shared `test.stytch.com` API host or a Live domain. No secret key is required. Restart Next.js and start a **fresh** authorization from `/oauth/test-client`.

The local inspector now fetches the discovered metadata, verifies the `issuer` exactly matches the configured trusted Test domain, and only exchanges codes at `https://same-issuer/v1/oauth2/token`; it does not follow discovery redirects or accept client-controlled token URLs. This prevents mistakenly exchanging PKCE codes at an unrelated or legacy endpoint. The project domain is a configuration value, not a token or private key.

If discovery fails, report the exact sanitized error. If discovery succeeds but exchange remains 403, inspect the sanitized provider identifiers and network path. A non-JSON 403 alone does not prove a proxy problem.


## Independent HTTPS MCP staging resource (2026-11-11)

The second, isolated staging-only Vercel project is available at
`https://panadan-mcp-oauth-staging.vercel.app`, with a canonical MCP resource
`https://panadan-mcp-oauth-staging.vercel.app/mcp/`. The app source lives in
`oauth-staging/mcp-resource/` and is served as FastAPI with MCP SDK v2.
It has **no** Panadan reporting code, Odoo, production VPN, database or legacy
bearer-token credential. Only a synthetic access tool is installed.

The staging app requires all of the following simultaneously:

- A real RS256-verified access JWT from the pinned Stytch **Test** issuer/JWKS.
- `aud` containing the canonical staging MCP URL, exact scope
  `panadan:mcp:read`, valid timestamps, and a signed OAuth client identity.
- An explicitly permitted Test client ID and SHA-256 hash of the disposable
  Test member's signed `sub` claim. By default the subject hash environment
  setting is all zeros, which deliberately denies all member access.

The Test authorization UI's sanitized token inspector returns `sub_sha256`
so an operator can configure that binding without ever copying a raw token or
OAuth authorization code. This hash is a persistent pseudonymous identifier
and should be handled as Test-only access metadata.

**Vercel MCP project**: `panadan-mcp-oauth-staging` in the Personal account,
root directory `oauth-staging/mcp-resource`. The Stytch authorization UI
remains a separate Vercel project and the original Panadan production
deployment stays unchanged.

**Stytch Test follow-up (not yet complete)**: modify only the existing
disposable Third Party Public Connected App's `access_token_custom_audience`
to `https://panadan-mcp-oauth-staging.vercel.app/mcp/`; obtain a fresh access
JWT and confirm the resource appears in its signed `aud` claim. A per-client
custom audience is not proof that Stytch enforces RFC8707 resource indicators
for dynamically registered ChatGPT/Claude clients. Test that separately.

Read-only preflight:
```bash
uv run --locked python tools/check_mcp_oauth.py \
  https://panadan-mcp-oauth-staging.vercel.app/mcp/
```

No production OAuth cutover is approved. Keep the PR in draft until live,
negative-case and real-client interoperability gates pass.

## Real Stytch Test token → synthetic MCP acceptance (2026-11-11)

**Observed by test operator through the hosted, sanitized callback:**
`Live staging MCP verification: Accepted: Stytch JWT verified and synthetic MCP tool executed. HTTP status: 200.`

The callback's `probe_mcp=true` path exchanges a fresh Authorization Code + PKCE
code at the trusted Stytch **Test** project-domain token endpoint, forwards the
access token only server-to-server to the fixed staging MCP URL, and returns
only a sanitized result. It does not display, log, or persist bearer tokens.

The Test-issued token's decoded (not independently trustworthy) metadata
reported RS256, 60-minute TTL, required `panadan:mcp:read` scope, a signed
Test Connected App client identifier, and an audience array containing both
the Stytch Test Project ID and the **exact**
`https://panadan-mcp-oauth-staging.vercel.app/mcp/` resource URL.
Panadan's staging MCP resource independently verifies RS256 signature using
the pinned Stytch Test JWKS and enforces issuer, audience, scope, timestamp,
signed client identity, and the explicitly configured Test-member binding.
The positive result also required the expected synthetic tool response:
a bare HTTP 200 without that output is not counted as acceptance.

**What this establishes:** One approved disposable Stytch Test member using
one explicitly registered Test client can successfully authorize and invoke
the synthetic MCP staging tool via the real issuer and resource server.
**What it does not establish:** RFC 8707 `resource` handling and
dynamic per-resource audiences for CIMD/DCR clients; OAuth refresh;
revocation effectiveness for already-issued access tokens; key rotation;
production Panadan account mapping and field-level policy; or interoperability
with ChatGPT, Claude, and a generic MCP inspector. The hosted client is a
diagnostic only, not production OAuth client integration.

**Required next negative/live gates before any cutover:**

1. Confirm missing token and malformed token receive `401` with the exact
   protected-resource metadata challenge in a real deployed request.
2. Revoke the disposable Test-member binding on the **isolated** staging MCP,
   confirm freshly issued tokens are denied, then restore the binding.
   A binding revoke does not imply revoking already-issued JWTs at Stytch.
3. Test wrong user, wrong client, wrong `aud`, wrong `scope`, expired token,
   and missing/bad signatures against the deployed staging verifier.
   Offline synthetic negative-case tests already exist.
4. Probe RFC 8707 resource parameter in authorization and token requests and
   verify actual token audiences for independent dynamically registered clients.
5. Test client reconnection/renewal, consent removal, key rotation and
   interoperability with actual MCP clients.
6. Review the production account-binding and consent contract independently.
   **Keep Panadan production on legacy bearer mode and this PR in draft.**


## Live staging member binding revocation and recovery (2026-11-11)

**PASS — reported via operator's sanitized hosted OAuth callback and staged
Vercel deployment verification.** This test was limited to the isolated Vercel
project `panadan-mcp-oauth-staging`; Stytch Live, Panadan production, and the
separate OAuth frontend project were not modified.

| Phase | Staging member binding | Browser's real Stytch Test JWT → synthetic MCP |
| --- | --- | --- |
| Baseline | Approved disposable member hash | `200` — signed JWT verified and synthetic tool executed |
| Revoked | Temporarily replaced only `PANADAN_STAGING_SUBJECT_SHA256` with 64 zeroes; redeployed | `401` — valid Stytch login/token exchange, but MCP authorization denied |
| Restored | Original approved hash restored as an encrypted env value; redeployed | `200` — signed JWT verified and synthetic tool executed |

The restored Vercel MCP deployment is `dpl_E7XgKWpQVD4vm8twj4EKATgPMbau`
(`READY`, staging source commit `3413abc`); the stable
`https://panadan-mcp-oauth-staging.vercel.app` alias points to the restored
deployment. Health and protected-resource metadata both returned HTTP 200.
The Test-only `PANADAN_STAGING_CLIENT_ID` and canonical `/mcp/` resource
audience remained unchanged.

The final recovered access token's **decoded** metadata included the fixed
Stytch Test issuer, `panadan:mcp:read` scope, 60-minute TTL, Test client ID,
and both the Stytch Project ID and the canonical staging MCP URL in its `aud`
array. Crucially, the live probe independently required the exact expected
synthetic MCP tool result; the callback reported
`Accepted: Stytch JWT verified and synthetic MCP tool executed` (HTTP 200).

**Scope and limitation:** This is **local MCP member-binding revocation**,
not Stytch Test token or session revocation. It does not prove immediate
invalidity of already-issued JWTs, nor the behavior of DCR/CIMD-registered
clients. Tests for dynamic clients, RFC 8707 resource selection, JWT expiry,
key rotation, and token renewal remain open. No production cutover is approved.


## MCP Inspector RFC 9207 authorization-response issuer mismatch (2026-11-11)

**Status: BLOCKED at OAuth authorization callback (before token exchange).**

A real MCP Inspector Streamable HTTP attempt to
`https://panadan-mcp-oauth-staging.vercel.app/mcp/` reached the authorization
callback but Inspector rejected it with:

```text
Issuer mismatch in authorization response (RFC 9207):
expected: https://viridian-faucet-2753.customers.stytch.dev
received: stytch.com/project-test-5ce2a5ad-c6a8-4177-a6a4-a918c7add228
```

This is **not** a failure in the MCP resource's RS256 JWT verifier. The
initial unauthenticated HTTP 401 is the expected protected-resource challenge.
Inspector is correctly refusing to proceed with a mismatching
authorization-response `iss`; no live Inspector access token/tool call is
confirmed. Panadan currently renders Stytch's `B2BIdentityProvider` on
`/oauth/authorize`; the provider/SDK handles the redirect to the OAuth client.

RFC 9207 requires an authorization-response `iss` (when present) to match
the authorization server metadata `issuer` exactly, using a canonical HTTPS
issuer identifier. The reported `stytch.com/project-test-...` value is not a
canonical HTTPS URL and does not match our configured Test issuer. A separate
public Descript MCP report documents the same Stytch-backed mismatch with
Claude Code (descriptinc/descript-mcp issue #12), suggesting provider- or
SDK-originated interoperability behavior. This is not proof of the precise
originating component until a sanitized Stytch authorize response is examined.

**Next steps (Test only):**

1. Ask Stytch support to explain and fix the authorization-response `iss`
   mismatch with the discovered Test Project Domain issuer, preferably by
   issuing the canonical HTTPS `iss` in every response when advertising
   RFC 9207 support. Include Test Project ID, issuer, reproduction details,
   and redacted screenshot; never include tokens, codes or PKCE verifiers.
2. Check actual Test AS metadata's
   `authorization_response_iss_parameter_supported` and the Stytch SDK's
   behavior. Our prior custom PKCE diagnostic validated state and resource
   access token but **did not check the RFC 9207 authorization-response `iss`**;
   that positive test cannot establish strict third-party client compatibility.
3. Do not disable Inspector issuer checking, rewrite untrusted `iss` values,
   or publish `stytch.com/project-test-...` as the OAuth issuer.
4. Once corrected, repeat Inspector authentication. Expect a separate
   explicit-approval step for Inspector's own dynamically issued client ID
   and resource-specific audience; the synthetic staging MCP currently pins
   a single disposable Test Connected App.
5. Keep the Panadan production legacy bearer mode and PR #104 draft.


## Live MCP Inspector compatibility and synthetic tool execution — PASS (2026-11-12)

**PASS — user-observed real MCP Inspector connection and tool call; Test-only synthetic resource.**
This result supersedes the earlier `BLOCKED` status in the RFC 9207
investigation above for the current staging configuration. The older failure
and its reproduction remain documented for regression tracking.

**Observed through MCP Inspector screenshots:**

- `panadan-mcp-oauth-staging` displayed **Connected** using **HTTP /
  Streamable HTTP**, negotiated **MCP 2025-11-25 (Legacy)**.
- `tools/list`, `prompts/list`, `resources/list`, and
  `resources/templates/list` showed **OK**.
- The **Tools** tab listed exactly one synthetic tool:
  `get_staging_access` (Synthetic staging access).
- Executing `tools/call get_staging_access` showed **OK** and returned
  the expected synthetic-only payload:

  ```json
  {
    "environment": "stytch-test",
    "data": "synthetic-only",
    "actor": "authorized-test-member",
    "capabilities": ["mcp:staging:read"]
  }
  ```

**Relevant compatibility fix:** The original Stytch Test frontend path
`/oauth/authorize` previously still rendered the Stytch
`B2BIdentityProvider` widget and issued a legacy
`iss=stytch.com/project-test-...` authorization response, which strict
RFC 9207 clients reject. In the isolated staging Next.js project,
`/oauth/authorize` now preserves the request and navigates to
`/oauth/authorize-compat`, where the Test-only headless Stytch consent
flow requires the exact configured Test issuer/client/callback constraints
and canonicalizes only the known Stytch Test issuer mismatch. The new
authorization frontend was deployed and verified on the staging alias.
Clients must continue validating issuer, state and PKCE; never disable
issuer verification.

**What is now established:** An independent MCP Inspector instance can
complete authorization, connect to the **isolated** synthetic staging MCP,
discover its tool and execute an authorized real `tools/call` successfully.
No production customer data or Odoo service was involved.

**What is NOT established:** Arbitrary dynamically registered CIMD/DCR
clients, refresh and logout semantics, immediate upstream token revocation,
key rotation, production account mapping or field-level authorization, or
compatibility with ChatGPT and Claude MCP clients. The live Inspector test
was performed with an explicitly configured Test Connected App, not proof
of hands-off dynamic client registration. The isolated Test-only issuer
compatibility shim still requires a provider-level correction or separate
security review before any production adoption.

**Disposition:** Mark **manual independent MCP Inspector interoperability
(Test-only)** as PASS. Keep PR #104 draft and Panadan production on legacy
bearer authentication. Plan separate dynamic-client and production
integration security gates.


## Dynamic client onboarding: Test-only policy and remaining audience gate (2026-11-12)

**Configuration observed in Stytch Test dashboard:** Both **CIMD** and
**Dynamic Client Registration** are already enabled. An MCP Inspector
third-party public client with creation method **DCR** was visible in
Connected Apps alongside the manually registered Panadan Local PKCE Test
client. This proves at least one dynamic client was registered; it does
**not** establish that the successful Inspector `get_staging_access` call
used that DCR client, nor that CIMD has been exercised.

**Implemented, with default fail-closed:** The isolated
`oauth-staging/mcp-resource` now accepts
`PANADAN_STAGING_CLIENT_MODE` values:

- `pinned` (default) — original exact internal Stytch Test client ID
  and exact approved Test-member SHA-256 subject binding.
- `any-test-client` — *only in this synthetic-only Test resource*,
  after full RS256 JWT verification against a pinned issuer/JWKS,
  exact canonical resource `aud`, exact scope, lifetime, and valid
  signed `connected-app-test-UUID` client ID, allow that same
  approved Test member to use another dynamically registered client.
  A missing client ID, invalid mode, wrong issuer/audience/scope,
  Live client ID or wrong Test member still denies access.

This experiment is deliberately **not a production client trust policy**.
Stytch DCR clients self-identify and must not be silently considered
trusted by actual Panadan tools. Resource access here is only to the
static, synthetic `get_staging_access` response. Production legacy
bearer paths and production databases are unaffected.

**Unresolved mandatory real-world gate:** The manually registered client
has a configured **custom JWT audience** for the synthetic MCP resource.
Stytch's public client API exposes a per-client
`access_token_custom_audience` setting, but that does not prove
that an arbitrary CIMD or DCR-created client receives the same value.
MCP OAuth requires clients to send the RFC 8707 `resource`
parameter at both authorization and token exchange. The resource
MUST retain exact `aud=https://panadan-mcp-oauth-staging.vercel.app/mcp/`
validation. Tokens containing only the Stytch Project ID MUST fail
until proper issuer-side resource binding is established.

**Next manual smoke after deployment:** In MCP Inspector, create or
reset a separate **Test** server connection, leaving **Client ID
empty** so Inspector dynamically identifies/registers itself; keep
OAuth scope `openid panadan:mcp:read`. Confirm authorization page
uses `/oauth/authorize-compat`, and check `Connection Info` for
CIMD metadata URL vs DCR registration. Attempt `get_staging_access`.
Only the expected synthetic tool response establishes success. No
tokens or PKCE secrets should be copied into logs or ChatGPT.


## Dynamic test-client smoke deployment (2026-11-12)

**Deployed to the isolated synthetic MCP staging Vercel project only:**
`panadan-mcp-oauth-staging`
(`prj_wMA2HK5oXsAxuKRstsvVFCLf1vMc`, Vercel stable alias
`https://panadan-mcp-oauth-staging.vercel.app`).

- Deployment: `dpl_7kuFDPT8dQVzUi212WioxioPdQnJ` — **READY**
- Source commit: `2f32bda528906568834f789f844739560bda9e75`
- Only in this synthetic-only staging project's Vercel production **deployment
  target**: `PANADAN_STAGING_CLIENT_MODE=any-test-client`.
  This does *not* mean the real Panadan production service was changed.
- Existing encrypted, approved Test subject hash binding and Test client
  fallback configuration left intact.
- Independent `GET /healthz` returned 200 and
  `GET /.well-known/oauth-protected-resource` returned 200 with the canonical
  `/mcp/` resource and trusted Stytch Test issuer.
- Independent unauthenticated `POST /mcp/` returned **401** with
  `WWW-Authenticate: Bearer ... resource_metadata=...` and
  `scope="panadan:mcp:read"`; the new policy is not a no-token bypass.
- All three GitHub Action workflows passed for this commit (full CI,
  staging UI, synthetic MCP resource). Unit/integration tests cover
  signed dynamic Test client access and rejection of wrong
  audience, issuer, scope, subject, Live client and missing client identity.

**NOT YET PASSED:** A *real* DCR/CIMD-issued Test JWT with the canonical MCP
audience successfully executing the synthetic tool. This requires a
new, unpinned MCP client connection and actual Test-member consent. If
Stytch issues a DCR/CIMD token with only its default project audience,
the exact resource audience check rejects it, as intended.

**Rollback:** On the isolated MCP staging Vercel project, set
`PANADAN_STAGING_CLIENT_MODE=pinned` and redeploy; no production Panadan
or Stytch Live changes are involved. Restore default once experimentation
is complete. Keep PR #104 draft.


## Hosted Test CIMD client smoke (2026-11-12)

A **read-only, publicly retrievable** Test CIMD metadata document and
a distinct Test-only browser PKCE mode were added under the Stytch
authorization frontend. The existing manual registered-client test
remains the default and unchanged.

The new browser flow:
- restricts the advertised CIMD client to the single
  `https://panadan-stytch-oauth-staging.vercel.app/.well-known/panadan-test-cimd.json`
  URL and exact hosted HTTPS callback;
- includes the canonical `/mcp/` resource in the initial authorization
  request and at the token exchange (in CIMD mode);
- requires the exact trusted HTTPS `iss` in the browser callback
  (RFC 9207), and forbids duplicated `iss`, `state`, or `code`;
- retains single-use PKCE verifier/state and removes authorization codes
  from browser history;
- permits only the owned URL in synthetic resource `any-test-client`
  mode, never arbitrary URL client IDs; the signed JWT and pinned Test
  member/resource/scope checks are unchanged.

**Live CIMD Test authorization/tool success is still PENDING.**
Stytch's headless SDK lacks a typed `resource` parameter for its
authorize-submit call, so end-to-end RFC 8707 resource forwarding has
not been established. A project-only JWT audience must fail MCP access
until corrected at the issuer, not via a verifier bypass.

This new metadata is a disposable synthetic Test client only and must
not be confused with production OAuth client metadata. Keep PR #104 draft,
no Stytch Live updates, and no production cutover.
