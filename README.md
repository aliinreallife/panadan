# Panadan · پانادان

Private-by-design Persian RTL reporting application for an allowlisted read-only PostgreSQL reporting view: FastAPI, an authenticated dashboard, read-only REST API, and read-only MCP tools.

**Current release: v0.7 (draft)** — Vazirmatn UI, Doran Jalali date/time filters, capability-based user access, and a formatted transcript reader with an unmodified **Raw original** view.

## Requirements

- Linux or WSL2, Bash, Git and Docker/Compose.
- [uv](https://docs.astral.sh/uv/) and Python 3.12.
- Node.js 20+ and npm to build the local Doran/Vazirmatn dashboard assets.
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

Install the locked Python dependencies and local frontend assets, then start the development stack:

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
- The PostgreSQL reporting role historically had `CREATE` on `public`; ask the database administrator to revoke unnecessary privileges for defense in depth.
- User permissions are capability-based (for example metrics, call summaries, sensitive details, MCP use and user administration). MCP tokens are revocable.
- Call details show **Panadan formatted** speaker turns and an unchanged **Raw original** transcript. Ambiguous speakers are not guessed.
- MCP supports two **mutually exclusive** modes: local/manual bearer by default or RS256 JWT verification from a configured external OAuth 2.1 identity provider. The admin must explicitly link each provider subject to a locally authorized Panadan account. See `docs/MCP_SETUP.md`.
- Panadan is not an OAuth authorization server. Sign-in, consent, client registration, PKCE, refresh tokens, and issuer metadata belong to the external provider. Live ChatGPT interoperability still needs a provider plus secure HTTPS route/tunnel and end-to-end validation.

To verify that your reporting login cannot **create or change source data**, run `./panadan.sh audit-db` and follow `docs/READ_ONLY.md` for the resulting PASS/FAIL and DBA recommendations. The application runs read-only transactions, but database grants must be independently verified.

Technical details: `docs/PRD.md`, `docs/DECISIONS.md`, `docs/SECURITY.md`, `docs/STATUS.md`, `docs/TRANSCRIPTS.md`.
