# Decisions
1. Keep remote PostgreSQL as a read-only data source, not an auth database.
2. Use local SQLite for admin password hash, revocable sessions, and hashed API/MCP tokens.
3. Bind port to `127.0.0.1` only. External deployment requires TLS and an access-controlled reverse proxy.
4. No general SQL queries; only hard-coded allowlisted view and parameterized filters.
5. Separate `mcp:read`, `api:read`, and `api:sensitive` tokens. MCP never returns customer phone numbers, transcripts or full free text.
6. PostgreSQL `SoldOut` is labeled as a source-system state; do not claim confirmed sale without business validation.
7. Keep the current VPN DNS/routing restrictions, review kill-switch and egress before production.
8. Non-OAuth static MCP bearer tokens are acceptable for compatible clients in the initial private deployment; standards-compliant OAuth will be required for broad client compatibility.
