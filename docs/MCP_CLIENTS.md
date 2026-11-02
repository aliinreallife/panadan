# Panadan remote MCP client interoperability (2026-11-01)

> **Status:** Implementation and staging checklist, **not** a statement that ChatGPT/Claude OAuth already works in production. Public HTTPS Panadan works; OAuth authorization-server and real-client discovery testing do not yet.

## Canonical endpoint and trust boundaries

- MCP Streamable HTTP endpoint: `https://dan.panafor.com/mcp/`.
- A separate FastAPI application serves session-authenticated dashboard and REST APIs. A dashboard cookie must **not** grant MCP access automatically.
- Panadan's local reporting authorization is mandatory on **every MCP request**, independently of remote OAuth login. The Odoo PostgreSQL connection executes bounded SELECT-only reads. Transcript excerpts are best-effort redacted and require explicit `calls:transcript:read` capability; names or other details can survive redaction.
- The server has two exclusive modes:
  - `legacy` (production default unless explicitly overridden): manual, revocable MCP bearer tokens; OAuth discovery deliberately not advertised.
  - `oauth`: strict RS256/JWKS resource-server verification with exact issuer, audience, timestamps, required scope, and locally bound immutable `sub`. Requires a separate identity provider; the Panadan FastAPI server does **not** implement OAuth grant/consent/token issuance.

## Disposable PostgreSQL staging: authenticated profile tool (#59, partial)

The separate `server/mcp_profile_staging.py` registers an **opt-in**
`get_profile` tool *only when* the explicit
`PANADAN_AUTH_BACKEND=postgres-staging` selector has passed the
loopback `panadan_ci` safeguards described in
`docs/ONE_COMMAND_OWNED_PG_SETUP.md`. The live production SQLite MCP
server continues advertising its original **five tools**.

The profile tool has `_meta["openai/profile"]=true`, a structured
response containing the persistent opaque `prf_...` ID (and an optional
display name), no arbitrary account-selector arguments, and MCP read-only
annotations. The tool gets the bearer credential from the SDK's authenticated
request context, verifies OAuth JWTs through the configured verifier in OAuth
mode (or restricts to an authorized local MCP bearer in legacy staging mode),
then rechecks the actual account/permissions in PostgreSQL. It never trusts
request `_meta`, user supplied IDs, or display names as identity,
and does not return email, phone, access tokens, role or raw account rows.

Staging tests check unique identities, stable same-account IDs, OAuth subject
mapping, legacy revocation, response safety and SDK registration metadata.
The PostgreSQL 18 integration job also runs a **fresh-process real MCP
Streamable HTTP** smoke test against the isolated, disposable `panadan_ci`
database with synthetic accounts. It verifies HTTP 401 for absent, invalid
and incorrectly scoped bearer tokens; protocol initialize, tool discovery,
actual `get_profile` call, two-account ID separation, repeat stability,
spoofed tool arguments, role-change/token revocation, and unaffected second
account. The test refuses nonempty accounts and never points to the
Panadan-owned production database. The separate process avoids reusing
the MCP SDK's one-shot session-manager lifespan. This is an SDK/HTTP
staging proof, **not** a ChatGPT/Claude remote OAuth compatibility claim.
**These tests do not claim ChatGPT/Claude OAuth works in production.** The
external IdP, production PostgreSQL cutover, refresh/reconnect interoperability
and full client matrix are still required before the profile tool can safely
be enabled in the live MCP service.

## Why hosted ChatGPT OAuth discovery currently fails

Observed message: `Couldn't discover OAuth settings. Check the server URL or enter settings manually`.

In legacy mode, `GET /.well-known/oauth-protected-resource` returns 404; MCP `401` does not advertise an OAuth `resource_metadata` challenge. Changing the URL to `/mcp`, disabling auth, accepting arbitrary bearer tokens, or treating dashboard login as an OAuth authorization server is **not** a valid solution.

The supported solution must include:

1. An external, HTTPS authorization server with RFC 8414/OIDC discovery exposing exact `issuer`, `authorization_endpoint`, `token_endpoint`, `code_challenge_methods_supported` containing `S256`, client identification/registration support and an accurate `token_endpoint_auth_methods_supported`.
2. Prefer Client ID Metadata Documents (CIMD) when supported; otherwise DCR or explicit preregistered OAuth clients where supported. For a stable OpenAI callback, verify RFC 9207 authorization response issuer identification rather than assuming it.
3. End-to-end `resource=https://dan.panafor.com/mcp/` propagation into the authorization/token exchange and **RS256 access JWT `aud`**. JWT must contain correct `iss`, `sub`, `iat`, `exp`, required `scope`; validate and map issuer+`sub` to authorized local account.
4. With OAuth mode enabled only in a reviewed staging deployment, `/.well-known/oauth-protected-resource` and `/.well-known/oauth-protected-resource/mcp` must be HTTPS-readable. Unauthenticated `/mcp/` must respond with a `401 WWW-Authenticate` bearer challenge that points to protected-resource metadata and correct scope.
5. Test authorization code + PKCE consent, callback, token exchange, access expiry, refresh, revoked local binding, incorrect audience/issuer, token replay constraints, and unauthorized transcript requests. Keep a rollback to legacy mode and do not silently allow both credential types.

