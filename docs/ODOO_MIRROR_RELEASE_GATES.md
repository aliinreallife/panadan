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

- [ ] **Data owner** authorizes copying personal contact details, transcripts,
  summaries and AI analysis out of Odoo into a designated Panadan-owned store,
  and confirms any cross-border/employee/customer obligations.
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
