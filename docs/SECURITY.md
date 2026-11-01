# Security deployment checklist

Do not commit `.env.app`, `.env.db`, `.ovpn` files, VPN private keys, SQLite auth data, customer previews, or call transcripts. All are in `.gitignore` and `.dockerignore`. `git status` before publish.

- Default exposure is loopback only. To expose beyond local WSL, place an authenticated TLS reverse proxy and separately configure allowed MCP Host/Origin values; never expose the current HTTP deployment on a public IP.

## Canonical HTTPS ingress (opt-in; no automatic deployment)

- Set `PANADAN_PUBLIC_ORIGIN=https://dan.panafor.com` **together with** `PANADAN_COOKIE_SECURE=true` in the private VPS `.env.app`. Invalid origins and insecure cookies fail at application startup. Do not enable until HTTPS termination is ready.
- Panadan intentionally retains Uvicorn's `--no-proxy-headers`. Only the configured canonical HTTPS origin is used for browser POST Origin checks and rendered absolute links. Client-supplied `X-Forwarded-Host`, `X-Forwarded-Proto`, and `X-Forwarded-For` are **not trusted**. Host checking is restricted to the configured public domain and explicitly named local/private diagnostic hosts.
- The reverse proxy must preserve `Host: dan.panafor.com`, terminate HTTPS, and use an isolated Docker network to reach Panadan's internal HTTP port. Never publish the upstream HTTP port on `0.0.0.0`. Since forwarding headers are ignored, per-IP rate limiting sees the proxy IP: install a trusted-edge rate limiter before public launch.
- Configure MCP separately with `PANADAN_MCP_ALLOWED_HOSTS=dan.panafor.com` and `PANADAN_MCP_ALLOWED_ORIGINS=https://dan.panafor.com`. OAuth and customer-data permissions remain independently gated.
- The existing HTTP SSH-tunnel path remains suitable for private diagnostics. A public `Secure` cookie may not function for HTTP browser login through that tunnel; use the canonical HTTPS hostname after cutover.
- Do not edit or recreate Plane's proxy or web container in this code change. Its manually installed `/intake.html` lives inside the Plane web container and requires a persistent bind mount before any Plane web upgrade. Validate the private Caddy configuration and rollback separately.
- Set a long random bootstrap password. It creates the admin account only once. After initialization, password changes require a dedicated management procedure (not supplied by this MVP).
- Use separate short-lived scoped tokens. Token material is displayed once and only the SHA-256 digest is persisted.
- Dashboard cookie is HttpOnly + SameSite=Lax; set secure cookies to true behind HTTPS. Login is throttled per source IP in process (single-worker only). Admin forms enforce per-session CSRF.
- Data access uses `default_transaction_read_only=on`, statement timeout and parameterized queries. The PostgreSQL user still has `CREATE` on `public` as found by the source audit; database admin should revoke that if unnecessary.
- Logs should never include raw Authorization headers or credentials. No real customer data included in tests/source.
- API `api:read` and MCP `mcp:read` expose safe structured fields only. `api:sensitive` allows full call details when explicitly requested. UI admin detail includes sensitive data.
- OAuth mode is an optional MCP resource server; a separate standards-compliant IdP handles login, consent and token issuance. Only RS256 JWT access tokens from the configured HTTPS JWKS issuer with exact audience, scope and expiry are accepted. OAuth mode never accepts legacy manually issued MCP tokens.
- Before production: IP-based login throttle store (Redis), account recovery, audited admin management, remote backups, TLS termination, CSP, explicit MCP host allowlist, security review, integration tests, retention policy.

## uv-native local development (v0.3)

- Development publishes raw PostgreSQL TCP relay on `127.0.0.1:15432` **only**. Any program on the local Windows/WSL host might attempt connection to that port, but still requires database credentials and TLS. Do not share it beyond localhost.
- Relay runs in the VPN container network namespace; PostgreSQL egress must continue to use `tun0` and firewall fail-closed rules.
- Native WSL web process binds to loopback port 8508; do not run this on a public network or expose it through a public reverse proxy.
- Developer admin SQLite database is a local file in `data/`. Previous container-based auth SQLite data/tokens are not automatically migrated; new tokens must be issued.
- `uv.lock` must be generated and committed on the workstation before pushing. CI and Docker must install with `--locked`.
- Production images built by GitHub Actions are private GHCR packages; restrict package read access and deploy immutable sha-tagged versions.

## v0.4 defense-in-depth (pending full deployment verification)

- the reporting database PostgreSQL: every reporting query runs in `SET TRANSACTION READ ONLY`.
  Database credentials are not available to browser JS, REST callers, or MCP clients.
- SQLite: accounts, session rotation and token revocation are intentionally writable;
  this does not give any caller write access to the reporting database.
- Capabilities: `metrics:read`, `calls:read`, `calls:sensitive`, `mcp:use`,
  `tokens:manage`, and `users:manage`, evaluated on every request. Tokens are
  owned by a user and become invalid when the user is disabled or changed.
- REST: `api:read` can be metrics-only; endpoints independently check required
  capability. `api:sensitive` is necessary for sensitive call details.
- MCP: Bearer authentication protects GET/POST/DELETE before SDK dispatch.
  Tools return only allowlisted non-sensitive columns.
- Transcript: client-side formatting only for authorized sensitive-detail users;
  original raw text remains retrievable. Text is rendered without HTML injection.
- Browser assets: Doran and Vazirmatn bundled locally in production; no external
  Google Fonts calls on pages containing business data.
