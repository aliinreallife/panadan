# Unified data permissions, MCP delegation, and access discovery

**Status: PRODUCT/SECURITY DESIGN ONLY — NOT IMPLEMENTED OR DEPLOYED.**
This document supersedes the assumption that merely adding a permission
group selector (PR #99) implements fine-grained authorization. The current
production MCP gate still requires `mcp:use`, `calls:read`, and `metrics:read`
for its standard tools. It does not support per-column grants, per-app
user-managed OAuth consent, or capability introspection. Keep this design
outside the live reporting cutover.

## 1. User story

- An admin gives a user access to exactly three source fields: `id`,
  `CALLDATE` and `aicallinfostate`.
- The user sees only those permitted fields in relevant Panadan reporting
  views/API. Their MCP tools can return **at most** those three fields.
- When authorizing an AI application, the user sees all three eligible fields
  preselected, and may approve only `CALLDATE` and `aicallinfostate`.
- This particular application then returns only two fields; the user's
  dashboard may still return three.
- If an admin removes `CALLDATE`, the AI immediately loses it; if the
  admin later grants `customername`, the AI does **not** receive that new
  field until the user explicitly approves an updated application grant.

## 2. The authorization equation

Each data-request operation computes an effective server-owned policy:

    effective = current_user_access
                INTERSECT client_approved_delegation
                INTERSECT verified_token_limits
                INTERSECT fixed_server_policy

Within each term, consider at least: capabilities, visible source fields,
row/tenant/team scope, allowable operations, and independent disclosure
restrictions. This intersection runs at **request time**, not just when
the connection is created. Cached token claims and MCP model arguments never
override revoked user permissions.

A *new* OAuth approval form starts with all the user's current **MCP-eligible**
permissions selected, with a prominent warning for sensitive fields and an
explicit approve/deny action. Administrative operations, raw SQL, source
writes, and other non-MCP capabilities are NEVER auto-eligible.
Reauthorization of a previously restricted app starts from its previously
approved subset by default; don't silently expand it because the user
received new privileges since the previous consent.

Group presets merely set defaults for the user's capabilities/field grants.
Dynamic group inheritance, changing many existing accounts at once, is a
separate migration needing transactional revision/revocation semantics.

## 3. Source field catalog and sensitivity

The observed 37-field Odoo reporting-view contract is fixed in
`server/odoo_full_mirror_adapter.py` (COLUMN_TYPES). Use a reviewed,
versioned **field registry** mapping stable IDs to exact SQL columns,
Persian labels, description, category, and applicable surfaces.

*Proposed classification, needs business owner signoff before production:*

- Operational/internal: `id`, `CALLDATE`, `tellstate`, `tellside`,
  `tellnum`, `voice_length`, `call_time`, `aicallinfostate`,
  `vw_followup_stage_name`
- Commercial/organizational confidential: `possibility_of_sale_ai`,
  `deal_value`, `invoiced_target`,
  `vw_danix_base_info_users_userinfo`,
  `vw_danix_base_info_users_name`, `vw_danix_base_info_users`,
  `vw_how_to_know_name`, `how_to_know_id`,
  `pipeline_expert_id`, `stage_id`, `team_id`,
  `crm_team_name`, `crm_team_user_id`, `crm_team_user_name`,
  `currency_id`, `vw_res_currency_name`, `vw_res_currency_full_name`
- Customer identifying/free-text high confidentiality: `call_id`,
  `customername`, `customertell`, `outcome`,
  `ai_recommendation`, `summary`, `tell_state_desc`,
  `REFRECIDAICALLINFO`, `transcription`
- Internal change markers, not offered by default: `create_date`,
  `write_date`

The display/consent catalog is reviewed **metadata**, not raw data. There
is no implicit visibility for unknown future fields. Distinguish
`transcription` (raw full text) from separately redacted, paged and
audited transcript excerpts: the latter is not authorization for raw text.

The current production `server/database.py` supports a smaller fixed
PUBLIC/DETAIL/SENSITIVE projection than this 37-column proposal.
Do not expose all mirrored fields in production until per-field filtering,
row scoping, backend selection and duplicate-join behavior are reviewed.

## 4. Permission Discovery API and MCP tools

An AI must not guess what a user's data grants are. It needs a first-class,
non-sensitive schema/capability introspection interface.

### Endpoint: `GET /api/v1/me/access`

Requires a real, authenticated identity and/or a scoped bearer token bound
to a live active account. Not publicly accessible, and must **not** require
the caller to already hold calls/metrics permissions just to inspect their
own grant. It only describes the **calling actor's** access.

Expose:
- effective MCP-eligible capabilities and permitted field IDs/labels;
- granted scopes/operations and row/team limitations as non-sensitive
  policy descriptors, never a list of protected customers;
- categories/safe fixed field descriptions for restricted capabilities,
  differentiating "user lacks permission" vs "user owns permission but did
  not approve it for this app" vs "blocked by server policy";
- approval details for the **current verified client only**, including
  authorization expiration, when known;
- an explanation of what the AI should ask the user to do next, without
  administrator email, member directory, sensitive record values or
  cryptographic details.

Never let a client request some other user's identity in this endpoint.
A dedicated administrator view may separately inspect/manage user grants
with explicit authorization and audit.

### MCP tool: `get_my_access()`

Available to *authenticated, MCP-enabled* clients even when the user has
no calls/metrics privileges, so it can explain missing access. No raw
SQL, source customer records, private grant IDs, passwords or tokens.
This tool must be treated as a safe metadata operation only.

Recommended stable response shape (illustrative, **not live**):

~~~json
{
  "schema_version": 1,
  "actor": "self",
  "client": {"label": "Connected AI application"},
  "permissions": {
    "capabilities": ["calls:read", "mcp:use"],
    "columns": ["id", "CALLDATE"],
    "row_scope": {"kind": "organization_policy"}
  },
  "can_request_more_access": true,
  "note": "Available fields are restricted by the user, app approval and server policy."
}
~~~

The `columns` array is the *actual effective* list, not merely what the
human user possesses. Returning a list of denied field **names** is safe
only for entries in a preapproved public-to-members schema catalog.
Do not reveal whether a specific restricted call/customer/employee exists.

### MCP tool: `explain_access(requested_field?, requested_operation?)`

Accept only a server-reviewed, enumerated field ID or operation, never a
user-provided SQL expression or arbitrary person identifier.

Use structured, stable reason codes:
- `allowed`: caller has current effective access.
- `needs_admin_grant`: the owning Panadan user lacks this permission.
- `needs_user_consent`: user possesses the right but excluded it from
  this AI app's delegated approval.
- `needs_both`: admin must grant first, then user must approve for this app.
- `row_scope_restricted`: current actor's organizational scope disallows
  this operation; do not confirm target existence.
- `not_exposable`: application policy prohibits this operation, even
  if a user asks an admin to grant it.
- `unknown_or_unavailable`: unknown field, server/version mismatch or
  unavailable policy evaluation — fail closed.

Sample (no customer value disclosed):

~~~json
{
  "requested": {"field": "customertell"},
  "allowed": false,
  "reason": "needs_admin_grant",
  "missing": [{"kind": "user_column", "id": "customertell"}],
  "next_step": "Ask your Panadan administrator to grant access to customer phone numbers."
}
~~~

For person-specific requests (e.g., "phone number for employee X"),
the result MUST NOT confirm X exists or identify another user's grants.
Only report whether the caller can perform the **category of operation**.
An actual data lookup also needs a separate row/tenant authorization check.

When a normal MCP tool call is rejected, return a sanitized structured
access-denied result consistent with these reason codes and an option to
call `get_my_access`/`explain_access`. Never return a private record
value in either the message or metadata. Malformed or unauthenticated
requests still return a generic 401 rather than a detailed access report.

### Optional: user-initiated access request

Future portal endpoint `POST /dashboard/access-requests` and optional
MCP action `request_access`: submit only a reviewed permission ID, minimal
justification and authenticated actor identity to an **admin approval queue**.
Rate-limit, CSRF-protect browser operations, audit the request/review, and
require explicit user confirmation before any assistant sends a request.
No self-approval, automatic grant, silent notification, target-person
enumeration or raw customer information in the request. Administrators can
approve or reject; approval updates the user's grants, and the user must
then re-consent the app where applicable. The AI may *suggest* this flow
without submitting it.

## 5. OAuth consent and delegated grants

Panadan currently acts as an OAuth **resource server**, with an external
OAuth identity provider and locally bound `sub`. It does NOT currently
provide the authorization-server consent screen or per-app local grants.

To implement delegated subsets safely, either:
- integrate supported per-client, granular consent/scope issuance at the
  external IdP, ensuring Panadan validates the asserted client/scope; or
- build a separate, user-authenticated Panadan app-approval flow, tied
  cryptographically to a validated `client_id`/authorized party and bound
  to the verified OAuth token resource and user. Never trust a display name
  or `client_id` supplied in a tool argument.

For each client grant store: verified Panadan user ID, trusted client
identity, registry version, exact approved capability and field ID subset,
row-scope upper bound, grant revision, approval/revocation timestamps and
audit records (no customer rows). Expiring or revoked grants fail closed.

All of these rules apply identically when using a replacement manual MCP
token with constrained grants. Existing legacy tokens must NOT silently
inherit newly invented column privileges. Old OAuth client links must not
silently gain a default "all granted" approval during migration.

## 6. Enforcement points

- Central server policy must project permitted columns in the dashboard,
  REST, MCP, WebMCP and exports. Hidden UI fields alone are not security.
- Apply row/tenant boundaries before/alongside column projection; never
  treat operator search filters as access control.
- Filter tools/list and tool schemas by effective capability/field set,
  AND recheck each tools/call independently. Do not rely on discoverability
  controls. Preserve audited redacted transcript protections.
- Query and output transformations must both be protected. Internal IDs
  needed to execute queries are not automatically authorized in output.
- Column authorization also constrains filters, search, sorting, grouping,
  aggregate metrics and error messages: otherwise hidden columns may leak
  via inference. A metrics grant never means arbitrary sensitive aggregates.
- Use reviewed hard-coded SQL identifiers (never dynamically supplied
  column names, raw SQL, user identifiers or client claims).
- Do not store another user's full grant map, sensitive values or raw SQL
  in tool logs or client-facing denial messages.

## 7. Test and release gates

This is a security migration that must remain isolated from the currently
running staging sync. Minimum integration tests:

1. User with columns A/B/C: browser, REST and MCP return only A/B/C.
2. Client approved only A/B: MCP returns A/B, dashboard still A/B/C.
3. Admin revokes B: all sessions/clients lose B on next request; no stale
   caching, and no silent fallback to a broader default.
4. Admin grants D later: old client does not gain D until explicit new
   consent. New client gets only what the user approves.
5. Field-specific deny, team/row deny, and existence-probing attempts
   reveal no restricted values and no target existence.
6. Self-discovery endpoint and tools cannot inspect other users. Tool
   failures return sanitized reason codes and safe next steps.
7. Legacy MCP bearer, OAuth, direct tools/call bypass, tools/list, REST,
   dashboard, WebMCP, pagination, export, filters, totals and transcript
   audit all honor the same effective policy.
8. Connection revocation, user deactivation, OAuth client identity drift,
   token expiry, malformed grant, unknown fields, schema change and disabled
   auth store all fail closed.
9. Test private staging and read-only mirror separately. Do not cut over
   production source or merge this design into a live permission rollout
   until the backend is implemented, tested and an independently reviewed
   rollback is available.

Documentation-only spec. No code deploying or granting this access exists.
