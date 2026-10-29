# Panadan v0.6 status

## Delivered and merged to main

- [x] FastAPI reporting dashboard, REST API and MCP Streamable HTTP server
- [x] uv-managed Python 3.12 with committed `uv.lock`
- [x] WSL-native development with isolated Docker VPN and loopback-only PostgreSQL relay
- [x] Private GitHub repository and GitHub Actions CI
- [x] Prebuilt GHCR VPN/web images (confirm package visibility independently)
- [x] Vazirmatn Persian RTL dashboard and Doran Jalali date/time controls
- [x] Admin-managed users, capability-based read access, revocable API/MCP tokens
- [x] Explicit PostgreSQL read-only reporting transactions
- [x] Panadan formatted transcripts and unchanged raw source view
- [x] CI tests and Docker image builds pass after v0.4 merge
- [x] Installation instructions use `$HOME`, not a developer-specific directory
- [x] CI checks executable script modes

## Still to verify or implement

- [ ] Real WSL browser/UX smoke-test of v0.4 with live VPN and user permissions
- [ ] Confirm actual GHCR package visibility is Private for both web and vpn packages
- [ ] Full production image deployment on a target host, backup/restore validation
- [ ] OAuth 2.1 authorization-code/PKCE and remote MCP interoperability
- [ ] Public domain, TLS, proxy/Origin/Host security and rate limiting before public exposure
- [ ] PostgreSQL administrator revokes unnecessary CREATE privilege for reporting user
- [ ] Clarify `SoldOut`, `voice_length` and `deal_value` semantics with the source owner

The dashboard/API/MCP must remain read-only against the source reporting database. Only Panadan's separate local authentication store may write user and token records.

## v0.5 dashboard improvements

- [x] Call-type labels and source-state translations retain original raw values
- [x] Type filter uses parameterized reporting queries and values discovered by a read-only endpoint
- [x] Call detail opens with summary/analysis, keeps metadata separate and makes the long transcript last and collapsed by default
- [x] Original transcript remains available under the Raw tab once expanded
- [x] Admin-only REST API guide added to sidebar with authenticated Swagger/OpenAPI links and curl examples
- [x] Removed backend vendor branding from user-facing dashboard status text
- [ ] Browser visual QA of long Persian transcripts and the mobile layout in the live environment

## v0.6 OAuth integration

- [x] Opt-in MCP resource-server mode with RFC 9728 discovery and WWW-Authenticate challenges
- [x] Strict external RS256 access-JWT checks for signature, issuer, audience, expiry, issuance and scope
- [x] Provider subject → Panadan account binding managed by admin; roles checked on every request
- [x] Manual MCP tokens denied in OAuth mode; REST API token behavior unchanged
- [x] Account role changes revoke OAuth bindings
- [x] Offline security tests and a provider setup guide without real secrets
- [ ] Choose/configure a production identity provider supporting OAuth 2.1 PKCE and CIMD/DCR/static client
- [ ] Expose secure HTTPS identity and resource endpoints/tunnel with Host/Origin hardening
- [ ] Verify real ChatGPT OAuth consent, code exchange, callback, refresh and MCP tool discovery
- [ ] Review production auditing, rate limits, backups and key rotation before public access

## Reporting-database read-only audit

- [x] Source reporting methods issue only parameterized SELECT queries within explicit READ ONLY transactions.
- [x] Dashboard and REST reporting endpoints expose GET, and MCP exposes only the four reviewed read-only tools.
- [x] Add a non-mutating local permissions checker: `./panadan.sh audit-db`.
- [x] Add automated regression tests for read-only queries, HTTP route methods, MCP tools and simulated effective write privileges.
- [ ] Run `./panadan.sh audit-db` with the actual VPN-connected PostgreSQL login; previous audit indicated CREATE on public.
- [ ] DBA resolves unnecessary effective CREATE/write grants and verifies the account independently, preferably with a dedicated least-privilege reader.
