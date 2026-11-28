# Panadan Knowledge Platform — Implementation Status

Date: 2026-11-27 (last updated)
Authorization: D-067 roadmap; M00 and M01.1 verified; owner explicitly authorized M01.2 on 2026-11-27. D-068 approves all three UI references for frontend increments only. [Roadmap](ROADMAP.md) approved.
Inspected baseline: 97c797c3196ea05cdf65878962f6183e484f6459.
Protected refs observed: main and backup/pre-knowledge-platform-2026-11-25 at 44561cad16e17b7e60287dc8e0d7a7210fc5d32a.
Current gate: **G0 passed; M01.1 verified; M01.2 offline/frontend and audit rollback passed; intermittent delegation expiry fixture corrected, targeted PG rerun pending. G1 remains pending.**
This ledger records evidence, not estimates. No implementation milestone is verified merely because a plan is approved.

## 1. M00 progress and evidence

| Task | Status | Evidence / remaining work |
| --- | --- | --- |
| M00.1 | Static inspection complete | GitHub connector branch/tree inspection, current auth, ingestion, migration, frontend and verification files examined. Protected refs confirmed. No live queries. Assistant runner checkout unavailable; owner subsequently cloned the exact expected documentation-only HEAD in a local development environment. |
| M00.2 | Verified synthetic (owner-reported) | Owner-provided terminal output at 38e176b3343ace81b1ef2fe72b840f326fbf527f: clean fresh clone, Python 3.13.14, uv 0.11.32, Node 24.22.2, npm 11.19.1, Docker Engine 29.8.1 / Docker Desktop 4.93.0. `./panadan.sh verify --docker --assets` completed successfully. Dedicated disposable PG18.6 auth migration suite subsequently passed: 21 passed, 0 skipped/failed in 19.06s; compileall completed successfully. Final marker: M00 additional verification PASSED. |
| M00.3 | Complete (reviewed documentation) | This ledger defines synthetic fixture plan, default-off contract, migration review, UI backlog and proposed M01 increments. These are reviewable implementation conventions, not implemented controls. G0 passed; M01.1 subsequently authorized and verified. |

### Reuse inventory

| Area | Existing evidence | Disposition |
| --- | --- | --- |
| Identity | server/security.py, auth_store.py, field_permissions.py, permission_catalog.py; SQLite default and postgres-staging guard; account IDs and OAuth bindings | Reuse authentication, extend explicit stable principal bridge and scoped membership policy. Verify account lifecycle/recreation, revocation and legacy grants; no name/email binding or silent auth cutover. |
| Web/API/MCP | server/main.py, mcp_tools.py, oauth_mcp.py and transport/access tests | Extend shared authorized query service later; preserve legacy routes, consent and permissions. Existing global routes do not become workspace-scoped by adding a UI selector. |
| Owned DB | database/migrations/001_multisource_foundation.sql and 003_auth_foundation.sql, database/permissions/002_platform_runtime_roles.sql and 003_auth_runtime_role.sql | Preserve files and old schemas. New additive panadan_knowledge schema, separate role grants and tenant keys/RLS in M01. Review migration runner before choosing next numbering. |
| Ingestion | platform_ingest.py, platform_processing.py, Odoo adapter, coordinator | Reuse checkpoint and deterministic processing concepts. Existing raw revisions and global source keys not suitable as the new filtered tenant store; no automatic migration. |
| Source access | database.py fixed read-only parameterized view, historical READ_ONLY and source audits | Preserve source-only reader and independent privileges. Source grant/ID/clock/assignment verification required privately before real activation; no actual source audit in M00. |
| Frontend | templates/dashboard.html and other Jinja templates; static/style.css, app.js, mobile-nav.js, labels.js, jalali.js; web/build.mjs, Doran and self-hosted Vazirmatn | Reuse RTL, date/formatting and asset infrastructure where compatible. Develop isolated knowledge shell/components with both approved design references. Existing CSS uses green palette and repeated shell styles; do not globally overwrite legacy selectors before regression tests. |
| Verification | panadan.sh dispatches tools/verify-local.sh; tools/test-platform-integration.sh; .github/workflows/tests.yml | Reuse offline locked harness and disposable PG18.6 integration. Extend reviewed tests at each increment; no production DSN or persistent DB volume. |
| Missing product modules | Approved PRD / architecture / data model | Build progressively per M01–M11, not all schema objects at once. |

