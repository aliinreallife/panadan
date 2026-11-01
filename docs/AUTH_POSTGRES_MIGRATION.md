# Panadan authentication: SQLite → owned PostgreSQL 18

> **Phase 1, staging only — 2026-11-01.** The production dashboard and MCP
> remain on the existing SQLite `/data/auth.sqlite`. No production migration,
> dual-write, outage, role grant, Odoo source change, or account cutover has
> occurred. Tracked by [#70](https://github.com/aliinreallife/panadan/issues/70).

## Existing databases are distinct

| Database | Role | Current status |
| --- | --- | --- |
| Odoo source PostgreSQL at `192.168.3.9` | External CRM reporting | SELECT-only via VPN; never migrate/write source |
| Panadan-owned PostgreSQL 18.6 (`compose.platform.yaml`) | Intended owned ingestion and application storage | Optional separate Compose project. The repo schema is ready; whether the instance is running **on the VPS has not been verified** |
| SQLite `/data/auth.sqlite` | Active Panadan users, sessions, API/MCP access tokens, OAuth identity bindings, audit, throttles, operator metadata | **Current production authority** |

The proposed target uses a dedicated `panadan_auth` schema in **Panadan's
owned PostgreSQL only**, separate from `panadan_ingest`. No runtime user
has been given grants to this schema yet. A reviewed grant template is present,
but role provisioning and production use are intentionally manual and pending. Do not use the PostgreSQL
`panadan_owner` privileged credentials as the web/worker runtime role.

## Phase 1 code

- `database/migrations/003_auth_foundation.sql`: creates the auth schema,
  eight tables, indexes, identity sequences, tight constraints and explicit
  PUBLIC privilege revocations. The SQL refuses databases other than
  `panadan` or `panadan_ci` and requires PostgreSQL major version 18.
  It is additive/idempotent and creates no external connectors.
- `database/permissions/003_auth_runtime_role.sql`: opt-in, idempotent DML-only grants to a separately provisioned `panadan_auth_runtime` role. It does **not** create login credentials or activate runtime access, and may not be applied to Odoo.
- `server/auth_pg_migration.py`: checks an offline, consistent SQLite
  backup using `PRAGMA integrity_check`, validates table columns and
  user ownership, then prints only table counts. **No connection to
  PostgreSQL in default mode.** Optional `--apply-to-disposable` imports
  within one PostgreSQL transaction, preserving ID/hash relationships,
  into an **empty** schema on `panadan_ci` reachable from loopback only.
  A second run refuses to overwrite. Generated opaque `profile_id` is
  stable after import and is not tied to email, username or token.
- `tests/test_auth_pg_migration.py`: no-network snapshot validation and
  PostgreSQL 18 integration tests using only synthetic data, including
  an intentionally invalid late audit row proving full rollback.

**Sensitive:** SQLite backups contain password hashes, session hashes,
token hashes, OAuth issuer+subject pairs and audit. They are confidential.
Do not commit or paste them, display raw records, or use a live DB file as
migration input. Use the SQLite Online Backup API to produce a consistent
snapshot before any analysis. Keep the private age decryption key outside
the VPS. Never use an Odoo source DSN as a migration destination.

## Safe local validation

```bash
# No credentials required for this operation, and no DB is changed.
uv run --locked python -m pytest -q tests/test_auth_pg_migration.py

# Only a *copied*, consistent snapshot: does not change SQLite/PG.
uv run --locked python -m server.auth_pg_migration \
  --sqlite-snapshot /secure/path/to/auth-backup.sqlite

# To exercise actual PostgreSQL import, use the disposable CI runner:
bash tools/test-platform-integration.sh
```

The synthetic test also verifies that a dedicated auth runtime role can use auth DML but cannot create/truncate schema objects or read ingestion tables.\n\nThe standalone test runner starts a disposable PostgreSQL 18 `panadan_ci`
container and never reaches the production account store. It uses
`PANADAN_PLATFORM_TEST_DSN` and explicit reset guard. Live
`--apply-to-disposable` also requires a **separate**
`PANADAN_AUTH_MIGRATION_TEST_ALLOW_APPLY=YES` flag. The integration
tests set that flag on their own for synthetic transactions.

## Production cutover: deliberately NOT implemented yet

1. **Confirm the owned PG18 instance exists on the VPS**, its image
   digest, storage, backups, permissions and that Panadan Web can reach
   it on a dedicated private network without publishing it publicly.
   Do not assume the optional Compose project is running.
2. Review and approve the `panadan_auth` schema and a **dedicated
   least-privilege runtime role**, distinct from `panadan_ingest_writer`,
   `panadan_report_reader`, and `panadan_owner`. Its exact grants
   should be limited to needed auth tables/sequences; no source Odoo
   permissions.
3. Implement a PostgreSQL-backed `Store` conforming to existing
   `server/security.py` API and transaction guarantees: login throttle,
   password/session, access token creation/revocation, OAuth binding,
   transcript permission/audit, activity and operator metadata.
   Permission checks remain server-side, on every request.
4. Build a **staging rehearsal** from a copied and verified snapshot
   with protected data controls. Check exact account counts, password
   hash equivalence, account ID mapping, token hash/scope preservation,
   OAuth issuer+subject binding, revocation, rate throttling, audit and
   UI/API/MCP behaviors. Agree explicitly whether pre-cutover sessions
   and tokens will be retained or revoked; no silent new privileges.
5. Design a planned brief auth write freeze (or formally proven
   dual-write/event-log strategy), re-import a fresh snapshot in an
   isolated target, switch only the auth connection and run positive
   and negative live smoke tests. Have an explicit **reverse cutover**
   plan that prevents writes going into two authoritative stores.
6. Add **consistent PostgreSQL backups** (`pg_dump -Fc` plus off-site
   encryption, retention, regular tested restore), retain legacy
   SQLite backup until verified migration and stabilization. Do not
   claim the earlier SQLite-only age backup covers Panadan PostgreSQL.

Critical: PR #69 adds an opaque `profile_id` to SQLite. It is
**on architecture hold** until reconciled with this PostgreSQL migration.
Prefer allocating account profile IDs in Panadan-owned PostgreSQL as part
of the cutover without introducing another production SQLite migration.

## Unfinished operations

- No runtime auth PostgreSQL store or production switch yet.
- No automatic schedule, migrated production accounts, or proven restore.
- Existing source Odoo PostgreSQL privileges (#22) remain separately
  subject to DBA review; no changes should be made in that database.
