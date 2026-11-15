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