### Baseline test results

| Verification | Result |
| --- | --- |
| GitHub branch/tree/docs and protected ref inspection | Passed (static connector evidence) |
| Direct Git remote access | Assistant runner failed DNS (exit 128); owner local fresh clone succeeded at expected HEAD, clean status |
| Locked Python offline suite | 525 passed, 27 skipped, 0 failed; 51.45s (owner-reported) |
| Python compileall (CI parity) | Passed in follow-up command: server, tests, tools |
| Node dashboard tests | 65 passed, 0 failed/skipped (owner-reported) |
| Browser/shell syntax and locked asset build | Passed; npm emitted non-fatal esbuild install-script warning |
| Disposable PostgreSQL transactional integration | 42 passed, 0 failed/skipped; 2.14s (owner-reported) |
| PG18.6 schema replay, restart persistence, backup/restore | Passed (owner-reported); repeated schema notices expected |
| PostgreSQL auth migration integration | 21 passed, 0 failed/skipped; 19.06s, separate disposable PG18.6 container (owner-reported) |
| Docker image builds | Not run; not authorized PR workflow |
| Production, live source and external AI/MCP checks | Not attempted; outside M00 |

Owner terminal transcripts report 653 successful test executions across four invocations (not necessarily distinct tests), zero failures, and 27 offline skips. The two successful verification markers were Local verification PASSED and M00 additional verification PASSED. An intervening attempt from the home directory failed before pytest ran (no project/pytest); the corrected attempt from the project directory passed. No application test failure was observed. The assistant reviewed the transcripts and scripts, but did not independently execute the suites. Static review accounts for the 27 offline skips by 11 database-dependent tests in test_platform_ingest.py, four in test_platform_role_permissions.py, one in test_platform_scram_auth.py and 11 in test_auth_pg_migration.py; these require the disposable PG DSN absent in offline mode and all four files were subsequently included in successful PG runs. This matches the skip total, although the original offline transcript did not print individual skip reasons. All required baseline local suites and CI PG suite files are covered. Docker image build/actual production checks remain outside this gate. Historical CI results are not current baseline evidence. CI triggers on main pushes and pull requests, not ordinary feature-branch pushes. No workflow dispatch or PR created.

### Reproduce main G0 verification (owner completed)

Use a **fresh clone**, not the production checkout. Node 24, Python 3.13, uv, Git, npm and Docker are prerequisites. Do not copy .env files, VPN configuration or production secrets, or point tests at persistent platform DBs. Verify Docker context targets a development engine. Run from Linux/WSL:

```bash
git clone --single-branch --branch feature/knowledge-platform https://github.com/aliinreallife/panadan.git panadan-m00
cd panadan-m00
git rev-parse HEAD
git status --short
python3.13 --version
uv --version
node --version
npm --version
docker version
./panadan.sh verify --docker --assets
```

Run in a clean shell without real service credentials. The inspected verify script unsets PostgreSQL source/test env variables, runs locked Python/Node and syntax tests, optionally builds assets, and starts a separate loopback-only PG18.6 container using synthetic credentials with cleanup scoped to that container. Inspect current scripts at checkout before running. The local disposable runner tests ingestion, role permissions, SCRAM, optional Odoo adapter, restart persistence and backup/restore; the CI PG job additionally includes tests/test_auth_pg_migration.py. For G0, the dedicated auth migration suite and compileall have now passed in a follow-up run using a fresh loopback-only disposable PG18.6 container with synthetic credentials and cleanup trap. Offline skip coverage reconciled by static test inspection as described above. Retain exact revision and test results; do not infer production readiness. No need for a real source connection, paid provider or deployment.

## 2. Proposed implementation harness conventions

Default-off contract (design, not implemented): new knowledge routes/features unavailable unless explicitly enabled in reviewed owned environment, workspace enabled and current membership/permission passes. Default disabled for source connectors, schedules, real AI egress, external MCP knowledge access and destination delivery independently. Synthetic fixtures and mock providers may be enabled only in isolated test configuration. A feature flag never grants authorization. Fail closed on missing config, invalid scope, unknown cost, missing evidence or policy failure. Do not modify legacy reporting behavior or expose new users to global reports.

Migration review: inspect actual runner and existing migration numbers; new additive files only; no source DSN, no editing applied migrations, no unreviewed broad grants. For every increment review clean/existing-schema disposable install, ownership, tenant composite constraints, RLS negative cases, context reset, rollback by disablement and data preservation. No auto-assign legacy rows. Exact migration and feature-flag naming to be proposed with M01. No production migration.

