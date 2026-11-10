# PostgreSQL 18 unified-authorization snapshot parity (staging only)

This draft is stacked on PR #100 and does **not** permit production PostgreSQL
authentication, use real credentials, import customer data, or alter the
production backend selection. The current production authority stays SQLite.

The additive `panadan_auth` schema now retains `users.field_grants`,
`access_tokens.field_grants` and `cap_grants`, plus a per-user/client
`mcp_client_grants` table. The guarded SQLite online-snapshot importer
copies and verifies all nine tables field-for-field in one transaction. A
parity mismatch rolls back the entire import. Synthetic PG18 tests verify
user fields, token snapshots and client approvals survive unchanged.

## Still blocked before any production cutover

- The PostgreSQL `PgStore` lacks the runtime `user_access`,
  `api_token_access`, `mcp_access`, `client_grants`,
  approve/revoke/list-client methods and field-aware account editor present
  in the SQLite store. Those must be implemented with equivalent revocation
  and transaction semantics and verified with synthetic HTTP/MCP tests.
- The runtime selector expressly accepts **only** a disposable local
  `127.0.0.1/panadan_ci` staging database. Do not relax this restriction
  before a separate reviewed production selector and least-privilege role.
- No live dual-write exists. Cutover requires a fresh consistent SQLite
  snapshot, encrypted off-VPS independent recovery proof, frozen auth
  writes, verified empty PG18 target, transactional import with complete
  identity/field parity, and tested immediate rollback without token leaks.
- PG auth must never gain raw `panadan_ingest` permissions or external Odoo
  credentials. Per-operator row access remains separately unresolved.

No production migration or release is authorized by this PR.
