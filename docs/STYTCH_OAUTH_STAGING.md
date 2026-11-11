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
