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

## Recommended safe local bootstrap

The easiest way to initialize **only Panadan's own database** uses the
project's dedicated management CLI. No system PostgreSQL or separate `psql`
Docker image is required; the official `postgres:18.6-alpine3.24` image
already includes `psql`, `pg_dump` and `pg_restore`.

```bash
cd ~/panadan
./panadan.sh platform-db setup   # Once: generate private .env.platform (mode 600)
./panadan.sh platform-db up      # Start only the separate PostgreSQL 18 service
./panadan.sh platform-db init    # One transaction; additive, safe to repeat
./panadan.sh platform-db check   # Verify major version, 7 schema tables, metadata
./panadan.sh platform-db backup  # Optional: custom-format local dump, mode 600
./panadan.sh platform-db down    # Stop only this DB; NEVER remove its volume
```

`setup` refuses to replace existing credentials and generates a unique
cryptographic password. The setup command does not require Docker;
other database commands require Docker Compose v2. `up` requires a
valid `.env.platform` file whose permissions exclude group and world
access. Every database-management command checks that it is operating
on PostgreSQL major version 18. The `init` command verifies all seven
core tables exist after executing the schema within one SQL transaction;
it creates **no source connectors, imports, users, or schedules**.

The local database binds only to the configured loopback port (default
15433). Running `platform-db` does not start the VPN relay, read
`.env.db` / `.env.app`, or contact Odoo.

`backup` writes a PostgreSQL custom-format dump under
`data/platform-backups/` (Git-ignored; directory mode 700, file 600),
then verifies that `pg_restore --list` can read its directory. This is
a basic archive-format check, **not** a full restore verification and
**not** a remotely stored or encrypted backup. Backups of actual data
may contain personal information. Arrange encrypted off-host backups
and periodic *isolated* restore drills before ingesting real records.

To validate restore behavior **without any real data or secrets**:

```bash
bash tools/test-platform-integration.sh
```

The Docker integration helper now applies the migration twice on a
disposable PG18 DB, inserts synthetic metadata, restarts PostgreSQL,
dumps it, restores into another disposable database, and verifies the
metadata survived. It removes the test container and its temporary
backup automatically. This does not replace a production backup drill.

`down` retains the persistent named volume. Never run
`docker compose down -v` against a database holding user records.
`pg_dump` does not back up external files, nor guarantee a recovery
point for concurrent source writes once ingestion is enabled.

## Restricted runtime roles (opt-in)

The Docker bootstrap account `panadan_owner` is a privileged
administrator. Never give its password to the ingestion worker, reporter,
dashboard or MCP layer.

To provision two separate **non-admin LOGIN roles** on the independently
owned PostgreSQL 18 instance:

```bash
cd ~/panadan
./panadan.sh platform-db roles-setup  # one-time random credentials, never printed
./panadan.sh platform-db roles-apply  # explicit and transactional grants
./panadan.sh platform-db roles-check  # fail if restricted privilege invariants drift
```

`roles-setup` generates a new ignored `.env.platform.roles` with two
different 64-character random secrets (mode 600); it refuses overwriting.
`roles-apply` requires the active DB to be exactly `panadan` running
PostgreSQL 18. It applies only to the separate platform database,
not the existing Odoo source or its VPN. `roles-check` exits nonzero if
an expected restriction is missing or a sensitive table privilege appears;
treat a failed check as a release blocker. It is a baseline permission audit,
not a substitute for a full DBA review.

- The source-enablement check uses `panadan_ingest.lock_source_for_ingest(text)`, an explicitly granted, owner-executed, fixed-query row lock. PostgreSQL requires UPDATE privilege for direct `SELECT ... FOR SHARE`, so granting direct source-registry UPDATE to the runtime writer would violate the security boundary. `roles-apply` reapplies the additive foundation migration to install this helper on databases initialized before it existed.\n- `panadan_ingest_writer` can read source enablement and write only
  the current records, revisions, jobs, facts and checkpoints needed by
  the ingestion/processing libraries. It **cannot** create tables,
  register sources or enable a disabled source, and cannot delete raw history.
- `panadan_report_reader` can **only SELECT** from
  `panadan_ingest.safe_call_facts_v1`. This security-barrier view
  projects a small primitive allowlist from the current, nondeleted
  `normalize:v1` revision. It hides raw source IDs, transcripts,
  phone numbers, arbitrary JSON and all underlying tables.

The view is an internal defense-in-depth boundary, **not** a replacement
for per-user REST/dashboard/MCP authorization; no serving path is switched
to the new database by provisioning these roles. No source is enabled,
and no customer records are copied.

Reapplying `roles-apply` reuses the stored role passwords; it does not
generate new ones. Never paste either secret into chat or GitHub.

**Restore caveat:** `pg_dump -Fc` saves database objects and ACLs but
does not export PostgreSQL cluster-global role definitions or passwords.
Safeguard `.env.platform` and `.env.platform.roles` separately in a
secret manager. On a fresh restore target, provision roles first or
restore with `--no-owner --no-acl` and then reapply the reviewed grants.
Do not test a restore against the existing live volume. Local unencrypted
backups are not yet an acceptable protection for real customer data.

## Manual Compose alternative (WSL + Docker)

The CLI above is preferred because it generates and checks the private
credentials automatically. If using the manual alternative below, your
password must be a **64-character lowercase/uppercase hexadecimal value**
(e.g. generated privately using `openssl rand -hex 32`), and `.env.platform`
must be mode 600. Never print or commit the generated password.

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