The current OAuthConfig requires the canonical resource to end in `/mcp/`. Any deviation is a **deliberate migration**, with coordinated changes to IdP metadata, audience claim and tests.

## Client setup matrix (not yet end-to-end verified)

| Client | Intended integration | Current limitation / required test |
| --- | --- | --- |
| ChatGPT custom MCP/plugin | Public HTTPS Streamable HTTP + OAuth protected resource/issuer discovery + CIMD, DCR or preconfigured client | OAuth discovery fails in current legacy mode; no production IdP; end-to-end client tests required |
| Claude custom remote connector (claude.ai / Cowork / Claude Desktop remote) | Custom Web connector with public URL; published identity, automatic registration or own OAuth client | Needs externally reachable resource and correct IdP; manual fixed bearer headers are a distinct, less user-friendly option where supported |
| OpenAI Codex | MCP client using its supported remote OAuth flow | Test current version, callback, token refresh and tool discovery; never assume ChatGPT and Codex settings are identical |
| MCP Inspector | Streamable HTTP to HTTPS staging, inspect initialize/tools and OAuth Auth settings | Run synthetic and authorized tests before enabling production OAuth |
| Claude Desktop local server integration | May support local stdio or configurable remote connections separately from hosted Claude custom connectors | Document exact supported client version/configuration, never assume cloud connector uses localhost |

To connect Claude's hosted remote connector, the server needs to be reachable from Anthropic's cloud, not just from the operator's laptop. In Claude, select custom Web connector, enter URL, review detected auth, and choose published OAuth client identity, auto registration, or preconfigured client where appropriate. **Do not publish admin-issued MCP tokens in user-facing instructions or shared configs.**

To connect ChatGPT, add the remote MCP URL in the supported connection interface. Choose OAuth only after the external IdP and discovery metadata are live; register the **exact callback and client metadata values shown by the current ChatGPT connection UI** with the IdP. Do not invent callback IDs or assume static redirect URIs for all configurations.

## Non-secret diagnostic commands

The following output may indicate discovery status without exposing credentials:

```bash
curl -i --max-time 10 https://dan.panafor.com/.well-known/oauth-protected-resource
curl -i --max-time 10 https://dan.panafor.com/.well-known/oauth-protected-resource/mcp
curl -i --max-time 10 -H 'Accept: application/json, text/event-stream' https://dan.panafor.com/mcp/
```

Expected **before** OAuth rollout in legacy mode: protected-resource metadata absent and unauthorized MCP denied. Never test a real token with `curl -v` or paste headers/logs into issues. In OAuth mode, protected-resource metadata must match IdP metadata and MCP `401` challenge, but those responses must remain unauthenticated while actual tool results stay private.

After switching on a **staging** IdP, use MCP Inspector / provider logs with **redacted** results to validate the full initialize, tools/list and tools/call sequence. Test disabled users, permission changes, revoked bindings and expired/invalid tokens. A successful `/healthz` or `/login` does **not** test MCP.

## Planned improvements

- #57: choose and configure OAuth authorization server with CIMD/DCR + PKCE and JWT audience.
- #58: verify protected-resource discovery, 401 challenges, edge proxy routing and attack cases.
- #59: truthful read-only MCP tool metadata and authenticated stable profile identity for multi-account clients.
- #23: end-to-end authorization, tool and transcript security test matrix.
- #64: client-by-client compatibility, connection and refresh evidence.
- #21: later, if team/destination/operator access is restricted, apply shared query-level scoped RBAC to **every** dashboard/API/MCP tool first.

## Primary provider documentation

- [OpenAI: MCP/plugin authentication](https://developers.openai.com/plugins/build/auth)
- [OpenAI: Build an MCP server](https://developers.openai.com/plugins/build/mcp-server)
- [Claude: Remote custom connectors](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp)
- [MCP authorization](https://modelcontextprotocol.io/specification/latest/basic/authorization)
- [RFC 9728 protected resource metadata](https://www.rfc-editor.org/rfc/rfc9728)
