# Isolated Panadan permission integration with Stytch Test

This independent, disposable FastAPI/MCP server checks real Panadan
authorization **code** with a fixed, synthetic reporting dataset. It has no
Odoo, VPN, PG client, customer records or production auth database.

Resource: `https://panadan-authz-integration-staging.vercel.app/mcp/`

## Copied security components

The following files must remain byte-identical to their production PR
sources; CI compares them on each change:

- `server/oauth_mcp.py` — JWT issuer, RS256, JWKS, aud, scope and TTL
- `server/security.py` — Panadan user binding, client consent, fields
- `server/field_permissions.py` — capability/field projection
- `server/mcp_tools.py` — actual reporting MCP tool authorizers
- `server/main.py::MCPBearerGate` — exact production HTTP bearer gate

ONLY `server/database.py` is a synthetic, zero-network reporting fixture.
The separate `server/main.py` is an isolated deployment harness with
a first-use disposable-account provisioner protected by the **signed**
approved Test client ID and SHA-256 of a preapproved Test subject.

This is not production account enrollment, and should never be reused to
auto-provision production OAuth subjects.

## Required isolated Vercel environment

All values must exist **only on the dedicated new integration project**:

```text
PANADAN_INTEGRATION_STAGING_ENABLE=YES
PANADAN_MCP_AUTH_MODE=oauth
PANADAN_OAUTH_ISSUER=https://viridian-faucet-2753.customers.stytch.dev
PANADAN_OAUTH_JWKS_URL=https://viridian-faucet-2753.customers.stytch.dev/.well-known/jwks.json
PANADAN_OAUTH_RESOURCE=https://panadan-authz-integration-staging.vercel.app/mcp/
PANADAN_OAUTH_SCOPE=panadan:mcp:read
PANADAN_OAUTH_MAX_TOKEN_TTL=3600
PANADAN_INTEGRATION_APPROVED_CLIENT_ID=<separate-connected-app-test-uuid>
PANADAN_INTEGRATION_TEST_SUBJECT_SHA256=<sha256-for-disposable-Test-subject>
```

Never add `PG*`, VPN, production Panadan DB credentials, production Stytch
credentials or live reporting sources. Startup refuses remote DB settings.

## Guarantees and limitations

- The /mcp/ gateway is the real Panadan gate, and the tools recheck the
  same local user/client field authorization on every invocation.
- Each serverless instance has ephemeral /tmp SQLite only; grants and
  revocations are NOT shared across cold starts or replicas.
- The dedicated Test subject and Test client can seed **only one synthetic
  user**, with the two non-sensitive fields `id` and `CALLDATE`.
- Only synthetic call 73104 exists. Its redacted fields must never
  contain the sentinel string in tool responses.
- HTTP unauthorized/malformed bearer requests get 401, signed but locally
  unapproved clients can read safe empty consent guidance but not report rows.
- Local revocation and field narrowing are verified in deterministic
  HTTP integration tests, NOT as durable multi-instance production behavior.
- The next manual Stytch Test client must use the above resource URL as its
  exact custom audience, 60-minute expiry, and a separate DCR registration.
- Keep Panadan production on legacy bearer and PR #104 draft.

## Local CI

```bash
python -m pip install -r requirements.txt pytest httpx
python -m pytest -q tests
```


## Live Test verification (manual Test login required)

A separate Vercel project has been deployed to
`https://panadan-authz-integration-staging.vercel.app/mcp/`.
Health/discovery returned 200, and missing/invalid bearer requests
returned 401. Signed Stytch Test client access still requires the user's
browser session; do not claim full live integration before that succeeds.

The isolated app accepts only the already registered MCP Inspector
DCR Test client:
`connected-app-test-2d48e426-3f1c-4aa9-b30b-27f7ee5780e1`.

In **Stytch Test**, set this client's Custom JWT Audience to
`https://panadan-authz-integration-staging.vercel.app/mcp/`
and Access Token Expiry to **60 minutes**. Keep the original CIMD
client's audience unchanged.

In **MCP Inspector**, select a separate Streamable HTTP connection to
the new MCP URL, explicitly enter the DCR client ID (do NOT force a
fresh DCR registration), scopes `openid panadan:mcp:read`, Auth URL
override `https://panadan-stytch-oauth-staging.vercel.app/oauth/authorize-compat`,
no token override and no refresh-token request. Use the same Test member
as the earlier synthetic PASS.

Expected permitted tools: `get_my_access` shows only `id` and
`CALLDATE`, `list_recent_calls` returns only synthetic call
`73104`, and `get_call_metrics` reports `permission_denied`.
This is intentionally *not* connected to any production reports.

`/tmp` auth state is ephemeral and may be reset on Vercel cold starts
or across instances. Only CI verifies local consent/revocation behavior;
never represent in-instance tests as durable live revocation.
