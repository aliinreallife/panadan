# Panadan MCP authentication / راهنمای احراز هویت MCP

Panadan exposes **read-only** MCP tools. It has two mutually exclusive auth modes:

| Mode | Intended use | Who issues the token? |
| --- | --- | --- |
| `legacy` (default) | Local or trusted MCP clients supporting custom bearer headers | Panadan's own admin-issued, revocable token |
| `oauth` | Authenticated remote MCP with individual user identities | An **external OAuth 2.1 identity provider** with Authorization Code + PKCE |

The REST API and browser session authentication do not change when MCP switches modes.
Raw transcripts are **not** exposed. A separate explicitly granted `calls:transcript:read` capability can enable redacted, paginated excerpts via `get_redacted_call_transcript`. Arbitrary SQL and write operations remain unavailable.

## 1. Local setup without a domain (default)

Leave `PANADAN_MCP_AUTH_MODE=legacy` in your private `.env.app`.

Admin → **توکن‌های دسترسی** → create a `mcp:read` token for an active authorized account.
Clients supporting custom HTTP headers can use:

```json
{
  "mcpServers": {
    "panadan": {
      "url": "http://127.0.0.1:8508/mcp/",
      "headers": { "Authorization": "Bearer YOUR_MCP_TOKEN" }
    }
  }
}
```

Do not store the token in Git or paste it into shared documentation. Clients have different configuration formats.

**ChatGPT hosted connections cannot reach your machine's localhost directly.**
Some supported ChatGPT configurations offer Secure MCP Tunnel, but a tunnel alone does not implement OAuth.

## 2. OAuth resource-server mode (v0.6)

Panadan deliberately delegates user sign-in, consent, OAuth client registration,
authorization-code + **PKCE S256**, token issuance and refresh tokens to a proper
identity provider (IdP). It does **not** operate an OAuth authorization server.

**Choose and configure an IdP that supports all of:**

- An externally reachable stable **HTTPS** issuer with OAuth Authorization Server Metadata (RFC 8414) or OIDC discovery, and an HTTPS JWKS endpoint.
- Authorization Code with PKCE `S256`, and one of CIMD, Dynamic Client Registration or a **pre-registered client** that your target MCP client supports.
- A short-lived (maximum 60 minutes) **RS256-signed JWT access token** with `iss`, `aud`, `sub`, `iat`, `exp` and an authorized `scope` claim.
- Resource indicator handling (RFC 8707): accept the `resource` query parameter in the authorization and token requests and issue tokens whose **audience exactly contains the resource URL** you configure below.
- HTTPS redirect URI allowlisting for the ChatGPT / other-client callback, suitable refresh-token configuration where needed, and user-consent controls.

OAuth provider support is **provider-specific**; do not assume that a generic OIDC login alone satisfies the MCP OAuth requirements.

### Private configuration

Only enable OAuth **after** you have an HTTPS endpoint for the identity provider
and a trusted HTTPS route/tunnel/proxy to the MCP resource:

```ini
# In your private .env.app, never in Git:
PANADAN_MCP_AUTH_MODE=oauth
PANADAN_OAUTH_ISSUER=https://identity.example.org
PANADAN_OAUTH_JWKS_URL=https://identity.example.org/oauth/jwks
PANADAN_OAUTH_RESOURCE=https://reports.example.org/mcp/
PANADAN_OAUTH_SCOPE=panadan:mcp:read
PANADAN_OAUTH_MAX_TOKEN_TTL=3600
```

Replace the example hosts and URLs with *real* IdP and resource URLs.
The configured resource URL **must end with `/mcp/`**.
The issuer and JWKS URL are never taken from incoming tokens or HTTP headers.
Restart Panadan after editing `.env.app`.

If any OAuth setting is missing, malformed or insecure, Panadan refuses to start
in OAuth mode. It does not fall back to an unverified bearer token.

### Protected resource discovery

After enabling OAuth, clients can query:

```text
GET https://reports.example.org/.well-known/oauth-protected-resource
GET https://reports.example.org/.well-known/oauth-protected-resource/mcp
```

This advertises the canonical `resource`, the IdP `authorization_servers` issuer
and the required scope. Unauthenticated MCP requests return `401` with
`WWW-Authenticate: Bearer resource_metadata="..."` so clients can discover OAuth.
Panadan does **not** publish authorization-server metadata because that document
must be hosted by your real IdP.

### Bind Panadan accounts to identity-provider subjects

After the IdP is configured:

1. Sign in as Panadan admin and open **اتصال امن OAuth** (`/dashboard/oauth`).
2. Locate each person's immutable **subject ID (`sub`)** in the IdP administration UI.
3. Link that exact `sub` to the intended Panadan user. **Never link by display name or unverified email.**
4. Give the Panadan user only the appropriate local `calls:read`, `metrics:read`, and `mcp:use` permissions.
5. Test with a signed, audience-correct access token. The MCP endpoint rechecks the local account's active status and permissions **on every request**.

Changing a user's role/status automatically removes the OAuth subject binding;
the administrator must explicitly approve it again. Revoking the binding immediately
blocks subsequent MCP requests. Revoking the **JWT at the IdP** is separate and
depends on provider capabilities; short token expiration limits risk. Tokens are
not stored in the Panadan database.

**OAuth mode excludes manual `mcp:read` bearer tokens.** Existing API tokens still
work only against their authorized REST endpoints.

### What ChatGPT needs

When permitted by your ChatGPT plan/workspace and after secure hosting is configured:

1. Add a custom MCP server using the externally reachable MCP URL, or an eligible Secure MCP Tunnel.
2. Choose OAuth authentication and configure provider client identification (CIMD, DCR, or static credentials).
3. Configure the exact redirect URI shown by ChatGPT in your IdP, as well as the requested scope and resource indicator.
4. Authorize a linked Panadan identity and verify the non-sensitive MCP tools.

**Not yet proven**: live ChatGPT OAuth sign-in, IdP client registration, and
callback/refresh interoperability. They require an actual IdP and reachable HTTPS
endpoint; passing local JWT tests alone does not establish end-to-end compatibility.

## 3. Important hardening before remote exposure

Do not publish the present development HTTP endpoint or the PostgreSQL TCP relay.
Remote deployment requires a real HTTPS reverse proxy or supported secure tunnel,
host and origin allowlists, secure cookies, rate limiting, abuse and audit controls,
reliable auth-store backups, operational key rotation, and review of the provider's
authorization and consent settings. Reporting database connections continue to use
explicit read-only transactions. Verify the reporting account's server-side SQL
privileges are restricted independently.

Provider / ChatGPT documentation:
- https://developers.openai.com/plugins/build/auth
- https://modelcontextprotocol.io/specification/latest/basic/authorization
- https://www.rfc-editor.org/rfc/rfc9728

## Authorized AI conversation analysis

The MCP tool `get_redacted_call_transcript(call_id, offset=0)` returns up to
6,000 **redacted** characters plus `next_offset` and `has_more`.
Use `next_offset` to fetch the next part until `has_more=false`. The total
conversation and number of requests are **not capped**. Only a linked, active
user whose Panadan role explicitly allows `calls:transcript:read` may read
these excerpts. Every request is recorded in the local audit store.

The redaction masks common phone numbers, email addresses, links and IBANs;
**it is not anonymization**. Spoken personal names, addresses and sensitive
facts may remain. Obtain appropriate authorization before sending transcripts
to an external AI provider. No transcript contents are written to the audit log.
