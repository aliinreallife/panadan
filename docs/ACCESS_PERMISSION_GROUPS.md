# Access categories and permission group templates (draft)

Production authorization checks remain server-side in Panadan's SQLite
session, API and MCP token verification. PG authentication stays staging-only.
This change does not grant access by CSS, JavaScript or preset label.

## Categories

| Persian label | Existing capabilities | Meaning |
| --- | --- | --- |
| کم‌خطر | metrics:read | Aggregate statistics; still internal |
| داخلی | calls:read | Call lists and non-sensitive details |
| محرمانه | calls:sensitive, calls:transcript:read | Sensitive record details and audited transcript access |
| اتصال و یکپارچه‌سازی | mcp:use | MCP usage subject to existing token/OAuth checks |
| مدیریتی | tokens:manage, users:manage | Admin-only token and account management |

Each individual permission describes exactly what it enables, and what
prerequisites it has. These are explanations, NOT extra privileges.

## Ready-made groups

- فقط آمار: metrics:read
- مشاهده تماس‌ها: calls:read
- تحلیل‌گر استاندارد: calls:read, metrics:read, mcp:use
- تحلیل‌گر محرمانه: calls:read, metrics:read, calls:sensitive
- بررسی مکالمات: calls:read, metrics:read, calls:transcript:read

The group selector copies the preset's explicit capabilities into a
particular user's form. An admin may then modify individual capabilities.
Other users are unaffected. These are **non-dynamic templates**; changing a
template in a future release must not silently elevate existing accounts.
Role names are retained for compatibility. For non-admins, effective saved
capabilities control access; role names are not a reliable security tier.

The admin role has every existing capability. Use a non-admin role for a
restricted account. Changes to existing user grants continue to revoke
their current sessions, tokens and OAuth bindings.

## Security dependencies

- In the unified-access branch, MCP requires at least one of call-list or metrics permissions; each MCP tool checks the separate capability it needs.
- Sensitive call detail and transcript access require call-list permission.
- Non-admin accounts cannot manage users or tokens.
- The server independently revalidates every submitted grant list; UI
  automation or a forged preset ID cannot bypass it.
- Existing users are not migrated or automatically granted privileges.
- The current data source, source VPN, mirror, scheduled jobs, API/MCP scopes
  and reporting backend remain unchanged.

## MCP should inherit the user's individual permissions (follow-up requirement)

The current implementation uses one coarse MCP gate requiring the active
user to hold all of: mcp:use, calls:read and metrics:read. This is a
**confirmed current limitation**, not a feature delivered by this PR.

For a future narrowly scoped per-tool implementation, use this policy:

| Tool | Proposed user grant requirement |
| --- | --- |
| Recent calls, call summary, call states | mcp:use and calls:read |
| Call metrics | mcp:use and metrics:read |
| Redacted transcript | mcp:use, calls:read, calls:transcript:read and an access audit |
| Sensitive record detail | No MCP tool presently offers this; require a separate reviewed approval to add one |
| User/token management | Not available to MCP |

MCP still needs a valid, locally bound legacy bearer token or approved OAuth
user. Filter tools/list based on **that authenticated user's current
permissions**, and reject unauthorized tools/call independently, not just
in the UI or advertised tool list. Recheck active user/grants at every call;
revocation must take effect immediately. Preserve existing transcript
redaction, paging and disclosures. Do not accept a user ID or permissions
from model-supplied arguments or tool metadata.

This specification is a desired follow-up only. Do not relax the existing
MCP prerequisites or advertise per-tool enforcement until it is implemented
and tested across legacy MCP, OAuth, unauthorized direct calls, tool discovery,
revocation and concurrent requests.

## Planned unified field permissions and AI-readable access explanations

The intended per-column access model, OAuth application-specific subsets,
read-only access-discovery API/MCP tools, and administrator request workflow
are specified in [UNIFIED_AUTHORIZATION_MCP.md](UNIFIED_AUTHORIZATION_MCP.md).
They are **not** implemented by the current categorized permissions UI.

## Future dynamic group membership

Group inheritance that updates many users automatically is a SEPARATE
security migration, requiring explicit conflict rules, revocation semantics,
audit trails, both SQLite and PostgreSQL-staging support and review. It must
not be silently introduced in the present visual editor.

Do not merge or deploy this draft PR until CI and manual privilege tests
pass. It is independent of mirror PR #97 and sync status PR #98.
