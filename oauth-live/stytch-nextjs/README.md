# Panadan Stytch Live Authorization UI

**Standalone production-issuer OAuth authorization page. NOT deployed to dan.panafor.com or connected to customer data.**

This is an isolated Next.js application for the real Stytch **Production**
B2B project. It does not include the experimental Stytch **Test**
RFC 9207 issuer-compatibility shim, synthetic MCP probe, token inspector,
or authorization-code echo endpoint.

## Configure after code review

1. In **Stytch Production → Management → Organizations**, create one
   explicit pilot organization and member. Configure the RBAC resource
   `panadan`, action `mcp_read`, and scope `panadan:mcp:read`. Do not
   turn on broad signups for all production users.
2. In **Frontend SDK**, enable the Production frontend SDK and authorize
   exactly your chosen production authorization UI hostname.
3. Deploy to a dedicated, independent Vercel project
   `panadan-stytch-oauth-live` with this directory as the Root Directory.
   Configure `NEXT_PUBLIC_STYTCH_PUBLIC_TOKEN` there using the **Live
   Public Token**, not the Live Secret Key. The code checks the
   `public-token-live-...` syntax and refuses the Test public token.
4. In **Stytch Production → Connected Apps → Settings**, set
   **Authorization URL** to
   `https://panadan-stytch-oauth-live.vercel.app/oauth/authorize`
   after verifying that the Vercel project owns that hostname.
   Enable CIMD registration for ChatGPT, and configure the correct signed
   access-JWT audience `https://dan.panafor.com/mcp/`, with 60-minute
   maximum TTL. Verify OAuth discovery issuer/authorization/token/JWKS
   against `https://flame-calf-4073.customers.stytch.com`.
5. In a Live login smoke test, complete email OTP, organization selection
   and Stytch-issued consent for a *new* OAuth client. Never paste
   codes, session cookies, access JWTs or API secrets in chat.
6. Only after approved production recovery and user-grant testing,
   separately deploy and enable the real Panadan **resource server**
   at `https://dan.panafor.com/mcp/` as reviewed in
   `docs/LIVE_MCP_OAUTH_ROLLOUT.md`.

## Security

- This frontend never queries Odoo, a reporting database, or Panadan
  authentication tables. A Stytch Live member session does not grant
  reporting access.
- `/oauth/authorize` accepts only Authorization Code + PKCE S256 with
  either exact allowlisted MCP resource if supplied, and required scope.
  Stytch performs the authoritative client/redirect/consent validation.
- The callback authorization code is issued by Stytch directly to
  the OAuth client; it is never displayed or stored by this app.
- Production/Live does NOT use the synthetic Test client or old Test issuer.
  If Stytch's native component emits a response issuer inconsistent with
  its Live discovery document, treat that as a blocker. Do not copy
  Test-only issuer rewriting to production.
- The real dashboard's SQLite authorization and per-column MCP grants
  continue to apply at the resource server. Existing live legacy bearer
  mode stays active until a reviewed, backed-up cutover.

## Live synthetic-resource test (not production reporting)

The UI source now also allows **exactly** `https://panadan-mcp-live-synthetic.vercel.app/mcp/` for an isolated, synthetic-only resource. Duplicate or arbitrary resource values remain rejected. Its distinct JWT audience cannot authorize real Panadan MCP, and the Stytch Test issuer remains forbidden.

**Status 2026-11-18:** GitHub source and tests are updated and CI passes, but the updated Live UI **has not been deployed**. The Git-source preview failed with `git_info_fail`; the direct-source preview was then blocked by the Personal Vercel account's daily API deployment quota (HTTP 402). The active Live UI continues to allow the production resource only. Do not claim end-to-end Live synthetic OAuth acceptance until the new UI is deployed, the distinct audience is issued by Stytch, and an approved user completes consent.
