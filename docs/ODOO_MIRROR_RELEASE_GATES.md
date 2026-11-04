# Panadan Odoo full-mirror release gates (v1 draft)

**State: NOT RELEASED.** PR #97 contains staged implementation and synthetic
tests. Production still reads Odoo directly. Nothing here grants authorization
to copy customer records, enable full-mirror ingestion, edit the live
database, or switch the existing Panadan UI/MCP.

## Architecture

- Source: the already permitted read-only Odoo view
  `public.vw_danix_call_info_report` (37 fixed fields). **No Odoo DML,
  new privileged role, CDC feed or schema migration is required.**
- Target: separate Panadan-owned PostgreSQL 18 with per-source current digest,
  immutable raw revisions, processing jobs, and an atomic scan cursor.
- Sync: duplicate-safe canonical ID groups, repeated full-view reconciliation
  instead of relying on parent `write_date`, bounded manual/scheduled-by-operator
  ticks, source-only read queries, no inferred deletion.
- Reads: sanitized current-state listing under `panadan_report_reader`;
  full 37-field detail under separate
  `panadan_mirror_sensitive_reader` + per-user verified numeric operator scope,
  sensitive capability checks, and durable pre-read audit; staging-only REST
  and safe summary MCP.
- Live service: production `server.main` dashboard, API and MCP still use
  existing source paths until a separately reviewed cutover. New staging app
  is disabled by default and must never be reverse-proxied publicly.

## Mandatory external approvals — cannot be inferred from code or tests

- [x] **Project operator attests authorization** (2026-11-04) to copy
  Odoo customer records, including phone numbers and transcripts, into
  Panadan-owned storage for this project. This is a *user-provided
  attestation*, not independent verification of data-owner paperwork.
  Before real copying, operations must document the approved staging
  destination and applicable cross-border/employee/customer requirements.
- [ ] **Odoo owner** confirms the 37-field view contract, source timezone and
  exact identity/ownership semantics of `vw_danix_base_info_users`.
  Display names and teams are **not** identity proof.
- [ ] **Retention/privacy owner** approves purpose, retention periods,
  access logging, legal holds, erasure workflow and backup retention for
  immutable raw revisions and transcripts. Never interpret disappearance
  from the joined view as permission to delete.
- [ ] **Infrastructure owner** approves the isolated staging storage boundary,
  encrypted/off-host backup and independently proven restore, restricted
  writer/report/sensitive role secret rotation and least privilege.
- [ ] **Operations owner** approves a reconciliation interval/acceptable lag,
  alerts for nonzero tick/health exits, bounded load during peak Odoo hours,
  recovery procedure and a rollback window.

## Test-only milestones (already exercised in GitHub CI)

- [x] Duplicate ID groups, child-only edits and stable normalized digests.
- [x] Revision history, checkpoint ACID commits, replay, interrupted pages,
  missing source-row retention, and finite manual `snapshot-run`.
- [x] PostgreSQL 18 synthetic migration, idempotency, restart/restore,
  role boundaries and separate sensitive audit.
- [x] Staging REST calls/list/count/full detail and token/role isolation.
- [x] Default-deny verified operator ID scopes, admin reauthorization,
  scope changes, session and token revocation.
- [x] Guarded staging launcher refuses Odoo/production DSNs, public origins,
  untrusted remote clients and unsafe secret files.
- [x] Controlled sync `tick` policy with page/time/backlog limits and
  unrelated source-job isolation.
- [x] Read-only `verify-run` parity walk with a resumable cursor and
  duplicate-ID boundary tests.

These tests use **synthetic data**. They are not proof that a real staging copy
or a production rollback succeeds.

## Required real staging acceptance — do not skip

1. Take and verify encrypted/off-host backups **before any import**.
2. Provision an isolated owned PostgreSQL 18 staging instance. Review
   migrations 001, 002, 003 and 004 *in that order* and provision the
   three narrowly scoped roles. Confirm ordinary reader, writer and
   PUBLIC cannot SELECT the sensitive view or raw tables.
3. Independently verify source operator ID assignments. Enable the admin
   grant workflow **only after** the Odoo data owner has confirmed the IDs.
   Never auto-grant all operators to admin.
4. Run one bounded source read-only preview (already benchmarked early/late
   pages at about 1 second per 101 rows), then request explicit approval for
   the initial real staging copy.
5. Import one approved bounded page; compare every source variant and
   all 37 field names; verify two separate operator accounts, a read-only
   token, a sensitive token, denial for cross-operator IDs, and audit failure
   refusal. Avoid printing personal values in test output.
6. Complete a whole-source reconciliation using finite ticks; run
   `verify-run` repeatedly until `complete=True`. Expect transitory
   differences if the source changes during a multi-page scan.
7. Run a second whole pass. Unchanged digests must create no new revisions;
   changed child rows must create one new revision per affected call.
   Disappearing view rows must not auto-delete. Validate queue limits,
   stale alerts, interruption/resume, crash/restart and source failure.
8. Independently restore an encrypted staging database **into a new isolated
   PG18 instance**. Confirm revision counts, checkpoints, grants/audit logs
   and application reads (not just `pg_restore --list`).
9. Prove that every planned production dashboard/API/MCP/WebMCP route
   enforces an authenticated principal, verified operator scopes and the
   proper separate sensitive privilege. **Legacy production paths are not
   yet switched by this PR.** Document compatibility and rollbacks.

## Safe stopping points

- Before real data-copy approval: run only synthetic CI, source read-only
  previews and preflight checks.
- Before complete permission and retention acceptance: keep the full mirror
  off and local detail/API/MCP inactive.
