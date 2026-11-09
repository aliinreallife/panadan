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

- MCP requires BOTH call-list and metrics permissions.
- Sensitive call detail and transcript access require call-list permission.
- Non-admin accounts cannot manage users or tokens.
- The server independently revalidates every submitted grant list; UI
  automation or a forged preset ID cannot bypass it.
- Existing users are not migrated or automatically granted privileges.
- The current data source, source VPN, mirror, scheduled jobs, API/MCP scopes
  and reporting backend remain unchanged.

## Future dynamic group membership

Group inheritance that updates many users automatically is a SEPARATE
security migration, requiring explicit conflict rules, revocation semantics,
audit trails, both SQLite and PostgreSQL-staging support and review. It must
not be silently introduced in the present visual editor.

Do not merge or deploy this draft PR until CI and manual privilege tests
pass. It is independent of mirror PR #97 and sync status PR #98.
