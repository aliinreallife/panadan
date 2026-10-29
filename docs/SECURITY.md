# Security deployment checklist

Do not commit `.env.app`, `.env.db`, `.ovpn` files, VPN private keys, SQLite auth data, customer previews, or call transcripts. All are in `.gitignore` and `.dockerignore`. `git status` before publish.

- Default exposure is loopback only. To expose beyond local WSL, place an authenticated TLS reverse proxy and separately configure allowed MCP Host/Origin values; never expose the current HTTP deployment on a public IP.
- Set a long random bootstrap password. It creates the admin account only once. After initialization, password changes require a dedicated management procedure (not supplied by this MVP).
- Use separate short-lived scoped tokens. Token material is displayed once and only the SHA-256 digest is persisted.
- Dashboard cookie is HttpOnly + SameSite=Lax; set secure cookies to true behind HTTPS. Login is throttled per source IP in process (single-worker only). Admin forms enforce per-session CSRF.
- Data access uses `default_transaction_read_only=on`, statement timeout and parameterized queries. The PostgreSQL user still has `CREATE` on `public` as found by the source audit; database admin should revoke that if unnecessary.
- Logs should never include raw Authorization headers or credentials. No real customer data included in tests/source.
- API `api:read` and MCP `mcp:read` expose safe structured fields only. `api:sensitive` allows full call details when explicitly requested. UI admin detail includes sensitive data.
- For full MCP specification client auth, add OAuth 2.1 authorization server and resource metadata; this MVP's manual bearer tokens are for clients that support custom auth headers.
- Before production: IP-based login throttle store (Redis), account recovery, audited admin management, remote backups, TLS termination, CSP, explicit MCP host allowlist, security review, integration tests, retention policy.

## uv-native local development (v0.3)

- Development publishes raw PostgreSQL TCP relay on `127.0.0.1:15432` **only**. Any program on the local Windows/WSL host might attempt connection to that port, but still requires database credentials and TLS. Do not share it beyond localhost.
- Relay runs in the VPN container network namespace; PostgreSQL egress must continue to use `tun0` and firewall fail-closed rules.
- Native WSL web process binds to loopback port 8508; do not run this on a public network or expose it through a public reverse proxy.
- Developer admin SQLite database is a local file in `data/`. Previous container-based auth SQLite data/tokens are not automatically migrated; new tokens must be issued.
- `uv.lock` must be generated and committed on the workstation before pushing. CI and Docker must install with `--locked`.
- Production images built by GitHub Actions are private GHCR packages; restrict package read access and deploy immutable sha-tagged versions.