Synthetic fixtures: two fictional workspaces with intentionally overlapping source external IDs and separate stable principals; one designated synthetic operator and fixed 30-day half-open interval per primary scenario, plus out-of-window/operator and ambiguous assignments; invented Persian/mixed-language call text including clearly synthetic sensitive canaries; duplicate/replayed/changed markers, missing dates/transcripts and contradictory evidence; compatible/incompatible extraction signatures; synthetic cost/rate ledger with concurrency and uncertain outcomes; mock AI and local fake destination only. No actual transcripts, customers, provider tokens or private deployment IDs. Store fixtures in reviewed tests, no raw durable payload in the new knowledge path. Record explicit expected counts, scope and denial outcomes; do not infer unique customers.

Test map: M01 AT-01 / DM-T01; M02 AT-02/03 / DM-T02–04; M03 AT-04 / DM-T05; M04 AT-08 / DM-T10; M05 AT-05 / DM-T06/07; M06 AT-06/07 / DM-T08/09; M07/08 AT-09; M09 AT-07/10 / DM-T09/12; M10 AT-03/11 / DM-T11; M11 AT-01–12 and DM-T01–12, recovery and all required regression. See roadmap for complete traceability. New integration tests must be explicitly included in reviewed test runner/CI; no PR or CI configuration change in M00.

## 3. U0 design preparation

D-066/D-067/D-068 adopt all three references as complementary inputs; the original visual direction remains governing, and the interactive prototype is not a replacement backend. [UI_DESIGN_REVIEW.md](UI_DESIGN_REVIEW.md) governs reconciliation. Preserve warm editorial visual language and Persian RTL; design Home briefing, Explore, Knowledge, Applications, Infrastructure with role-aware access, workspace switching and legacy reporting. Navigation remains a proposed detailed design, not a permission policy. Candidate Forest #293F34, Sage #A4B5A0, Ink #202822, Canvas #F6F5F1, Surface #FFFFFF, Border #DADFD7; alternate reference palette remains available. Use dark ink on warm surfaces; test sage/semantic contrast before using for text. Proposed 4px grid, 40px controls, >=44px mobile touch targets, 6–12px radii, functional reduced-motion-aware transitions, Vazirmatn/Inter subject to asset/license review. No final token or logo artwork approval.

| UI increment | Reviewable screens and interactions |
| --- | --- |
| U0/U1 | Isolated RTL shell, workspace selection, briefing, member/access views, denied/empty states, preserve existing reporting |
| U2/U3 | Resources and permitted representation inspector, integrations, seven objective templates, pipeline configuration and run history |
| U4/U5/U6 | Usage and cap controls, observation/evidence inspector, knowledge list/detail, review queue, taxonomy |
| U7/U8 | Customer insight feed/dashboard/detail, content opportunity and full brief |
| U9/U10 | Pinned packages, access preview and MCP/API, additional source setup and separate destination delivery |
| U11 | Full desktop/mobile journeys, keyboard/contrast, errors, partial/stale/restricted/budget states and detailed UI review |

Three-pane knowledge inspector on desktop and sequential detail on mobile are candidates; preserve filter/selection state without retaining unauthorized cached payload. No new design dependency/framework or dark-mode requirement added. No actual UI implementation or screen rendering performed in M00.

## 4. M01.1 — additive knowledge foundation (verified synthetic)

Owner approved M00 completion and M01.1. This authorizes implementation of existing decisions D-047–D-050, D-057–D-058 and D-067, not a new architecture decision, further increments or any production execution.

### Changes

