# Panadan disaster-recovery runbook — review-only baseline

Status: **Not yet drill-proven.** Written for issue #63, and for the current
shared Plane/Caddy HTTPS installation. This is an ordered recovery checklist,
NOT a one-command production restore. Do not run these steps against the live
VPS merely to test them. First rehearse on a disposable independent host.

Source-of-truth: [production topology](PRODUCTION_OPERATIONS.md),
[encrypted backup procedures](BACKUP_AUTOMATION.md),
[owned PostgreSQL setup](ONE_COMMAND_OWNED_PG_SETUP.md), and the
[Plane intake preservation check](PRODUCTION_OPERATIONS.md#plane-custom-intake-preservation-gate-62).

## 1. Define service recovery objectives and ownership

Before enabling production cutover or regular backup pruning, the operator
must record and approve the following in a private operations system:

| Decision | Status / owner action |
| --- | --- |
| Recovery owner and a second reviewer | **Not yet assigned** |
| Account-data RPO | **Not yet approved**: determine maximum tolerable lost account changes |
| Platform/PostgreSQL RPO | **Not yet approved**: separate from source Odoo data |
| Public dashboard/MCP RTO | **Not yet approved**: includes VPN, proxy, auth and DNS restoration |
| Alert delivery and escalation | **Not yet verified** |
| Offline decryption and backup-key recovery | **Not yet comprehensively verified** |
| Approved restore environment and switchback owner | **Not yet defined** |

A successful local checksum or empty-schema PostgreSQL restore cannot establish
these objectives. Do not silently choose RPO/RTO values or mark them achieved.

## 2. Preserve evidence, do not compound the outage

1. Record incident time, host, failing symptom, last known-good image/commit,
   latest verified off-VPS backup identifiers (not their contents), and who
   authorized recovery.
2. Distinguish a temporary Panadan outage from loss of the entire shared host.
   When Plane remains working, **do not recreate or stop its proxy/web services**
   as a Panadan diagnostic.
3. Avoid broad Docker down, volume deletion, system cleanup/prune, firewall
   edits, service reinitialization, or direct SQL writes to Odoo. The external
   source reporting database is not Panadan-owned.
4. Inspect the existing production controller's read-only check and status
   commands. Do not use deploy-web/deploy-proxy during triage: they recreate
   containers.
5. Treat a current SQLite authentication database as the source of truth
   until #70 has completed a validated cutover. Never overwrite it as a test.

## 3. Confirm recovery materials outside the failed host

Keep the *locations and owners* in a private vault/inventory, not the secret
values, tokens, backups, customer records or identities in the Git repository.

- Pinned container images or a verified digest/archive, and a matching
  immutable source commit/lockfiles; do not rely on moving latest/main tags.
- Approved Panadan app configuration, read-only Odoo connection settings,
  OpenVPN client credentials, and the real production Compose/HTTPS overlays.
- Original Plane Compose configuration, plane.env, external Caddy override
  and Caddyfile, plus the **correct** existing TLS /data and /config volumes.
- Original custom Plane intake.html and any required assets, saved outside
  the Plane web container with a trusted hash (issue #62).
- The currently active SQLite auth backup (online snapshot, not an
  uncoordinated copy of WAL-mode database files), encrypted off-VPS.
- All Panadan-owned PostgreSQL 18 encrypted archives required for the
  recovery point, including auth data if PostgreSQL auth was already enabled.
- The independent AGE private identity, securely escrowed **off the VPS**;
  the public AGE recipient alone cannot decrypt a backup.
- Ignored platform credentials, runtime auth-role credentials, and any
  external OAuth identity-provider/issuer configuration. PostgreSQL pg_dump
  does not include cluster-global role passwords.

Do not print any private file when checking availability. If a required key,
image, backup or production overlay is missing, declare the recovery blocked;
do not generate replacement account/owner passwords over existing volumes.

## 4. Rehearse a disconnected data restore first

1. On an independent trusted machine, obtain a *specific* encrypted off-site
   artifact and independently verify its retrieved bytes/checksum.
2. Decrypt using an escrowed private age identity only on that machine.
   Use private temporary storage; discard temporary plaintext afterward.
3. Restore an authenticated SQLite snapshot into a **new disposable location**.
   Check SQLite integrity, schema, account/role counts and a synthetic test
   login. Exercise disabled users, revocation and transcript permissions.
   Do not restore over a running /data/auth.sqlite or publish plaintext.
4. For PostgreSQL 18, restore a custom-format archive into a separately
   provisioned **network-isolated ephemeral cluster**. Verify expected
   panadan_ingest and panadan_auth tables for the chosen backup date,
   representative record counts, constraints and ACL/role assumptions.
   Reprovision/reapply reviewed roles because pg_dump does not save global
   roles/passwords. Do not expose the test database to the internet or VPN.
5. Existing verify-offsite-platform-restore.sh is suitable for the documented
   **pre-auth, zero-source** snapshot and optional additive auth-schema
   rehearsal. It is **not** proof that a later populated PostgreSQL auth
   archive can be recovered. A populated post-cutover restore drill remains
   required in #55/#70.

Record only pass/fail evidence, artifact identifiers, date, schema counts and
reviewer in the private recovery journal; no raw customer rows or credentials.

## 5. Stage infrastructure on a replacement host

Only after the disconnected data restores are valid, and with an approved
maintenance plan:

1. Provision the supported host/OS, Docker Compose and required pinned
   images. Verify storage capacity, backup destination access and secret
   management before starting services.
2. Restore *only the approved private configuration* from escrow. Keep Odoo
   read-only source credentials separate from Panadan's own database roles.
3. Recreate Panadan's independently owned PostgreSQL persistent volume and
   restore from the reviewed encrypted backup; validate its schema and roles.
   Never initialize/reset an existing production volume to fix a restore
   error. Rehearse on a spare host before attempting a production recovery.
4. Recreate private Docker networks/topology from the reviewed Compose
   configurations. Internal networks must stay private; app/web must retain
   the approved VPN namespace relation and source route via tun0.
   The repository owned-pg plan and verify can check a *prepared* host,
   but owned-pg apply changes real networks/roles and requires explicit review.
5. Restore the SQLite auth state into the designated **new** app volume if
   production still uses SQLite. Do not substitute the platform DB backup
   for pre-cutover authentication data.
6. Restore/start the Panadan VPN and prove the approved reporting DB accepts
   read-only SELECT 1 through the tunnel. Never grant CREATE or other Odoo
   writes to resolve a connectivity failure (issues #22/#26).
7. Stage the pinned Panadan web application and its private gateway with
   secure cookies, correct HTTPS public origin and no unapproved host ports.
8. If the entire shared proxy stack must also be recovered, restore the
   authoritative Plane configuration and Caddy data/config from their
   own verified source; preserve Plane routes and intake.html. Do NOT
   recreate a *still-running* shared Plane proxy to recover only Panadan.
9. Keep public traffic disabled until the checklist below passes.
   Change DNS/Caddy routing only with an authorized rollback plan.

The existing VPS-local prodctl.sh and private overlays are not yet fully
reproducible from this repository. The approved recovery must use the
actual backed-up configuration, not assume checked-in templates are the
entire running deployment (issue #56).

## 6. Required go/no-go tests before public cutover

| Boundary | Required observation |
| --- | --- |
| TLS / origin | Correct certificate, HTTPS origin and secure session cookie |
| Existing Plane | Original Plane app serves, and /intake.html exact bytes match trusted original |
| VPN route | tun0 route and approved source PostgreSQL read-only SELECT 1 pass |
| Auth | Test login, session/logout, revoked account and bearer denial pass |
| API/MCP | Deny unauthenticated and cross-scope calls; no raw transcript without separate capability/audit |
| Backups | Selected restored SQLite/PG data and permissions verified independently |
| Ingress | No unexpected public DB, gateway or internal network ports |
| OAuth | If enabled only: issuer, audience, PKCE/resource metadata and actual client sign-in verified |
| Monitoring | Backup freshness, VPN/TLS health, 5xx/error rates, disk space and alert delivery tested |

The existing commands bash tools/check-plane-intake.sh fingerprint and
bash tools/check-plane-intake.sh verify /secure/original-intake.html provide
read-only page checks, **not** full preservation. Use reviewed production
controller check/status only for existing service topology.

## 7. Rollback, sign-off and future drills

- Keep last known-good images, old configuration and encrypted restore
  points available until the new stack is confirmed and signed off.
- If only the Panadan upstream fails while the shared Caddy remains healthy,
  prefer reverting the **reviewed Panadan route** instead of rebuilding
  Plane Web. If a shared proxy rollback is necessary, it can interrupt both
  products and requires an explicit maintenance decision.
- Never run a restore or migration on live account data as part of routine
  smoke tests. Preserve prior SQLite auth during and after any future
  PostgreSQL auth cutover until a separate rollback plan is approved.
- Record actual achieved RPO/RTO, restoration duration, missing materials,
  test results and remediation privately; do not write customer data or
  secrets into GitHub issues or CI logs.
- Rehearse on a disconnected alternate host after backup-format, schema,
  authorization, Docker image or OAuth changes; agree a recurring drill
  cadence with the recovery owner.

**Open gates:** #55 (automated delivery, escrow, post-auth restore, alarms);
#56 (reproducible hardened ingress); #62 (actual persistent Plane intake);
#63 (full tested restore and RPO/RTO); #70 (auth storage cutover); #57/#58/#23
(remote OAuth/MCP), #22 (source least privilege). These must not be closed
solely because this runbook is checked in.