- Before a signed production rollout: **do not merge**, run
  `docker compose up/down`, switch target DSNs, restart VPN/Plane/Caddy, or
  add the staging app behind public ingress.
- Any permission/schema drift, failed backup restore, private overlay change
  or unknown source identity: disable scheduled tick / cancel deployment
  and investigate. Do not patch around guard failures.

## Production deployment (separate approval)

Use the repository's existing **guarded web-only** deployment path and the
private owner-reviewed Compose overlays, never a bare Compose deployment.
The previous pinned Web image must remain available for rollback. Deployment
must not alter VPN, Plane or Caddy. The live app switch requires additional
compatible dashboard/API/MCP code and verified permissions, not just a green
PR CI. The guarded controller can refuse when private overlays diverge;
refusal is not authorization to relax it.

**Known correctness limit:** A joined Odoo view without a real change feed
cannot guarantee recording every intermediate change. Reconciliation can
converge to the most recently observed source state, but does not provide
lossless CDC or a consistent single instant snapshot across ~95k rows.


## Isolated staging writer option (not production activation)

The existing supervised importer initially supported only a restricted
writer for the production-owned PG18 host `panadan-auth-postgres` /
database `panadan`, while the isolated staging API expected a disposable,
localhost-only `panadan_ci`. These two targets are deliberately different.

`server/odoo_mirror_target.py` now allows the already reviewed
`server.odoo_full_mirror_pilot` and
`server.odoo_mirror_scheduler` commands to use a **separate, opt-in
staging-only writer** without weakening the existing production writer
selector. Default/unspecified mode preserves the existing guarded writer.

To select *only* a pre-existing isolated PostgreSQL 18 staging instance,
set the following variables in the private, isolated runner environment:

```text
PANADAN_FULL_MIRROR_TARGET_MODE=isolated-staging
PANADAN_FULL_MIRROR_STAGING_ISOLATED=YES
PANADAN_FULL_MIRROR_STAGING_WRITER_DSN_FILE=/absolute/private/writer.dsn
```

The file must be a regular, non-symlink file, owned by root or the
executing account, mode `0600` or stricter, and contain one libpq DSN
line with **only**:
- host `127.0.0.1` and an explicit numeric TCP port,
- dbname `panadan_ci` and user `panadan_ingest_writer`,
- password and explicit sslmode `prefer`, `require` or `verify-full`.

The selector rejects production `panadan`, source `odoo`, alternate
hosts, wrong database roles, libpq redirect environment, symlinks, group
or world readable files and any unsupported mode, **without fallback** to
the production target. Once connected, it verifies the real PG18 database
name and `current_user`. No password or private DSN is stored in
GitHub, exposed in chat or printed in diagnostics.

**Staging is not an implicit consent or rollout switch:** the source Odoo
reader remains separately read-only; `snapshot`/`snapshot-run`/`tick`
still require all four explicit approval flags and a separately registered,
enabled source in the owned target. The selected loopback PostgreSQL port
must be a *genuinely isolated test instance*, not a port-forward to the
live production instance; that infrastructure fact must be verified by
the operator. This module does not provision a staging DB or initialize
roles, connect the dashboard to production, or schedule automatic copying.

For exact project-specific staging command syntax and SQL migration review,
see `docs/ODOO_FULL_MIRROR_PRODUCTION.md`. Do not paste passwords,
transcripts or complete DSN files into issues or ChatGPT.


## First-page staging pipe transport (2026-11-04)

The project operator elected to **defer encrypted off-host backups for the
isolated staging experiment only**, after passing an independent restore
drill on an empty database. This is a *knowingly accepted staging recovery
risk*; an existing VPS-local empty-db dump and restore drill are not an
off-host recovery plan and do not satisfy production release gates.
After a real-data import, perform a NEW encrypted local backup and independent
restore check; no production cutover is permitted without approved DR.

The existing production VPN namespace can read Odoo, but the protected
staging writer accepts only `127.0.0.1:55432` in the VPS host namespace.
A one-shot manual transfer avoids weakening either network boundary:

`tools/run-odoo-mirror-staging-page.sh first-page
--ack-source-contract --ack-retention --ack-copy --ack-sensitive-data`

- Exporter runs a temporary, locked-down container sharing only the existing
  VPN namespace. It checks Odoo `report_user` + READ ONLY, validates the
  fixed 37-column schema, and fetches **at most 25 source rows**.
- Exported JSON (which is **sensitive**) travels exclusively via a Unix
  process pipe to an independent temporary importer container. Never echo,
  tee, redirect, inspect, or save exporter stdout. The source container
  disables Docker's stdout log driver to avoid preserving the stream in
  container logs.
- Importer uses a separately mounted `0600` restricted staging writer
  DSN, host localhost `127.0.0.1:55432`, and a snapshot cursor check.
  It verifies the canonical digest, all expected field names/types, source
  ID ordering, duplicate-group completeness, payload-size budgets and
  stable `call_id`/`create_date` identity anchors **before** the atomic
  checkpoint/ingestion transaction.
- Each invocation requires the four explicit acknowledgements, an independently
  enabled staging source, and **zero preexisting mirrored records**. This
  first-page helper **must not** be used to resume a complete scan.
- No Odoo writes, no tunnel reconfiguration, no unprotected full DB role,
  no production dashboard cutover, no plaintext export file, and no
  automatic scheduled job are introduced.
- Before granting any staging users access to sensitive detail, the Odoo
  owner must independently confirm numeric operator-ID semantics and
  authorization scope. **Do not enable the staging dashboard yet.**

This is a staging pilot, not a production recovery/synchronization solution.
