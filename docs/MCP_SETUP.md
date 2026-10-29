# Panadan MCP setup / اتصال MCP

## Today: localhost, no public domain

Panadan exposes `/mcp/` as **Streamable HTTP** behind a dedicated revocable
`mcp:read` bearer token, created in Dashboard > Access Tokens. This token
is separate from browser sessions and REST API credentials. It is tied to
an active user permitted to read both calls and metrics, and it exposes
only the **non-sensitive** reporting tools (`list_recent_calls`,
`get_call_summary`, `get_call_metrics`, `get_available_states`).

On the same machine, a capable MCP client can configure its URL as
`http://127.0.0.1:8508/mcp/`, with header
`Authorization: Bearer <YOUR_MCP_TOKEN>`. Never commit the token.

JSON-shaped example for clients supporting URL + custom headers:

```json
{
  "mcpServers": {
    "panadan": {
      "url": "http://127.0.0.1:8508/mcp/",
      "headers": {
        "Authorization": "Bearer YOUR_MCP_TOKEN"
      }
    }
  }
}
```

Config schema varies by client. Keep this configuration local and private.

## ChatGPT when you have no domain

ChatGPT cannot call your localhost HTTP endpoint directly. OpenAI supports
**Secure MCP Tunnel** for compatible products as a way to reach a private
server without publishing it on the Internet:
https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt

**Important:** The current Panadan bearer-token gate does NOT implement the
OAuth 2.1 Authorization Code + PKCE / protected-resource metadata contract
needed for supported user-facing OAuth MCP connection flows. A tunnel alone
does not implement OAuth. It is **not** accurate to describe this build as a
one-click ChatGPT OAuth integration. Plan and test OAuth before enabling that
workflow. No arbitrary public port forwarding is recommended for Odoo data.

## Later: public domain

Only expose Panadan behind HTTPS after implementing: OAuth 2.1, access/refresh
token lifecycle, issuer/audience/scope validation, request rate limiting,
proxy-aware secure cookies and explicit allowed hosts/origins, and a security
review. Dedicated DB and MCP credentials remain in private environment files.
The reporting database always runs inside `READ ONLY` transactions.

See https://developers.openai.com/plugins/build/auth
