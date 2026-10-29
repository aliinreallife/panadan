# Panadan – Product Requirements (MVP)

## Purpose
Provide an easy read-only interface for call-report data in `odoo.public.vw_danix_call_info_report` via an isolated OpenVPN connection.

## Users and permissions
- Dashboard administrator: sign in with local password, use secured cookies and CSRF protection, inspect selected full call records, create/revoke API and MCP tokens.
- REST client: scoped bearer key (`api:read`), receives non-sensitive reporting fields.
- Sensitive REST client: separately issued `api:sensitive` bearer key and explicit `include_sensitive=true` on the record endpoint.
- MCP client: separate bearer key (`mcp:read`); only summary metadata and metrics, no transcripts or customer telephone numbers.

## Core features
- Call list, date/status filtering, paging, drawer details
- Summary metrics, call-state lookup
- Scoped API tokens with revocation and expiry
- MCP Streamable HTTP tools for summarization/analytics
- Single SQL-view allowlist and parameterized reads, server-enforced read-only sessions
- VPN inside dedicated network namespace shared by app, local-only HTTP port

## Non-goals
- Editing Odoo records, raw SQL query execution, bulk customer export, multi-tenant user provisioning, general Odoo administration.
- Full OAuth 2.1 / third-party ChatGPT connector authorization (next phase).

## Success criteria
- Existing WSL VPN profile migrates without being committed
- Admin can authenticate and view call list; unauth requests fail
- API and MCP bearer keys are isolated and revocable
- Tests pass; running with no secret bootstrap password fails closed
- No real customer records in source control or CI
