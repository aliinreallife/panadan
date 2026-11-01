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
- `server/security_pg.py`: **staging-only** explicit PostgreSQL `PgStore` implementation for login/session, password verification, users/roles, persistent throttling, revocable API and MCP tokens, OAuth bindings, transcript audit, activity reporting and operator assignment. The live `server/main.py` still constructs SQLite `Store` unconditionally; **no feature flag or production auth cutover** has been introduced.
- Synthetic PostgreSQL-18 integration exercises account session and token revocation, OAuth rebinding, profile IDs, transcript permissions, login throttle, activity reporting and operator metadata. This is a new adapter; real copied-data rehearsal is still mandatory.
- **VPS observation (2026-11-01):** operator verified `panadan-platform-db-1` running, healthy on PostgreSQL 18.6, the `panadan-platform_panadan_platform_pg18_data` volume present, and `.env.platform` available. This does not verify runtime grants or connectivity from Panadan Web's shared VPN network namespace.
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

## Confirmed production preflight — 2026-11-01

The operator ran **read-only checks** on the existing VPS and verified:
- PostgreSQL 18 healthy, `panadan_ingest` has 7 tables and no registered/active sources.
- Existing `panadan_ingest_writer` and `panadan_report_reader` passed restricted-role verification. These checks do **not** establish the future `panadan_auth_runtime` role.
- `panadan_auth` schema is currently **not installed** in `panadan`, so the application database contains no imported authentication accounts.
- Local PostgreSQL custom-format dump created: `data/platform-backups/panadan-20261101T130707Z-673d8eb3.dump` (mode 600). The existing `platform-db backup` workflow verifies `pg_restore --list`, **not** an independent restore or off-server copy.
- Public `https://dan.panafor.com/healthz` and `https://plane.panafor.com/intake.html` continued responding successfully.

**Next gates:** encrypt and transfer this *PostgreSQL* backup off-VPS using a public `age` recipient (never place the private key on VPS); verify remote decrypt/checksum equality; rehearse restoration into disposable `panadan_ci`; review and merge this PR; only then consider installing the additive `panadan_auth` schema and dedicated restricted role in the owned production database, without switching FastAPI.

Neither the local dump nor the previously backed-up SQLite auth snapshot may be used as proof of a complete off-site disaster-recovery procedure. No production `pg_dump` timer is enabled.


### Off-VPS recovery drill completed (2026-11-01)

The operator ran the `tools/verify-offsite-platform-restore.sh` helper on a local WSL computer using the age-encrypted PostgreSQL dump. The isolated PostgreSQL 18 restore completed successfully: seven `panadan_ingest` tables, zero sources, and no `panadan_auth` schema. The ephemeral container was deleted. A prior decryption stream SHA-256 comparison with the original VPS dump matched. This confirms that the *pre-auth* platform database backup is recoverable. The live SQLite account store has not been migrated or restored to PostgreSQL. Automation, separate key escrow, post-migration auth backup and end-to-end application recovery are still pending.

## Optional offline rehearsal after successful restore

To rehearse migration 003 against the same verified backup **without touching the VPS**, run from WSL with local Docker. Fetch the current PR branch, then use the encrypted backup and the existing local age private identity. Both the restored database and the proposed schema are confined to a disposable `--network none` PostgreSQL 18 container. This is still a schema-only rehearsal: accounts remain in SQLite.

```bash
cd ~/panadan
git fetch origin feat/pg18-auth-foundation-and-migration
git show FETCH_HEAD:tools/verify-offsite-platform-restore.sh > /tmp/panadan-restore-check.sh
git show FETCH_HEAD:database/migrations/003_auth_foundation.sql > /tmp/panadan-auth-schema-test.sql
bash -n /tmp/panadan-restore-check.sh
bash /tmp/panadan-restore-check.sh \
  "$HOME/backups/panadan/panadan-20261101T130707Z-673d8eb3.dump.age" \
  "$HOME/.config/age/panadan-identity.txt" \
  --auth-schema /tmp/panadan-auth-schema-test.sql
```

Expected: original 7 ingestion tables and zero sources pass restoration checks; the proposed DDL creates exactly eight auth tables; the original seven ingestion tables remain. This does **not** exercise auth data import, restricted runtime grants, connection routing, or an application cutover. Do not run the SQL against production as part of this rehearsal.

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

- A staging PostgreSQL runtime adapter exists but is **not selected by FastAPI** and not cut over to production.
- No automatic schedule, migrated production accounts, or proven restore.
- Existing source Odoo PostgreSQL privileges (#22) remain separately
  subject to DBA review; no changes should be made in that database.
