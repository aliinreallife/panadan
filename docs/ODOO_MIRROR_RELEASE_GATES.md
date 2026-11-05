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


## Larger supervised staging pages after first 275 calls (2026-11-04)

Operator verification results: 275 current records, 275 historical revisions,
11 committed 25-row pages, source disabled, all 37 view fields present.
The 275-row encrypted VPS-local backup passed an independent PG18 restore drill
and payload/checkpoint comparison; the first 25 and the latest 25 source calls
passed fresh Odoo-to-staging parity. These source checks are bounded samples,
not proof of whole-view consistency.

A follow-up transport revision supports **up to 100 source rows per page**
while keeping the **55,000,000-byte wire ceiling** and the 2 MB per-event
ceiling. The operator must first test a read-only 100-row export/validation
from the current pass-1 checkpoint. No raw customer JSON may be printed or
persisted. The manual `tools/run-odoo-mirror-staging-next.sh` helper
is limited to **3 pages x 100 source rows**, checks the cursor against the
maximum staged ID, and disables the staging source after each page and on
trapped failures. Duplicate source rows remain grouped without choosing one
AI analysis. A malformed page or failed cursor CAS must fail closed.

Do not start the write batch until the 100-row read-only test and full branch
CI have passed. Recheck the staging source is disabled after the batch, then
run integrity / independent encrypted restore / fresh source parity again.
Production dashboard, Web, VPN topology, and MCP stay unchanged. Local backup
remains insufficient as a production disaster recovery plan.


## Supervised, recoverable staging backfill pilot after 825 calls (2026-11-05)

The 825-row milestone completed: 825 current records and revisions; 24
committed pages; complete 37-field payloads; source disabled. The local
encrypted archive was independently restored inside a network-isolated PG18
container with byte-for-byte payload checks, and the latest 100 calls matched
a fresh read from the read-only Odoo reporting view.

The first *supervised* pilot is deliberately finite: `tools/run-odoo-mirror-staging-supervised.sh`
runs no more than **9 further pages x 100 source rows** (up to 900 view
rows) starting from the 825/24 baseline. It uses the already-reviewed
VPN-to-local temporary-container pipe importer; nothing installs a scheduler,
daemon, production DB connection or persistent plaintext transfer file.

Before any write, the supervisor verifies: named isolated staging endpoint
`127.0.0.1:55432`, networkless restore container, healthy existing VPN,
source disabled, pass-1 checkpoint equal to the maximum staged ID, matching
record/revision counts, all 37 fields, digest consistency, 24+ recorded
sync pages, a private decryptable encrypted backup, and the prior independent
825-row restore drill. A malformed state fails closed.

The supervisor permits **three 300-row recovery intervals**. It checks that
free disk space is at least **6 GiB before every page**, and makes a NEW
`age`-encrypted `pg_dump -Fc` recovery point after each interval. It
decrypts and validates the archive catalog but does **not** claim that a
catalog check is an independent restore: perform a full independent restore
after the pilot. It retains old encrypted archives and the required private
identity key on the VPS; this is not off-site or production recovery.

Interruptions retain the committed DB cursor. A mode-0600 local progress marker
records the most recently validated encrypted recovery point without customer
data. If a chunk stops after 1 or 2 pages, the next invocation uses a strictly
bounded 1- or 2-page helper to finish the incomplete interval. If the final
page committed but archiving was interrupted, the supervisor encrypts that
current checkpoint before any additional writes. It refuses unbacked progress
outside one 300-row interval. The supervisor itself is re-runnable only within
this **first 825-to-at-most-1725** test envelope; it is not a perpetual full
mirror scheduler.

Each page runs inside a disposable container. Source credentials remain
READ ONLY inside the existing VPN namespace; the importer uses a separate
0600 staging-only writer DSN and preserves raw source values and duplicate
analyses without preprocessing. Customer data is passed via an anonymous pipe
with Docker stdout logging disabled. The source enablement flag is turned off
after every page and on trapped failures. A failed import, source drift, schema
drift, stale cursor, low disk, encrypted backup failure, unexpected count, or
data-integrity failure stops the pilot.

Run only after CI passes and the operator has reviewed the specific pinned
commit. This is staging and explicitly must not switch the production dashboard,
REST, MCP or VPN topology to the mirror. A full source reconciliation and
fresh-source parity are still needed: bounded page parity alone is insufficient
for production cutover.


## Operator-initiated full first-pass staging backfill (2026-11-05)

The first supervised 300-row interval progressed from 825 to **1,125 calls,
1,125 revisions and 27 pages**, with the staging ingestion source disabled.
The old limited supervisor exited after printing the disk-space check at the
first encrypted backup; a new 1,125-row recovery point has **not** yet been
confirmed. Do not assume a backup exists merely because the import committed.
This is why a new *full first-pass* driver performs an explicit backup of the
current state **before** importing anything more.