- database/migrations/004_knowledge_foundation.sql: new schema and five tables (workspaces, principals, memberships, policy_versions, audit_events); UUID keys, tenant composite PK/FKs and same-workspace policy approver/audit actor consistency, uniqueness, state and bounded JSON checks, indexes. Workspaces/principals disabled by default; policy versions draft by default. No seeded tenants, account copies, credentials or source payloads.
- Guard requires PostgreSQL 18, exact database/user pair (panadan/panadan_owner or panadan_ci/panadan_ci), administrator and explicit transaction-local target confirmation. Dedicated NOLOGIN, NOINHERIT, NOSUPERUSER, NOBYPASSRLS owner; refuse incompatible role or schema ownership. PUBLIC privileges revoked. Three tenant tables have ENABLE/FORCE RLS and no policies, so they are inaccessible through ordinary RLS; no runtime grants. Global registry tables not granted to runtime either. Superuser maintenance can bypass RLS as expected. This is a guarded migration foundation, not proof of production privileges or service authorization.
- tests/test_knowledge_foundation.py: 18 test cases (nine offline DSN validator cases and nine opt-in DB cases). Checks guard failure, role/schema collision, replay and default state, legacy data preservation, unique and tenant composite keys, invalid approval and audit actors, JSON bounds, owner and default-deny ACL/RLS. Strict synthetic loopback DSN and explicit reset opt-in; removes inherited PG environment variables; rolls back each fixture transaction, no persistent fixture data. Refuses preexisting knowledge schema instead of deleting it.
- tools/test-platform-integration.sh and .github/workflows/tests.yml: include foundation suite in local disposable and CI integration coverage; local runner also includes previously separate auth migration suite. CI still runs on PR/main as before; no PR opened. Existing platform-db init continues to apply only migration 001. No auto migration, auth change, runtime feature flag, new route or grant.

Structural approval fields do not establish actual authority; identity binding, grant resolution, typed policy validation and immutable published version/append-only audit command enforcement belong to M01.2 onward. Scope grants referencing sources, client/sharing tables and runtime policies/grants are deferred to their approved increments. Exact identity authority contract remains unresolved. M01.3 adds scoped transaction context/RLS policies; M01.4 adds the workspace UI. No change to prior migrations or existing source access.

### Verification and next action

Owner-reported verification at 3f01e8ed870e249270092e123277e5401e37df4f: 534 Python offline tests passed, 36 skipped (nine more than M00, corresponding to the new PG-dependent foundation cases); 65 Node tests passed; syntax checks and asset build passed. Disposable PG18 integration: 79 passed, two failed in 21.14s. Both failures were incorrect test expectations for ON DELETE RESTRICT: PostgreSQL emitted psycopg.errors.RestrictViolation when deleting a workspace referenced by memberships or a membership referenced by audit events. The deletion was correctly rejected in each case. Commit 4e157217879f70612b23f2040a9e555d821d75aa corrects only these two expected exception types; migration SQL and its RESTRICT constraints are unchanged. The first run did not reach the runner's subsequent restart/backup/restore checks; compileall success was not explicitly reported. No tests executed by the assistant. Subsequent owner-reported rerun at 01491b919382ce1c25a06c2c34655c8358fbc87e (received 2026-11-27): all 81 integration test executions passed in 21.91s, zero failures or skips; the disposable PG18.6 runner completed its existing ingestion schema initialization/restart/persistence and backup/restore checks. The successful `M01.1 verification PASSED` marker from the fail-fast command also establishes successful Python compileall for server, tests and tools. The only intervening code changes were two corrected test exception assertions, so the earlier offline 534 passes, 36 environment-dependent skips, 65 Node passes and asset/syntax results remain applicable. All nine new opt-in database cases ran in the corrected suite. The runner's restart/restore smoke verifies the legacy ingestion fixture, not persistence or recovery of the new knowledge schema (its tests roll back their transactions); knowledge-specific recovery remains future work. M01.1 acceptance satisfied on reviewed owner-provided synthetic evidence, not independently executed by the assistant and not production verification. No runtime access enabled.

Reproduction commands (completed; full offline verification and corrected targeted PG rerun evidence recorded above):

```bash
cd ~/panadan-m00
git pull --ff-only
git rev-parse HEAD
git status --short
./panadan.sh verify --docker --assets
uv run --locked python -m compileall -q server tests tools
```

The disposable runner includes both auth and knowledge integration suites; the corrected run passed. No additional M01.1 verification rerun is required on the unchanged implementation. Do not use the production checkout or manually apply the migration to any real database. Rollback at this stage means leaving the feature inaccessible and reverting feature-branch code if required; no destructive schema downgrade. G1 remains pending M01.2–M01.4 and associated tests. Obtain separate M01.2 authorization after M01.1 evidence is reviewed.

## 5. M01.2 — identity and permissions (implemented, unverified)

Owner explicitly approved M01.1 completion, M01.2 implementation and use of all three UI references on 2026-11-27. D-068 records the additional UI decision; no unrelated scope added.

### Implementation and decisions within approved design

