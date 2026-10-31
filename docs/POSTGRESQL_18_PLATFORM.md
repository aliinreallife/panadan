# Panadan-owned PostgreSQL 18.6 stack (optional, **not deployed**)

This is an **opt-in, separately owned database** for Panadan's planned
multi-source ingestion and processing platform. It does **not** replace,
upgrade, write to, migrate, or otherwise touch the existing remote Odoo
PostgreSQL server behind OpenVPN. The current dashboard/REST/MCP still read
the existing Odoo view, and auth/audit remain in separate SQLite.

## Chosen version

- Stable PostgreSQL **18.6** as of 2026-10-31. PostgreSQL 19 is still
  RC1 and not recommended for production.
- The official Docker image is pinned to
  `postgres:18.6-alpine3.24@sha256:10a5c69a83035ab5239f5620d708520e8b28f5aa1f2b20143e6024532edadfb5`.
  The pinned **multi-platform manifest digest** prevents the tag silently
  changing. Upgrade it deliberately for later security/minor updates.
- Both CI's isolated disposable test DB and the optional platform
  Compose service use the **same image**.
- PostgreSQL 18 changed its default Docker `PGDATA` to
  `/var/lib/postgresql/18/docker`. Our named volume mounts
  **`/var/lib/postgresql`**, not the old `/var/lib/postgresql/data`.
  Never retarget an existing volume or switch major versions in place
  without verified backups and a real `pg_upgrade` or dump/restore plan.

## Optional local platform database (WSL + Docker)

No database is started automatically by `./panadan.sh dev`,
`./panadan.sh up`, or CI. This is an **independent** Docker Compose
project and an empty database by default.

1. In the main repository checkout, create the ignored local env file:
   ```bash
   cd ~/panadan
   cp .env.platform.example .env.platform
   chmod 600 .env.platform
   ```
2. Edit `.env.platform` and set
   `PANADAN_PLATFORM_DB_PASSWORD` to a unique, strong random secret.
   Do **not** use or copy the Odoo reporting password, nor paste the
   platform password into chats, screenshots or GitHub.
3. Explicitly start and verify only the platform DB:
   ```bash
   docker compose --env-file .env.platform -f compose.platform.yaml up -d
   docker compose --env-file .env.platform -f compose.platform.yaml ps
   docker compose --env-file .env.platform -f compose.platform.yaml exec -T db \
     psql -U panadan_owner -d panadan -Atc 'SHOW server_version;'
   ```
   The official Docker image may require a first-time download. Port
   **127.0.0.1:15433** is the default; the existing VPN source relay
   continues on **127.0.0.1:15432**. The database is NOT public.
4. Optionally initialize the **empty owned database only**:
   ```bash
   docker compose --env-file .env.platform -f compose.platform.yaml exec -T db \
     psql -U panadan_owner -d panadan -v ON_ERROR_STOP=1 \
     < database/migrations/001_multisource_foundation.sql
   ```
   The schema creates tables and **disabled** source registry entries.
   It never triggers source synchronization or copies customer records.
   Do not run this against the Odoo source or the auth SQLite.
5. Stop without deleting data:
   ```bash
   docker compose --env-file .env.platform -f compose.platform.yaml down
   ```
   **Never add `-v` to `down`** for a database containing records.
   The named Docker volume survives an ordinary stop/start.

### Backup and security requirements

This setup is a **local development/pilot service**, not a hardened
multi-user production deployment. Before allowing actual customer data:
set a documented retention/deletion policy, storage encryption,
dedicated restricted database roles, tested encrypted off-host backups,
monitoring, restore rehearsals, and access control across
dashboard/REST/MCP. The `panadan_owner` bootstrap account has
database ownership privileges and must **not** be used for the runtime
read-only dashboard role. Compose environment passwords can be visible
to authorized Docker administrators; production should use a secrets
manager or equivalent supported runtime.

When rotating credentials on a **nonempty** PostgreSQL volume,
changing `.env.platform` alone will not change the existing database
account password; use an approved role/secret rotation procedure.

## Synthetic integration tests

From a worktree with the Odoo sync adapter:

```bash
cd ~/panadan-sync-test
git fetch origin
git switch --detach origin/feat/updated-at-only-odoo-sync-adapter
bash tools/test-platform-integration.sh
```

This creates and destroys a **separate disposable** `panadan_ci`
PostgreSQL database on a random loopback port. It never connects to
Odoo or to `compose.platform.yaml`, and it uses synthetic data only.
PostgreSQL 18 is checked in the integration suite. Regular local Python
and Node tests still work without database credentials.

## Important upgrade boundaries

- This only upgrades the **new** Panadan-owned platform image baseline
  and the synthetic test database. The remote Odoo server's version is
  owned by its administrator; Panadan does not and must not upgrade it.
- No upgrade of Python, Node, FastAPI, MCP, VPN or SQLite is implied
  by the PostgreSQL version change.
- No automatic data import, sync scheduler, source-table migration or
  report cutover is part of this change.
- Once the source supports a reliable `updated_at` (or
  `sync_updated_at`) and data retention is approved, a guarded pilot
  connector may be enabled in a separate release.

Source:
- https://www.postgresql.org/docs/release/
- https://hub.docker.com/_/postgres (official PostgreSQL 18 PGDATA change)
