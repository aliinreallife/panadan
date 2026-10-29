# Panadan · پانادان

Private Persian RTL call-report dashboard, authenticated FastAPI REST API and read-only MCP endpoint backed by **only** the permitted PostgreSQL view `odoo.public.vw_danix_call_info_report`.

## What changed in v0.3

- **uv-first**: `pyproject.toml`, locked sync, `.python-version`, `uv run` and GitHub Actions with uv. System `pip` is not required.
- **Local development without Docker Hub builds**: `uv run` starts FastAPI in WSL, while Docker **only** starts the isolated OpenVPN tunnel plus a localhost-only TCP relay to PostgreSQL.
- No `wheelhouse/`, no per-start pip or wheel downloads, no `Dockerfile.web.local`, no `up-local` workaround.
- **Production** is two prebuilt GHCR images, built in GitHub Actions, deployed using `compose.prod.yaml`. Docker Compose does not build on the deployment host.
- Auth: dashboard admin session, separate revocable scoped API and MCP bearer tokens. MCP is still manual-bearer rather than OAuth 2.1. Keep local-only.

### A lockfile note

The ZIP **does not contain a `uv.lock`**, because dependency-index access was unavailable during packaging and a fabricated lockfile would be unsafe. Your first `./panadan.sh setup` runs `uv lock` on WSL and creates a real reproducible lockfile; **commit `uv.lock` to Git** before pushing. All subsequent commands use `--locked`, including CI and Docker builds. Initial uv dependency download requires WSL access to the Python package registry. Future runs reuse the uv cache.

## Recommended install — next to old Panadan, no overwrites

```bash
cd ~
unzip /mnt/c/Users/ali/Downloads/panadan-uv.zip
cd ~/panadan-uv
./migrate-from-danf.sh ~/panadan
nano .env.app                      # PANADAN_ADMIN_PASSWORD=your-unique-14+-character-password
./panadan.sh diagnose
./panadan.sh setup                # resolves once, generates uv.lock, installs dependencies
# Stop previous Panadan Docker web/VPN first to avoid conflicting VPN sessions:
(cd ~/panadan && docker compose down)  # if previous app is running
./panadan.sh dev                  # dashboard at http://localhost:8508/login
```

Note: `./panadan.sh dev` stays attached to your terminal (Ctrl+C stops the local web server); the VPN services remain available until `./panadan.sh vpn-down`. Your **old `~/panadan` remains unchanged**. Keep the new directory or rename it only after verifying the new version.

**Local dashboard:** http://localhost:8508/login  
**API:** http://localhost:8508/api/v1/calls  
**MCP:** http://localhost:8508/mcp/ (separate MCP token)

### Quick commands

```bash
./panadan.sh setup             # install/update locked dependencies (does not start app)
./panadan.sh dev               # start VPN, relay and FastAPI through uv
./panadan.sh vpn-up            # VPN and DB relay only
./panadan.sh vpn-down          # stop dev VPN/relay
./panadan.sh test              # unit tests (synthetic data only)
./panadan.sh status            # container states
./panadan.sh logs              # VPN/relay logs
```

### Architecture

```text
Windows + WSL                       Docker private network

FastAPI + MCP (uv run)                 OpenVPN (tun0)
    |                                      |
    +-- localhost:15432 --> TCP relay ------> PostgreSQL 192.168.3.9:5432
        (host loopback only)     (shared VPN namespace; fail-closed DB egress)
```

**Security:** `compose.dev.yaml` publishes the relay on `127.0.0.1` only, never on external interfaces. It is a raw PostgreSQL TCP forwarder protected by existing database credentials/SSL, not an authenticated HTTP proxy. Any local program could attempt to connect to the relay, but must still authenticate to PostgreSQL. Never publish port 15432 publicly or run the dev Compose file on a shared untrusted machine. The FastAPI app is likewise bound to `127.0.0.1`. Its admin detail route can expose personally identifying call data; never upload reports or transcripts to GitHub.

### Production workflow

1. Run `./panadan.sh setup` so a real `uv.lock` exists; commit it. Review `docs/SECURITY.md` before deployment.
2. Publish a **private** repository (`gh repo create aliinreallife/panadan --private --source=. --remote=origin --push`) only after checking no `.env`/VPN/data files are staged.
3. GitHub Actions runs tests from the lockfile, builds VPN/web images, pushes `ghcr.io/<owner>/panadan-{web,vpn}:main` and `:sha-<commit>` to GHCR. Ensure private GHCR package pull permissions are configured.
4. With GHCR access on the target host, copy locally your private `.env.app`, `.env.db` and `vpn/` files, then run `./panadan.sh up`. For reproducible production deployment, set `PANADAN_WEB_IMAGE` and `PANADAN_VPN_IMAGE` in `.env.app` to **sha-tagged** images.
5. Dashboard port is bound to loopback; for remote access deploy a proper authenticated TLS proxy, host/Origin protection, audit logging, and full OAuth support as applicable for remote MCP clients.

If Docker Hub/GHCR DNS is broken locally, **local dev still works** using your existing `danf-v2-...` images. Production pulling from GHCR requires registry connectivity (or preloading the built images through `docker load`).

### Authentication and data permissions

Dashboard password uses hashed local storage in `data/` and HttpOnly CSRF-protected sessions; API `api:read` and `api:sensitive` scopes are separate from MCP `mcp:read`. No arbitrary SQL tool, source write operations, public exposure or raw transcript MCP tool. Queries use parameter binding and PostgreSQL read-only sessions. This is not an OAuth authorization server; remote ChatGPT MCP integration may require additional auth work.

### Development guidelines

Use `uv add <package>`, `uv add --dev <package>`, `uv lock`, `uv sync --locked`, `uv run --locked pytest -q`. Do not use `python3 -m pip` or manually update `requirements.txt`. Keep `pyproject.toml` and `uv.lock` together. CI fails when lock is absent/outdated.

Project decisions and hardening tasks: `docs/PRD.md`, `docs/DECISIONS.md`, `docs/SECURITY.md`, `docs/STATUS.md`.
