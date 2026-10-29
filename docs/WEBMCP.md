# WebMCP (experimental browser integration)

Panadan now exposes optional **WebMCP** browser tools to AI-enabled Chromium
browsers **while an authenticated dashboard tab is open**.

WebMCP is **not** the remote MCP JSON-RPC server at `/mcp/`. It does not replace
OAuth, does not create external API endpoints, and does not let hosted ChatGPT
connect to localhost. It is a browser-native tool registry exposed through
`document.modelContext.registerTool()`.

## Browser requirements

- A supported Chromium-based browser with WebMCP early preview enabled.
  Chromium WebMCP is experimental and subject to API changes.
- For Chrome development builds, visit `chrome://flags/#enable-webmcp-testing`,
  enable it, and restart the browser. Chrome's experimental documentation describes
  current availability; you may need the experimental browser channel/origin trial.
- An authenticated Panadan dashboard at `http://127.0.0.1:8508/dashboard` or
  a properly configured HTTPS origin. `localhost` is a trustworthy development
  origin; public network HTTP should **never** be exposed.
- A WebMCP-capable **browser agent/extension or test harness**. Registration alone
  does not install an agent in the browser.

When registration succeeds, the dashboard shows
`WebMCP فعال · آزمایشی`. Unsupported browsers behave normally; nothing is
downloaded and no external script is required.

## Registered tools

| Tool | Required dashboard permission | Data |
| --- | --- | --- |
| `panadan_get_call_metrics` | `metrics:read` | Aggregate counts and averages |
| `panadan_find_calls` | `calls:read` | Small paginated list of metadata, maximum 20 per call |
| `panadan_get_call_overview` | `calls:read` | High-level metadata for one call ID |

The tools use the **same-origin browser session cookie** to call the existing
server-side endpoints. Server RBAC checks are authoritative even if browser
JavaScript is modified. All WebMCP data requests are `GET` and `no-store`.
No arbitrary SQL, insert/update/delete, token creation, user-management action,
or cross-origin network requests are registered.

**Important privacy design:** Basic metadata tools never return transcripts or customer names/phone
numbers. Overview uses the dedicated
`GET /dashboard/overview/{call_id}` endpoint with `sensitive=False`, avoiding
even an unnecessary server response containing a transcript. AI-facing tool
output is explicitly marked `readOnlyHint` and `untrustedContentHint`.

WebMCP tool permissions reflect the page's server-rendered access state.
Capabilities still need to be checked by the server for every request.

## Manual testing

1. Run `./panadan.sh setup && ./panadan.sh test && ./panadan.sh dev`.
2. Sign in as a user with `metrics:read` and/or `calls:read`.
3. In a supporting browser with WebMCP enabled, visit `/dashboard`.
4. Confirm the `WebMCP فعال · آزمایشی` status appears.
5. In a WebMCP-capable browser agent/extension, inspect the available page tools.
6. Check that a metrics-only account can see only `panadan_get_call_metrics`;
   a calls-only account gets the two call-metadata tools.
7. Inspect tool results and ensure no sensitive text is present. Logout
   removes the page and its registered tools; moving away aborts the tools.

Automated Node tests mock the browser tool registry and verify the
function-level guardrails without connecting to real customer data.
Do **not** claim browser-interoperability is validated until step 5 is
tested against a supported agent and browser.

## Next upgrade

The `panadan_get_redacted_transcript` browser tool is registered only when
`calls:transcript:read` is explicitly granted alongside `calls:read`. It
retrieves one redacted chunk at a time and returns a `next_offset` so the
entire long conversation remains accessible. Accesses are logged without
transcript contents. This remains experimental until tested in a supporting
WebMCP browser agent.

For remote, cross-client OAuth authorization, see `docs/MCP_SETUP.md`.