`tools/run-odoo-mirror-staging-full-pass.sh` executes a complete **first**
source-view pass, beginning at the current committed checkpoint (>=825), until
the Odoo view announces the end and staging checkpoint becomes
`{"pass": 2, "last_id": 0}`. It neither resets the cursor nor starts the
second pass, and it never calls the legacy backfill/update streams. No
fixed 900-row or 300-row import ceiling remains. A 2,000-page budget is a
runaway-loop safety cap, not a target. For the reported approximately 95,510
Odoo source-view rows, 2,000 pages of up to 100 source rows is sufficient.
Source-group variants are stored together; distinct calls may be fewer than
source rows.

The operator must invoke the full-pass command explicitly with all four
existing acknowledgements. The runner reuses the proven pipe-based exporter
and importer in 3-page batches, with no persistent plaintext transfer files.
Source remains READ ONLY in the existing VPN container namespace, and the
target only receives the isolated PG18 staging writer credentials. The source
flag is disabled after every page and on a trapped failure. If the shell or
network interrupts, committed pages and checkpoint remain in PostgreSQL and
the operator can rerun the same command after inspecting failure output.

The runner checks the staging DB identity/version, isolated port
`127.0.0.1:55432`, required separate networkless restore container,
healthy source VPN, source disabled, cursor/max-ID consistency, current/revision
counts, complete 37-field payload structure, current and revision digests,
and a previously validated independent restore of the 825-row baseline.
It checks **>=6 GiB available disk space before every source page** and
**>=6 GiB plus 128 MiB of reserve before each encrypted backup**.

It creates and verifies a **new age-encrypted PostgreSQL archive at startup**
(covering the unarchived 1,125-row checkpoint), then whenever about **5,000
more records** have been imported, and at completion. Each archive is mode
0600, unique (no overwrites), decrypted and inspected with `pg_restore -l`,
and preceded by a full staging payload/digest/schema check. Empty or changed
source reads, stale checkpoints, disk pressure, schema/identity drift, and
archive failures fail closed. A successful archive catalog check does not
prove full disaster recovery; a fresh independent restore drill of the final
large dataset remains mandatory before any production rollout.

Crucial limitation: the Odoo reporting view is read by a succession of
read-only page transactions, not one cross-page repeatable-read transaction.
Source rows updated during the initial scan may become stale in staging.
Completion of pass 1 is therefore a **staging first-copy milestone**, not
proof of ongoing synchronization or whole-view parity. A later deliberate
reconciliation pass and fresh-source checks are needed for correctness and
handling removed/changed rows. This runner never silently begins pass 2.

The backup encryption identity and archives remain on the same VPS and are
not off-site disaster recovery. No production database, deployment, dashboard,
REST, MCP, scheduled worker or VPN configuration is modified by the script.


## Full-view source parity and pass-2 replay (2026-11-05)

The complete first pass and independent encrypted restore both verified
**95,912 current call groups, 95,912 revisions and 975 committed pages**;
staging checkpoint is `{"pass":2,"last_id":0}`. The full read-only 37-field
source parity census subsequently observed **95,996 source call groups** from
**95,997 view rows** (one duplicate-row group): **95,755 unchanged**,
**157 changed**, **84 new/missing at staging**, and **0 locally stored groups
absent from that source scan**. These are observations from a mutable view,
not a frozen snapshot. Only aggregate counts, never sensitive fields or
source identifiers, are printed.

`tools/run-odoo-mirror-staging-reconcile-pass2.sh` is an explicitly
operator-triggered **complete second source pass** in isolated PG18 staging.
It calls the already reviewed 100-source-row transport through
`run-odoo-mirror-staging-next.sh` using the explicit
`PANADAN_MIRROR_EXPECTED_PASS=2` capability (the legacy default still
accepts pass 1 only). On replay, unchanged source payloads are idempotent;
changes append new immutable revisions and update the local current digest;
new stable call IDs create records; missing-at-source records are **retained**,
not automatically deleted. The existing identity-anchor and full 37-column
schema/digest validation still fail closed on source ID reuse or view drift.

The new supervisor requires the verified independent 95,912-row restore,
pass-2 checkpoint, registered *disabled* staging source, private source and
target credentials, a healthy read-only VPN, isolated staging port
`127.0.0.1:55432`, and networkless restore container. It creates a fresh
`age`-encrypted archive of the current database *before any writes*,
then periodically at **300 committed pages** and upon completion, decrypting
and reading the entire archive stream to verify encryption/catalog integrity.
Every source page requires at least **6 GiB free disk**, and each backup
requires that plus 128 MiB of temporary reserve. Existing backups are kept.

