# One-command Panadan-owned PostgreSQL authentication infrastructure

This workflow consolidates the previously separate PostgreSQL schema, role,
off-VPS recovery rehearsal and private-network preparation. It is source-
controlled so a new server does **not** require a hand-maintained list of
`docker network connect` and `psql` commands.

**Scope:** infrastructure preparation only. The production FastAPI
`server/main.py` still uses SQLite for users, sessions, tokens and audit.
This workflow **never** switches authentication, enables OAuth, imports
real accounts, changes Odoo, or recreates Plane/Caddy, VPN or Panadan Web.

## What lives where?

- `compose.platform.yaml`: Panadan's independent PostgreSQL 18 image,
  persistent storage and existing 127.0.0.1 host binding.
- `deploy/compose.auth-network.platform.yaml`: adds an external internal
  network alias `panadan-auth-postgres` to the database.
- `deploy/compose.auth-network.panadan.yaml`: adds **only the VPN container
  network namespace** to that network; keeps default and existing ingress
  service networks. Web continues `network_mode: service:vpn`.
- `database/migrations/003_auth_foundation.sql`: eight-table `panadan_auth`
  schema, separate from the existing seven-table `panadan_ingest`.
- `database/permissions/003_auth_runtime_role.sql`: database auth runtime
  role with DML on `panadan_auth` but no ingestion access or DDL.
- `tools/setup-owned-auth-pg.sh`: operator-facing, fail-closed wrapper.
- `tools/setup_owned_auth_pg.py`: actual orchestration, baseline checks,
  a fresh local `pg_dump`, internal bridge creation and attachment, post-
  connect source-VPN/HTTPS/TCP tests, and transactional schema/role creation.
- `tools/check_auth_db_network.py`: read-only network guard.
- `tools/verify-offsite-platform-restore.sh`: earlier offline
  WSL-only restore and schema/permissions rehearsal, not the live installer.

Dockerfile is intentionally **not** responsible for database schema or
network provisioning. Network configuration must survive builds and be
managed by Docker Compose/production operations.

## Existing production install (recommended)

Prerequisites: current healthy `panadan-platform-db-1`,
`panadan-vpn-1`, `panadan-web-1`, healthy HTTPS `dan.panafor.com`
and `plane.panafor.com/intake.html`. Run from the source checkout
with this PR present (merge reviewed PR before applying).

The operator has already verified independent age-encrypted PostgreSQL 18
backup restoration and schema + permission rehearsal on WSL. The **apply**
operation nevertheless requires explicit acknowledgment of that evidence,
and makes a **new local PG dump** immediately before changes. That local
dump does not substitute for recurring offsite backups or key escrow.

```bash
cd ~/panadan

# 1. No writes. Inspect readiness, Compose overlays and Odoo tun0 route.
sudo bash tools/setup-owned-auth-pg.sh plan

# 2. One explicit, guarded operation (real infrastructure changes).
sudo bash tools/setup-owned-auth-pg.sh apply \
  --ack-restored-backup --approve-live-network

# 3. Repeatable network, role, source-VPN and HTTPS verification.
sudo bash tools/setup-owned-auth-pg.sh verify
```

The apply command stops on incomplete prerequisite files, unexpected PG
version/schema, duplicate or foreign network membership, any overlap
between the new Docker subnet and existing VPN routes, wrong source
routing, failed HTTPS endpoint check, or unsuccessful private TCP probe.
Network attachments created *by the current invocation* are rolled back
on failure (only new attachments; never original Docker networks).
If an additive schema was committed and a subsequent check fails, **that
schema/role may remain** and must be inspected before retrying; the
script never drops or truncates account tables.

It creates or reuses a separate `.env.platform.auth` file, ignored by
Git and required to be 0600. It contains one random 64-hex auth runtime
role password and must be protected separately. The secret is sent to
local `psql` only over stdin, never passed on command-line argv or
printed in tool output. **Do not put privileged `panadan_owner`
credentials into Panadan Web.**

No image pulls, `docker compose up`/down, container stop/recreation,
`docker network disconnect` on existing endpoints, Odoo writes or
active SQLite file access occur during this setup.

### Persistence when deploying/recreating containers

Compose network configuration **must** accompany future approved
deployments. For Panadan Web/VPN, always include all *existing private
production overlays* **plus**
`deploy/compose.auth-network.panadan.yaml`. For the standalone owned
PostgreSQL project, include the base Compose file **plus**
`deploy/compose.auth-network.platform.yaml`. Do not replace existing
hardened `data/ingress` files or invoke bare `panadan.sh up/down`.

In the current server, `~/panadan/prodctl.sh` is an **untracked operator
script**. Review/update that script's Compose invocation manually
before using it for any future deployment; this PR **does not** overwrite
it or recreate containers. A later deployment should run
`setup-owned-auth-pg.sh verify` immediately after changes.

Docker Compose can recreate containers on config changes, which can
briefly disrupt Panadan/Plane/Odoo routing. Network-only attachment here
avoids the initial recreation; schedule persistence changes for an
approved maintenance window.

## First-time installation of owned PostgreSQL only

If there is **no Panadan-owned PostgreSQL container or volume**,
the same entry point can initialize its independent PostgreSQL service:

```bash
sudo bash tools/setup-owned-auth-pg.sh init-platform --approve-live-network
```

This reuses existing idempotent `platform-db setup/up/init` and
`platform-roles setup/apply/check` routines to generate local,
ignored credentials and the seven ingestion tables, then exits. It
does **not** install or deploy the web application, VPN credentials,
Plane, OAuth provider or any customer data. After the separate app
deployment, run `plan` and `apply` above.

If a stopped container or existing database volume is found, refuse
automatic "fresh" initialization: treat it as a recovery, not a new
installation. Never delete or recreate existing Docker volumes to
resolve a setup failure.

## Remaining blockers

- **Not yet done:** SQLite->PostgreSQL production accounts import,
  coordinated write freeze and rollback, live `PgStore` selection and
  end-to-end login/API/MCP smoke tests.
- **Not yet done:** secure runtime DSN injection into the web/VPN namespace,
  an independently rotated auth role, automated encrypted off-site PG18
  backup/retention/alerts, and copied-data restore rehearsal.
- **Not yet done:** external OAuth authorization server, CIMD/DCR/PKCE
  discovery and actual ChatGPT/Claude MCP linking.
- Keep issues #55, #56, #57, #58 and #70 open until those items are
  independently validated. Passing this setup does not mean they are done.
