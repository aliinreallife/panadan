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