- Do not expose private business data through an unauthenticated proxy or public tunnel.
- The reporting DB role `report_user` has historically shown `CREATE` on `public`;
  `READ ONLY` transactions protect this application, but the server administrator
  should revoke unnecessary CREATE privileges for stronger isolation.

## v0.6 OAuth boundary

- OAuth is **off by default**. `PANADAN_MCP_AUTH_MODE=oauth` requires explicit HTTPS issuer, JWKS URL, canonical resource URL ending `/mcp/`, and a requested scope. Misconfiguration causes startup to fail closed.
- The bearer challenge advertises RFC 9728 protected-resource metadata; Panadan does not create JWTs or authorization-server metadata.
- The admin binds the provider's **immutable subject**, not username/email, to one Panadan account. No auto-provisioning, no privilege inheritance from external token claims.
- Every MCP request rechecks the linked account's role, activation and `calls:read`, `metrics:read`, `mcp:use` permissions. Account permission changes delete links. The provider itself must manage token revocation and refresh.
- A short JWT lifetime (at most one hour) is enforced; signing keys are obtained from a preconfigured HTTPS JWKS with bounded caching. No URL supplied by the bearer token is fetched.
- OAuth alone does **not** grant sensitive call transcript access or PostgreSQL write access. The database's READ ONLY transaction guard remains unchanged.
- Remote deployment remains unsupported until hardened HTTPS origin/host policies, auditing, rate limits, the IdP consent/PKCE configuration and ChatGPT callback flow have been tested.

## Effective database-role audit

Run `./panadan.sh audit-db` on the connected WSL machine to inspect the **current** reporting account's effective CREATE/INSERT/UPDATE/DELETE/TRUNCATE privileges. This check only queries PostgreSQL catalogs in an explicit READ ONLY transaction; it never changes the source database. See `docs/READ_ONLY.md`. An earlier audit found schema CREATE rights on the reporting login, but that historical finding must be verified on the live server before claiming the account is strictly read-only. For robust least privilege use a dedicated reader role approved by the DBA, not blanket revokes on a shared production account.

## WebMCP (experimental browser integration)

WebMCP tools are registered only on an authenticated dashboard page in supporting
browsers, never at the remote MCP endpoint. They use same-origin GET requests
with browser-session permissions; the backend revalidates every request. Returned
payloads are projected onto a fixed metadata allowlist and omit transcript,
customer phone/name, and free text. A dedicated metadata-only backend endpoint
ensures sensitive database columns are not fetched just to provide an overview.
The WebMCP tool registry is aborted when the page unloads. No arbitrary SQL,
writes, external network requests or credential exposure is allowed.
Browser agents themselves have separate security considerations; test with a
trusted browser/agent before enabling against real call data.

## AI transcript permission and audit (v0.7)

- Non-admin accounts require explicit `calls:transcript:read` in addition to
  their call viewing permission. MCP callers are authenticated per request and
  their linked Panadan roles are rechecked before transcript disclosure.
- Only fixed, read-only SQL extracts bounded transcript portions. Each chunk
  is at most 6,000 characters; `offset` permits complete long transcripts
  without an arbitrary whole-conversation cap or an hourly use quota.
- Phone numbers, email addresses, links and IBANs are masked heuristically.
  Spoken sensitive information can remain: **redaction != anonymization**.
- Activity logs retain metadata (canonical endpoint or allowed MCP tool name,
  user ID, result, duration, timestamp), not request bodies or tokens. The
  admin activity screen presents 90-day aggregates and recent events. These
  logs themselves are sensitive admin data; protect SQLite backups.

## v0.7.1 transcript page-boundary hardening

- Each SQL page fetches a bounded 512-character context on both sides of the
  requested range, still through the reporting database's READ ONLY transaction.
- The returned excerpt is masked **before** clipping. Fixed-width block
  replacements preserve the original source offsets and avoid leaking halves
  of ordinary phone numbers, emails, URLs or IBANs across consecutive pages.
- This is still best-effort masking, **not anonymization**. Exceptionally long
  identifiers, names, spoken personal information and private business details
  may remain. Use explicit transcript permission and obtain the necessary
  authorization before connecting external AI providers.
- End-to-end synthetic MCP HTTP integration tests now cover initialization,
  tool listing, permissions, a successful transcript lookup, account attribution
  and immediate access revocation. No real PostgreSQL or customer data is used.
- An offset beyond the end of a transcript returns an empty terminal page.

A live, authorized end-user smoke test is still required before enabling
external-facing transcript access.

## v0.8 MCP SDK v2 trusted transport settings

- `mcp.server.mcpserver.MCPServer` (SDK v2.3.0) provides modern protocol support while preserving legacy HTTP clients.
- The MCP ASGI app is still wrapped in the authenticated bearer gate and uses explicit `stateless_http=True` and `json_response=True`; every transcript request rechecks account permissions and is audited.
- SDK v2 DNS rebinding checks are enabled, with loopback defaults and explicitly configured HTTPS Host and Origin allowlists. Do not add public wildcards or trust forwarded headers without a real proxy policy.
- Python 3.13 and Node 24 LTS are used for dev/build, with locked dependencies in both ecosystems. PR CI verifies the source tests and both Docker images before merging.
- Changing MCP runtimes **does not** implement the OAuth authorization server or approve public hosting. Continue to require HTTPS, live auth tests and a PostgreSQL reader-role audit before external access.