- Existing SQLite users have reusable integer primary keys and no stable profile field; session authentication joins numeric account IDs. The PostgreSQL staging auth implementation already generates opaque profile_id values, and the existing PG migration importer accepts and preserves a SQLite profile_id if present. Do not infer actual production identity or migration continuity from the branch.
- server/knowledge_identity.py adds an explicit opt-in transaction for stable random profile IDs and a unique, immutable installation namespace. Existing users receive identity anchors, not memberships or privileges; new user inserts allocate random profiles. Direct deletion, account ID/rowid rewriting, profile mutation and replacement conflicts are rejected in the opted-in store. First installation invalidates old browser sessions so login is fresh; same-installation replay preserves new sessions. No startup call or changes to existing Store, login routes or auth selector. This migration requires separately approved maintenance, backups and recovery checks before any live use. No live logout performed.
- SQLiteIdentityBridge validates the current unexpired browser session, active user and expected installation namespace in one SQLite query, returns only opaque identity reference, denies missing schema or invalid session without fallback. No username/email, legacy role, client-provided profile or numeric ID-based knowledge binding. No second authority, token copying or automatic account mapping. PG auth remains staging-only; a future cutover/restore needs separate verified namespace/profile continuity, reauthentication and grant/revocation reconciliation.
- database/migrations/005_knowledge_authorization.sql adds role_versions, membership_roles and scope_grants to the owned PG18 schema. Composite workspace keys and FKs, version uniqueness, bounded arrays, expiry/revocation checks and published role definition immutability; additive migration guard requires 004, explicit target, expected administrator and dedicated owner. New tenant tables have FORCE RLS with no policies or runtime grants. No source/operator FKs yet: only explicit workspace-scoped operational grants until M02.
- server/knowledge_authorization.py implements the internal workspace authorization and command service against a caller-owned PG transaction. Initial operational capability catalog: workspace.read, members.manage, roles.manage; two role templates (reader, administrator) as explicit proposals, no automatic assignment. Active principal + active workspace + active membership + current active pinned role version + matching explicit unexpired operational scope grant all required. No legacy admin override, wildcard, malformed-role fallback, data access, API/MCP or service authorization. Role versions may be published, assigned, retired; membership added only for an explicitly provisioned principal. Scope grants and assignments can be revoked, membership revocation revokes its assignments/grants; no self-grant or self-targeted membership changes. Grant issuance is limited to actor's effective capability and expiry. An issued grant is not automatically cascaded when its grantor later loses access; revoke target grants explicitly. Only the synthetic fixture performs initial administrator/principal bootstrap; actual reviewed provisioning, recovery and live activation remain pending.
- Commands lock the workspace row, use scoped parameterized SQL, recheck current authority and expiry, increment policy epoch and append metadata-only audit in the same transaction. Audit failure rolls back command. Permission result is not a reusable credential. No cross-store atomicity claim: auth revocation after the last check is still possible, and future sensitive operations must recheck at disclosure/dispatch. Runtime grants, trusted context, pool reset, concurrency and real end-to-end revocation enforcement are M01.3 gates. Generic policy schema enforcement and source/data scope are later scoped work. No runtime connection configured, HTTP route added, or role granted.
- tests/test_knowledge_identity.py adds five offline SQLite test cases. tests/test_knowledge_authorization.py adds 12 disposable PostgreSQL cases: guarded migration, role and scope intersection, cross-tenant reference denial, role immutability, expiry/delegation, disabled principals and revocation, session recheck, atomic audit rollback. Reuses the strict disposable DSN/rollback fixture. Local integration runner and CI job include the new suite. No new dependencies.
- ROADMAP.md and UI_DESIGN_REVIEW.md now reflect D-068; no frontend implementation or prototype code/backend import.

### Verification and remaining boundary

Assistant static review only; direct git probe failed DNS (github.com), Python 3.13.5 and pytest available but psycopg, Docker and psql absent. No locked repo tests or PostgreSQL migrations executed by assistant. Prior M01.1 evidence remains valid for 004 only. Run the full synthetic local gate and compile check from the existing disposable development checkout, not production:

```bash
bash -c '
set -euo pipefail
cd "$HOME/panadan-m00"
git pull --ff-only
git rev-parse HEAD
git status --short
./panadan.sh verify --docker --assets
uv run --locked python -m compileall -q server tests tools
echo "M01.2 verification PASSED"
'
```

