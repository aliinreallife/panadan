# Panadan · پنل گزارش تماس‌ها، FastAPI و MCP

**Private, read-only reporting app** for the permitted `odoo.public.vw_danix_call_info_report` PostgreSQL view. Includes a responsive Persian RTL dashboard, API tokens, and MCP Streamable HTTP with separately scoped bearer tokens. **All access runs through the existing isolated OpenVPN container**; Windows and ordinary WSL traffic remain untouched.

## Why normal Docker build failed

Your `registry-1.docker.io` DNS/HTTPS connection timed out before FastAPI was even built. It is a **Docker Desktop registry networking** error, not an application or PostgreSQL error. The normal build (`./panadan.sh up`) needs Docker Hub access. Use `up-local` instead when the two `danf-v2-*` images are already in Docker Desktop's local image store.

## Migrate from existing DANF Hub

```bash
cd ~
unzip /mnt/c/Users/ali/Downloads/panadan-repository.zip
cd ~/panadan
./migrate-from-danf.sh ~/danf-hub
nano .env.app                  # PANADAN_ADMIN_PASSWORD=unique-14+-character-password
(cd ~/danf-hub && docker compose down)  # only if its old VPN still runs
./panadan.sh diagnose
./panadan.sh up-local          # reuses the local DANF v2 images; no Docker Hub pulls
```

The source app is unchanged; new credentials files are copied privately and never committed. `up-local` runs `pip download` from **WSL** to populate `wheelhouse/` if empty. If WSL PyPI access is also blocked, run `./panadan.sh wheels` on a working network or populate the wheelhouse separately before retrying. `wheelhouse/` stays ignored by Git.

If Docker Hub works again, `./panadan.sh up` uses the original Dockerfiles and builds normally.

**Dashboard:** http://localhost:8508/login  
**API:** http://localhost:8508/api/v1/calls  
**MCP:** http://localhost:8508/mcp/ (bearer token required)

```bash
./panadan.sh status
./panadan.sh test
curl -fsS http://localhost:8508/healthz
./panadan.sh logs
./panadan.sh down
```

## API and MCP authentication

- Dashboard: private admin account from `.env.app`, HttpOnly session cookies, CSRF protection for form actions.
- API: scoped expiring `api:read` bearer token. Only `api:sensitive` tokens may request customer names, phones, call summaries, and transcripts through the designated detail endpoint.
- MCP: separate expiring `mcp:read` bearer token. No raw SQL, customer contact details or transcripts. Four tools: `list_recent_calls`, `get_call_summary`, `get_call_metrics`, `get_available_states`.
- Issue or revoke all API/MCP tokens in `/dashboard/tokens` after signing in.

`/docs` is available after dashboard login. Tokens are shown only at creation and only token hashes are stored.

## Safety constraints

- Read-only PostgreSQL transaction and timeout per query; SQL bound to an allowlisted reporting view.
- Database credentials and OpenVPN files live locally in ignored `.env.db` and `vpn/`.
- Browser UI is bound to `127.0.0.1:8508` only; do not expose it to the internet without hardened proxy/TLS, host controls and OAuth support for remote MCP clients.
- Existing PostgreSQL grants, network rules and VPN restrictions remain in effect. Other databases will still be blocked by `pg_hba.conf`.
- Local API/MCP static bearer tokens are **not** OAuth 2.1: some remote MCP clients require OAuth and cannot connect until it is implemented.

## Testing

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest -q
python3 -m compileall -q server tests
bash -n panadan.sh migrate-from-danf.sh
```

Tests use synthetic data. Do not commit call exports or customer records.

## Create the private GitHub repository

```bash
cd ~/panadan
gh auth status
gh repo create aliinreallife/panadan --private --source=. --remote=origin --push
```

The ZIP contains a local Git repo with an initial commit. This does not mean the remote GitHub repository was created.

See `docs/PRD.md`, `docs/SECURITY.md`, `docs/DECISIONS.md`, and `docs/STATUS.md`.
