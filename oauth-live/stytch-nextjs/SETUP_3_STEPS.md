# Stytch Live: minimum admin setup

This site is the **consent/login UI**, not the Panadan reporting server.
The end-user experience is **ChatGPT Connect → email code → approve → ChatGPT**.
The site does not grant report access merely because login succeeds.

## What the Panadan administrator must do once

1. **Stytch Production** (panadan B2B) → Management → Organizations:
   Create a private pilot organization and add **one approved member**.
   Do not open public self-signup yet.
2. **Vercel** → panadan-stytch-oauth-live → Settings → Environment Variables:
   Add the exact `NEXT_PUBLIC_STYTCH_PUBLIC_TOKEN` from Stytch Production's
   Project Overview (a *public token*, **never** the secret).
   Environment: Production. Redeploy the latest ready release.
   Confirm `https://panadan-stytch-oauth-live.vercel.app/api/status`
   returns `{"service":"panadan-live-authorization-ui","status":"configured"}`.
   Add `https://panadan-stytch-oauth-live.vercel.app` to Stytch
   Production → Frontend SDK → Configuration → authorized origins.
3. **Stytch Production → Connected Apps → Settings**:
   Set Authorization URL exactly to
   `https://panadan-stytch-oauth-live.vercel.app/oauth/authorize`.
   Confirm the issuer at
   `https://flame-calf-4073.customers.stytch.com` advertises correct
   HTTPS OAuth endpoints. Register/enable CIMD and configure the custom scope
   `panadan:mcp:read` as required by Stytch.

## Separate controlled resource-server release

Before the first **real** call: grant the exact signed Connected App client
only to the correct existing Panadan user, approve minimal fields, validate
Stytch Live JWT `iss`, `aud=https://dan.panafor.com/mcp/`, `scope`,
expiry and revocation, plus isolated rollback rehearsal. Production's existing
legacy MCP auth and real reporting data are unchanged by this frontend project.

Never copy Test credentials, authorize arbitrary clients, expose raw
transcripts by default, or commit credentials to this repository.
