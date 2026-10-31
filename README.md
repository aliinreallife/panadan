# Panadan · پانادان

Private-by-design Persian RTL reporting application for an allowlisted read-only PostgreSQL reporting view: FastAPI, an authenticated dashboard, read-only REST API, and read-only MCP tools.

**Current release: v0.8 (preproduction)** — Vazirmatn UI, Doran Jalali date/time filters, capability-based user access, and a formatted transcript reader with an unmodified **Raw original** view.

## Requirements

- Linux or WSL2, Bash, Git and Docker/Compose.
- [uv](https://docs.astral.sh/uv/) and Python 3.13 (uv can install the required Python version).
- Node.js 24 LTS and npm to build the local Doran/Vazirmatn dashboard assets.
- An authorized PostgreSQL reporting account and a private OpenVPN profile.
- For the WSL-local development workflow, the two **already-built** Docker images `danf-v2-vpn:latest` and `danf-v2-python:latest`. The dev workflow deliberately does not pull/build Docker Hub base images.

Do **not** upload real VPN credentials, environment files, SQLite auth data, customer records or transcripts to GitHub.

## Install on a new machine

Clone the **private** repository using a GitHub account with access:

```bash
gh auth login                       # only if not already logged in
gh repo clone aliinreallife/panadan "$HOME/panadan"
cd "$HOME/panadan"
```

If migrating from an existing Panadan/DANF installation, copy the private configuration without overwriting existing destination files:

```bash
./migrate-from-danf.sh /path/to/previous-installation
```

Otherwise, create local configuration from the examples:

```bash
cp .env.app.example .env.app
cp .env.db.example .env.db
mkdir -p vpn
# Securely place your OpenVPN profile at vpn/client.ovpn
# Edit .env.app and .env.db with your OWN credentials and settings.
chmod 600 .env.app .env.db vpn/client.ovpn
```

Set `PANADAN_ADMIN_PASSWORD` to a unique value of at least 14 characters. Review `docs/SECURITY.md` before any deployment.

Install Python 3.13 with `uv python install 3.13` if needed. Install the locked Python dependencies and local frontend assets, then start the development stack:

```bash
./panadan.sh setup
./panadan.sh test
./panadan.sh dev
```

Dashboard: <http://127.0.0.1:8508/login>. API: `/api/v1/`. MCP: `/mcp/` (requires a separate MCP bearer token).

`dev` runs the FastAPI/MCP server via uv in WSL and runs only the VPN and a **localhost-bound** PostgreSQL TCP relay in Docker. The VPN routing stays inside the Docker VPN container namespace. Run `./panadan.sh vpn-down` to stop the Docker tunnel afterward.

### Update an existing installation

You do not need to unpack ZIPs again:

```bash
cd "$HOME/panadan"
git switch main
git pull --ff-only
./panadan.sh setup
./panadan.sh test
./panadan.sh dev
```

`git pull --ff-only` advances a local branch **only if it can fast-forward**. If your history has diverged, it stops instead of creating an unexpected merge commit. It does not delete divergent local commits.

If a checkout has lost the executable file mode, `bash ./panadan.sh setup` can run the Bash script without executing it directly. The repository and CI now track/check its executable permission.

## Commands

| Command | Purpose |
| --- | --- |
| `./panadan.sh setup` | `uv sync --locked --dev`, npm dependencies and frontend assets |
| `./panadan.sh dev` | Local WSL FastAPI with isolated Docker VPN relay |
| `./panadan.sh test` | Python unit/integration tests (synthetic test data) |
| `./panadan.sh vpn-up` / `vpn-down` | Manage only the local VPN/relay containers |
| `./panadan.sh status` / `logs` | Inspect the local Docker services |
| `./panadan.sh audit-db` | Read-only audit of the effective PostgreSQL role permissions (requires local VPN) |
| `./panadan.sh diagnose` | Check uv and available development images |
| `./panadan.sh up` / `down` | Run or stop prebuilt production GHCR images |

## Deployment and private GHCR images

GitHub Actions builds `panadan-vpn` and `panadan-web` and publishes tags `:main` and `:sha-<full-commit-sha>` under `ghcr.io/aliinreallife/`. **The GitHub repository and GHCR packages have separate visibility settings.** New GHCR packages default to private, but confirm **both** package visibility settings in [GitHub Packages](https://github.com/aliinreallife?tab=packages) before relying on privacy.

To pull a private package, authenticate Docker with an authorized token that has `read:packages` access (such as a classic PAT), then use `docker pull` or `./panadan.sh up`:

```bash
# Use a token from your secret store; do not paste it in the command or save it in Git.
# Example: if gh's existing token has read:packages:
gh auth token | docker login ghcr.io -u "$(gh api user --jq .login)" --password-stdin

docker pull ghcr.io/aliinreallife/panadan-vpn:main
docker pull ghcr.io/aliinreallife/panadan-web:main
```

If your `gh` authentication lacks `read:packages`, grant the needed scope or use a suitable classic PAT via `docker login --password-stdin`. The `:main` tag moves with releases; prefer a specific `sha-` tag (or digest pin) for repeatable deployments. Set `PANADAN_VPN_IMAGE` and `PANADAN_WEB_IMAGE` in your local `.env.app` to select those images.

`compose.prod.yaml` publishes dashboard port 8508 on **127.0.0.1 only**. The application is not ready to be exposed publicly: TLS termination, secure cookies, proxy host/origin validation, audit/abuse controls, and OAuth 2.1 for hosted MCP clients still require implementation and security review. A public domain is **not** required for local development.

## Experimental WebMCP browser integration

For WebMCP-capable Chromium browsers, the authenticated dashboard optionally
registers **three browser-native read-only tools** using
`document.modelContext.registerTool()`: aggregate metrics, paginated call
metadata, and a single metadata-only call overview. This is separate from the
remote `/mcp/` endpoint; it is not a ChatGPT OAuth connection.

WebMCP is an early-preview browser feature. Unsupported browsers ignore it.
Permissions are enforced server-side, no third-party JavaScript is loaded, and
no transcript or customer-identifying data is returned to the page tools.
See `docs/WEBMCP.md` for testing steps and constraints.

## Operator profiles and directory

Use the operator filter on the dashboard, or click an operator name in the
call table to open `/dashboard/operator?name=...` for the operator's own
statistics and calls. `/dashboard/operators` lists known operators and lets
admins assign local destinations and teams, with `نامشخص` for unassigned
values. These labels can be used as additional dashboard, REST, MCP and WebMCP
filters without modifying the source reporting view.

**Team/destination filtering is not team-based authorization.** Restricted
access by destination, team and operator needs stable source operator IDs and
a single verified scope check across all reading surfaces. See
`docs/OPERATOR_SCOPES.md`.

## Activity & AI transcript access

Admin **فعالیت کاربران**: `/dashboard/activity` provides an RTL dashboard with
user, API, MCP and authentication activity, daily charts, error-only filters
and a searchable recent-event list. Logs store **metadata only** (account,
canonical endpoint or MCP tool name, result status and duration)—never tokens,
request bodies, query parameters or call text. Activity events are retained
for 90 days in the separate local SQLite store.

AI transcript access is **disabled for non-admin users unless explicitly granted**
`calls:transcript:read` alongside their call-reading permission. Approved
MCP and WebMCP clients may request redacted transcript chunks (up to 6,000
characters **per response**, not per conversation); each response provides the
next offset until the call is complete. No arbitrary hourly total or whole-call
limit is imposed. Every transcript retrieval is recorded without its text.
Masking is best-effort and **does not guarantee anonymization**.

The source reporting database remains strictly **read-only at the application
level**. An external IdP and HTTPS endpoint are still required to complete
the one-click OAuth consent experience.

## Data access and security

- Dashboard/API/MCP can query only explicit read-only PostgreSQL transactions and allowlisted reporting columns; they cannot execute arbitrary user SQL or modify the reporting database.
- Panadan's own SQLite store *does* write accounts, permissions, sessions and token records. This is independent of the reporting database.
- A 2026-10-31 privilege audit confirmed that PostgreSQL `report_user` inherits `CREATE` on `public` from `PUBLIC`. The app still enforces read-only transactions; ask the DBA to review dependencies and move to a true least-privilege reader without blindly revoking shared production grants.
- User permissions are capability-based (for example metrics, call summaries, sensitive details, MCP use and user administration). MCP tokens are revocable.
- Call details show **Panadan formatted** speaker turns and an unchanged **Raw original** transcript. Ambiguous speakers are not guessed.
- MCP supports two **mutually exclusive** modes: local/manual bearer by default or RS256 JWT verification from a configured external OAuth 2.1 identity provider. The admin must explicitly link each provider subject to a locally authorized Panadan account. See `docs/MCP_SETUP.md`.
- Panadan is not an OAuth authorization server. Sign-in, consent, client registration, PKCE, refresh tokens, and issuer metadata belong to the external provider. Live ChatGPT interoperability still needs a provider plus secure HTTPS route/tunnel and end-to-end validation.

To verify that your reporting login cannot **create or change source data**, run `./panadan.sh audit-db` and follow `docs/READ_ONLY.md` for the resulting PASS/FAIL and DBA recommendations. The application runs read-only transactions, but database grants must be independently verified.

Technical details: `docs/PRD.md`, `docs/DECISIONS.md`, `docs/SECURITY.md`, `docs/STATUS.md`, `docs/TRANSCRIPTS.md`.

## Odoo source updates + new calls (adapter prepared)

The multi-source foundation now has a **read-only, opt-in** Odoo view
adapter that covers (1) bounded initial history backfill, (2) ongoing
**new calls** detected by increasing `id`, and (3) edits to **existing
calls** detected by a verified `updated_at` or `sync_updated_at`.
Every cursor is durable and local ingestion stays transactional.
The initial update cursor must be seeded **before** starting backfill.

The current live view **does not yet expose** either update field. No
live ingestion, scheduling, customer-data copying, schema changes or
dashboard cutover are performed by these libraries. See
[Odoo updated-at sync](docs/ODOO_UPDATED_AT_SYNC.md) for source
requirements, limitations (especially deletions), synthetic CI tests
and the steps required before enabling a pilot.

## Multi-source platform foundation (opt-in)

Panadan's long-term architecture is a separate PostgreSQL data platform with
a source registry, versioned raw JSONB records, durable processing jobs,
versioned facts, and atomic per-source sync checkpoints. An initial schema and
synthetic-only ingestion/processing libraries are now available in
[Platform Foundation](docs/PLATFORM_FOUNDATION.md). The existing auth SQLite,
Odoo read-only reporting path, API and MCP are **unchanged**. No source
connector, scheduler, raw customer import, database deployment or Redis cache
is enabled by this change.

GitHub CI tests the new path against a disposable PostgreSQL database with
synthetic source payloads. **Do not** apply the migration to Odoo or ingest
personal data before agreeing on the source update/delete feed and retention.

## Assess local reporting mirror readiness (read-only)

Before moving dashboard/REST/MCP reads to a private Panadan PostgreSQL mirror,
inspect the existing Odoo reporting view's ability to support incremental
updates and deletes. **This command copies no records** and does not run a
full row count:

```bash
./panadan.sh audit-sync --sample 100
```

The result includes visible change-marker candidates and only aggregate
samples/optional query-planner estimates. If the VPN is unstable, try
`./panadan.sh audit-sync --sample 0 --no-explain`. See
[local reporting sync architecture](docs/LOCAL_REPORTING_SYNC.md) for
bounded keyset backfill, transactional upsert checkpoints, reliable
edit/delete detection, stale-data handling and when Redis is useful.
No mirror or scheduler is enabled by this command.

## Audit unknown source fields safely

The reporting view has 36 known columns, but not every column is reliable or
populated. To inspect structure and bounded aggregate statistics **without
printing customer names, phone numbers or transcripts**, run:

```bash
cd ~/panadan
./panadan.sh audit-fields --limit 300 --offsets 0,1000,5000
```

This requires the same WSL VPN as `audit-db` and returns JSON with only
metadata, counts, date bounds and numeric plausibility checks. Offsets follow
the reporting row ID, not necessarily the call date. Smaller samples may help
avoid the source database's 12-second statement timeout:

```bash
./panadan.sh audit-fields --limit 100 --offsets 0
```

After the initial audit, the targeted safe source-semantic check can compare
`call_time` with `create_date` under two timezone assumptions and classify
`tellnum` lengths without printing phone numbers:

```bash
./panadan.sh audit-semantics --limit 100 --offsets 0,1000,5000
```

Like `audit-fields`, it only reads the allowlisted reporting view in
explicit READ ONLY transactions. It produces aggregate metrics, not raw
customer records, and does not change date/phone fields used by the app.
The 900-row first-audit findings and confidence limits are documented below.

See [Source data dictionary](docs/DATA_DICTIONARY.md) for the confirmed units,
unverified call-time/phone/date/status semantics, and the prerequisites for
stable numeric-ID operator authorization. **Do not turn metadata filters into
team/department security permissions** before the cross-surface RBAC checks
described in [Operator scopes](docs/OPERATOR_SCOPES.md).

## Troubleshoot PostgreSQL connection timeouts

A healthy VPN Docker container does **not** prove that PostgreSQL itself
accepts connections. The current VPN health check validates the `tun0`
interface and that the database host route traverses the tunnel, while
`pgrelay` opens a separate outbound TCP connection for each client.

If `./panadan.sh audit-fields`, the dashboard or another database query
fails with `ConnectionTimeout`, diagnose the actual path first:

```bash
cd ~/panadan
./panadan.sh diagnose-db
./panadan.sh logs
```

The diagnostic checks (1) the VPN route to the DB IP, (2) PostgreSQL's TCP
readiness from inside the VPN namespace using `pg_isready`, (3) local
loopback relay acceptance, and (4) a real, explicit read-only PostgreSQL
`SELECT 1` using the configured credentials and SSL settings.

Interpretation:

- **Local relay TCP fails:** inspect the `pgrelay` container, Docker
  port mapping and WSL Docker integration.
- **Local relay works but VPN-side `pg_isready` fails:** inspect VPN
  reachability, the database listener and firewall with the DB/VPN operator.
  A tunnel route check by itself is not sufficient.
- **`pg_isready` succeeds but `SELECT 1` fails:** check SSL requirements,
  credentials, `pg_hba.conf`, server limits and relay logs.
- **All checks pass but `audit-fields` fails:** retry a small bounded sample
  (`--limit 100 --offsets 0`) and investigate server-side query execution,
  statement timeouts and view complexity.

### Dashboard loads but metrics, calls and filters all return 503

The dashboard HTML and static assets can load even when its reporting queries
cannot reach PostgreSQL. A healthy VPN container means only that its tunnel
interface and route were detected; it does not prove database reachability.

Run `./panadan.sh diagnose-db` from **another WSL terminal** while
`./panadan.sh dev` keeps serving the dashboard. If the read-only
`SELECT 1` succeeds but the reporting endpoints still fail, inspect the
**WSL server terminal** after requesting `/dashboard/data` again.

The server logs a restricted diagnostic such as
`Reporting backend failed type=ConnectionTimeout SQLSTATE=unknown`
or `... type=UndefinedColumn SQLSTATE=42703`.
Only the exception class and validated five-character SQLSTATE are logged:
no SQL, query parameters, credentials, hostnames, or customer records.
All unexpected reporting failures still return the existing generic HTTP
503 to the browser.

Typical categories: SQLSTATE `08xxx` indicates a connection failure;
`57014` indicates a canceled query (possibly a statement timeout);
`42xxx` indicates a SQL/schema error; `42501` indicates inadequate
privileges. Do not assume a 503 proves the VPN is down.

These safe logs are available **after restarting the WSL FastAPI process**
with the new code. No need to restart Docker or the remote database just
to enable logging. Do not share full VPN logs or environment secrets.

### Reload a previously running relay after updating Panadan

Panadan bind-mounts the **stable `./tools` directory** into the relay
container, keeping generated Docker Desktop/WSL mount references independent
of individual files replaced by Git.

An already-running relay's Python process will not reload `pgrelay.py`
after `git pull`. **Recreate only the relay** to pick up the updated code
and mount configuration, without restarting the VPN:

```bash
./panadan.sh relay-recreate
./panadan.sh diagnose-db
```

Equivalent explicit Compose command:

```bash
docker compose --env-file .env.app -f compose.dev.yaml up -d --no-deps --force-recreate pgrelay
```

If an older container fails with an OCI mount error referencing
`/run/desktop/mnt/host/wsl/docker-desktop-bind-mounts/...` and
`/relay/pgrelay.py`, it still holds a stale **single-file** bind source.
A forced recreation under the new directory mount is the preferred
recovery. Do not run `docker compose down -v`, delete Docker volumes,
or change VPN secrets to address this mount failure.

This only fixes local container startup. It **does not** make unreachable
PostgreSQL `192.168.3.9:5432` available or resolve VPN keepalive issues.

### When the tunnel is up but PostgreSQL gives no response

A confirmed route such as `dev tun0` proves the local routing decision,
not remote reachability. Repeating `Inactivity timeout (--ping-restart)`
in OpenVPN logs is an **additional potential tunnel health symptom**; it is
not definitive proof of a PostgreSQL or VPN-server defect.

If `pg_isready` from the VPN container says `no response`, investigate
with the VPN/DB operator: whether `192.168.3.9:5432` is currently
listening, VPN-server forwarding to the private database subnet, firewall
rules allowing the VPN client subnet, return routing, and OpenVPN keepalive
reachability. Avoid changing firewall rules or rebooting production services
until an administrator has confirmed the cause. Do not retry larger audits
until the basic `SELECT 1` diagnostic succeeds.

Neither the diagnostic nor the audit writes to Odoo. These commands must not
print passwords, DSNs, customer information or transcripts. Do not paste
private VPN client configuration, PostgreSQL logs containing connection
strings, or `.env.*` secrets in GitHub issues or chats.

## Preproduction SDK v2 migration

Panadan now uses official `mcp==2.3.0` (locked) and `MCPServer`, with Python 3.13, Node 24 LTS, refreshed FastAPI/psycopg dependencies and pinned, reproducible npm dependencies. The `FastMCP` v1 class no longer exists in the v2 SDK. The MCP HTTP route remains `/mcp/`, preserving old clients while supporting the newer 2026 MCP protocol. The transcript permission and read-only constraints are unchanged. PR CI builds both Docker images before merge.

The v2 MCP server validates request origins/hosts. For a trusted HTTPS proxy or tunnel, explicitly set `PANADAN_MCP_ALLOWED_HOSTS` and `PANADAN_MCP_ALLOWED_ORIGINS` as described in `docs/MCP_SETUP.md`. These allowlists **do not** implement OAuth login/consent or make the server safe to publish without proper TLS and additional security checks.

The 2026-10-31 300-row semantic follow-up strongly correlated `call_time` with
Tehran-local seconds since midnight and `create_date` with UTC-naive record
creation (~2 minutes later). All sampled `tellnum` values were 1–4-digit
codes, **not customer phone numbers**. Source-owner verification remains
required before displaying call-clock timestamps or using internal codes.
See `docs/DATA_DICTIONARY.md` for evidence and limitations.