Owner-reported first local verification: 537 passed, 48 skipped and two failed in 47.11s in the offline suite. Both failures are in test_knowledge_identity.py: the stable-profile test created a fresh session before asserting pre-installation session invalidation; the logout/disable/expiry test tried to use the invalidated pre-installation session. Actual observations were consistent with the intended one-time session invalidation. Commit e29867a7c278cc5373ceafdd234e055d23955860 fixes both test setups, explicitly verifies fresh login and leaves identity/authorization implementation and migrations unchanged. The offline gate stopped before Node, syntax, assets and PostgreSQL tests; no M01.2 integration result yet. Rerun the full verification command above. Expected 539 offline passes, 48 offline database-dependent skips, 65 Node passes, and 93 disposable PG integration passes; do not mark verified until actual results are reviewed. Owner-reported second run: 539 offline Python passes, 48 database-dependent skips, 65 Node passes, syntax and asset build passed. Disposable PG18.6: 92 passed, one failed in 30.75s. The remaining test, test_audit_failure_rolls_back_role_and_epoch, stopped at creation of its synthetic PL/pgSQL trigger due to malformed dollar quoting; the actual audit rollback assertion did not execute. Commit c445170380cf4855a604fd4cbc0972511ee6d148 fixes the test function body with an explicit tagged dollar delimiter and leaves implementation/migrations unchanged. Rerun bash tools/test-platform-integration.sh and Python compileall in the disposable local checkout; expected 93 passes. Earlier successful offline, Node, syntax and asset checks remain applicable because only the failing PG fixture and documentation changed. Restart/restore checks were not reached in the second run. Third local run at 22f5229d126706801f2d67235fff9e3e78f53d09: 92 passed, one failed in 28.05s; corrected audit rollback test passed, but the previously successful delegation-expiry test denied the intended permitted grant because roles.manage was absent from effective permissions. Static inspection identified mixed clock domains in the fixture: Python datetime.now set expiry while the service compares PostgreSQL clock_timestamp(). Host/container skew or clock changes are a plausible cause, not established by the supplied traceback. Commit e15b342d054714500b212a302f208637587275e6 derives expiry from the database clock, confirms the actor has both required capabilities before the denial checks, verifies denied attempts wrote no grant, and asserts the successful grant's exact member, grantor and bounded deadline. A one-hour synthetic actor window and 30-minute delegated window reduce incidental timing sensitivity; no production expiry checks or authorization code changed. Rerun the same disposable integration and compileall command, expected 93 passes; if denial recurs, investigate the new explicit precondition and database timestamps. Restart/restore still not reached. No additional runtime tests executed by assistant. Do not call profile installation or apply migrations on any real auth or owned database. No production bootstrap or restore guarantee yet. M01.2 remains unverified; M01.3 requires test evidence and explicit authorization. Existing legacy app behavior remains unchanged because no new entrypoints are wired.

## 6. Milestone ledger

| Milestone | Status | Gate |
| --- | --- | --- |
| M00 Baseline/harness | Complete — verified synthetic baseline (owner-reported) and reviewed harness | G0 passed |
| M01 Workspace security | M01.1 verified synthetic; M01.2 offline/frontend and audit rollback passed, delegation expiry fixture corrected, targeted rerun pending; M01.3–M01.4 not started | G1 pending |
| M02 Resources/privacy | Not started | G1 |
| M03 Objectives/runs | Not started | G2 |
| M04 AI gateway/budgets | Not started | G3 |
| M05 Observations/aggregation | Not started | G4 |
| M06 Knowledge/review/taxonomy | Not started | G5 |
| M07 Customer Intelligence | Not started | G6 |
| M08 Content Intelligence | Not started | G7 |
| M09 Packages/API/MCP | Not started | G8 |
| M10 Extra sources/distribution | Not started | G9 |
| M11 Synthetic E0 readiness | Not started | G10 |
| M12 Real-data E1–E3 | Not started / unauthorized | G11 + private approvals |
| M13 Release/E4 | Not started / unauthorized | Reviewed pilot + release approval |

Next action: review actual M01.2 local test output, correct any failures, then obtain explicit authorization for M01.3. No automatic account mapping or runtime activation. Migration, service and test code committed only on authorized branch; no live migration, login/session mutation, runtime app wiring, source records, external connections, paid requests or production changes. Protected refs must be rechecked after commit.
