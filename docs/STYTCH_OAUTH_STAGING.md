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