The 2,600-page ceiling protects against nonterminating loops; it is not the
intended import size. The supervisor stops at the completed pass-2 cursor
`{"pass":3,"last_id":0}` and **will not automatically start pass 3**.
No cron, production service changes, Odoo writes, dashboard/API/MCP read-path
switch, Docker networking changes, or plaintext backup files are created.
Use a persistent terminal (tmux), since lost SSH sessions can leave a source
flag enabled if interrupted mid-page; inspect and disable the source before
relaunching. The supervisor is resumable from the last committed CAS cursor.

After pass 2, run the read-only *entire-view* parity census again and inspect
aggregated changed/new/no-longer-visible counts. A successful pass 2 and a
new encrypted archive are **not** an independent restore drill; verify the
latest recovery point separately before approving scheduled synchronization.
The current approximately 7.1 GiB free disk headroom is close to the 6 GiB
floor, and backups remain VPS-local rather than off-host. Do not declare a
production release without explicit approvals for sensitive-data access,
retention/erasure, Odoo joined-field update semantics, operator scoping, and
reversible cutover.


## Incremental staging synchronization: create_date and write_date only (2026-11-05)

**Operator's updated discovery contract:** The authorized Odoo reporting VIEW
exposes write_date as its only known update marker; create_date can also
identify newly created calls. The joined view's id is NOT assumed to be a
monotonically increasing creation watermark. Never poll new calls using
id > last_seen_id, and never run scheduled whole-view parity/reconciliation.

Implementation:
- server/odoo_mirror_incremental.py selects candidate IDs ONLY when
  write_date OR create_date falls in a bounded source-clock window.
  It groups candidates by id, sorting by timestamp and id as a tie-breaker.
  Then it fetches all 37 columns and all joined-row variants ONLY for
  selected IDs in one read-only repeatable-read source transaction.
- The initial scan looks back 24 hours, uses a 60-second settling delay,
  and replays a 15-minute overlap between completed windows. Separate
  created_or_modified_v1 checkpoints store frozen windows and a
  (last timestamp, last ID) page cursor, committed atomically with revisions.
  Up to 80 candidate call IDs and 100 joined view rows are allowed per
  bounded 55 MB pipe transfer. A call payload is capped at 2 MB.
  Oversized/ambiguous events fail closed; nothing is truncated.
- The verified 96,022-record pass-3 staging checkpoint remains unchanged.
  Every changed group retains all joined-row variants. The previously
  reviewed (call_id,create_date) anchor detects reuse of an existing ID;
  changed data appends a revision, unchanged data does not.
  Missing-at-source calls are not deleted.
- tools/run-odoo-mirror-incremental-cycle.sh runs up to ten pages per
  invocation, sharing the manual importer's continuation lock. Source
  activation is page-scoped, with fail-closed cleanup and orphaned-source
  recovery only after the exclusive lock is held. The 6 GiB disk floor
  remains mandatory. No backup, restore, or full-view parity is performed.
- tools/install-odoo-mirror-incremental-systemd.sh is a separate
  operator-triggered, create-only installer. It copies a pinned Git revision
  of tracked source files into a root-owned immutable release under /opt.
  A five-minute systemd timer runs this isolated-staging service from
  the root-owned release, never a user-writable checkout. The root system
  service accesses the existing Docker socket; disposable source and
  importer containers use the unprivileged panafor UID with read-only
  filesystem, dropped capabilities and disabled Docker logging.
  Explicit --ack-scheduled-sensitive-sync approval is mandatory.

Accepted limitations:
- A joined field that changes without write_date advancing cannot be
  detected by this timestamp-only approach. A call newly exposed by a JOIN
  with preexisting old create_date/write_date may also be missed.
- Source id is only a local grouping/association key and a timestamp
  tie-breaker; we have not proven that it cannot change when joins change.
  If an existing ID maps to a different call_id/create_date anchor, ingestion
  fails closed. Changed IDs may appear as new calls and leave stale ones.
  We will not promote call_id to the primary key without independent proof.
- Naive source timestamps are assumed UTC until independently verified.
  This is a series of snapshot-consistent pages, not one immutable view.
  More than 30 days of timestamp backlog fails closed for operator review.
- No mandatory backups are made per the operator's explicit choice.
  Prior encrypted archives are not deleted, and data loss may require a
  full rebuild following host/storage failure.

This adds no scheduled full-field comparison or complete view replay.
It does NOT change the Odoo source, current production dashboard/API/MCP,
authentication, VPN topology, network routes, or production PostgreSQL.
The five-minute timer is staging-only until explicitly approved for
production cutover after authorization and runtime acceptance tests.
