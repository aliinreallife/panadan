# Controlled Panadan web-only release — 2026-11-02

**Source-only playbook, not evidence that production has been updated.**
Current live stack was last independently verified on 2026-11-01.
The new app image was published successfully by the GHCR workflow on
`cb5d0823aa5d81a72c089375043b32c24d455eaf`. This release only
recreates **Panadan Web**; it must not restart/reconfigure VPN, owned PG18,
gateway, shared Plane proxy, or Plane Web. It **does not migrate SQLite auth to
PostgreSQL** or turn on MCP OAuth.

## Release artifact

```text
ghcr.io/aliinreallife/panadan-web:sha-cb5d0823aa5d81a72c089375043b32c24d455eaf
```

Do not use GHCR `:main` or `:latest`. The latest *repository* commit may be
newer than the latest *published web image* because documentation/tests/ops
changes do not trigger `.github/workflows/images.yml`. Image pulls require
private GHCR `read:packages` access. Pulling does not deploy.

**Offline recovery test:** The pre-release SQLite backup can be verified on
a trusted independent WSL/Linux machine with
`bash tools/verify-offsite-auth-restore.sh ENCRYPTED_AUTH_SQLITE.age
OFFSITE_AGE_IDENTITY`. See
[the SQLite recovery drill](BACKUP_AUTOMATION.md#independent-sqlite-auth-restore-verification-web-release-gate)
for safe prerequisites, limitations and expected PASS results. Do not
paste files, keys or customer/account data into GitHub or chat.

**Hard preconditions before writing production:** Operator independently
verified an encrypted, off-host SQLite auth backup **and performed a safe
restore drill**; existing VPS-local `prodctl.sh` and private overlay behavior
reviewed against `tools/prodctl-production.sh`; the new source-controlled
controller's read-only plan and smoke checks pass; explicit maintenance window
and a previous pre-pulled pinned image for rollback. If these are not true,
**stop after read-only inspection** rather than manually bypassing a guard.
Neither the Python selector for `postgres-staging` nor any production OAuth
feature flag is approved for this web update.

## 1. VPS read-only checks (safe to execute now)

These commands show no secret environment values and change no Docker
container, network or database. Stop and investigate any failed check.

```bash
cd /home/panafor/panadan
git status --short
git switch main
git pull --ff-only

# New controller is NOT the untracked VPS-local prodctl.sh.
sudo bash tools/prodctl-production.sh plan
sudo bash tools/prodctl-production.sh check
sudo bash tools/smoke-production-web.sh

# Existing running image reference; write down for manual rollback.
sudo docker inspect panadan-web-1 --format '{{.Config.Image}}'
```

The plan validates the real private Compose overlays *without printing*
interpolated secrets. It fails closed if they differ from the expected
topology, if SQLite no longer uses a named persistent `/data` volume, if a
`postgres-staging` selector or staging DSN appears in the effective web
environment, or if unapproved OAuth mode is active. This may **not** yet pass
on the current VPS without reconciling its private overrides; refusal is not
authorization to change/recreate services. In that case, share only the
generic `REFUSED:` reason; do **not** send `docker compose config` output
or `.env` content.

`smoke-production-web.sh` checks VPN health and the read-only `tun0`
route to the source, public HTTPS health, login `Secure`/`HttpOnly`
nonce-cookie attributes, Plane home/intake availability, and expected 401
for anonymous REST and MCP. It never performs a login, reads a call,
retrieves a transcript, or logs bearer headers. A 200 on intake does not
prove exact original content: if you have an independently backed-up trusted
intake HTML, supply `PANADAN_TRUSTED_INTAKE_FILE` to check its bytes too.

## November 2 VPS preflight incident: do not force rollout

The operator's first run on the live VPS confirmed the old
`panadan-web:cac4b36` image is still serving, and the read-only
`smoke-production-web.sh` passed. The release was **NOT deployed**:

- `plan` / `check` refused at the **Panadan production service
  invariants** check. This can mean a difference between the actual
  private effective Compose and the new stricter repo guard. It does
  **not** prove any specific failing field yet. The new diagnostic
  now reports only a fixed allowlisted `SAFE CHECK:` category. Run
  `sudo bash tools/prodctl-production.sh plan` after updating the repo,
  and inspect only that category; **never paste the raw rendered
  `docker compose config` or private `.env` contents**.
- `sudo docker pull` failed `unauthorized` because the published
  image is private GHCR and the **root Docker client** lacked usable
  package-read credentials. Git SSH access to the repository does not
  itself authenticate Docker. Use a GitHub account authorized for the
  package and a scoped credential with `read:packages`; authenticate
  using `docker login ghcr.io -u ACCOUNT` and its interactive token
  prompt, not a token printed to the shell/issue. Prefer a temporary,
  root-owned `DOCKER_CONFIG` and log out after the pull. Pulling alone
  does not alter running containers.
- `sudoedit .env.app` failed by design because sudoedit refuses to
  edit files inside an unsafe user-writable directory. Do **not**
  disable sudoedit safety settings or change directory permissions
  to bypass the check. First confirm file owner and mode using
  `stat -c '%U:%G %a' .env.app` (only metadata). If owned by
  your account, open with your non-root editor; if root-owned,
  edit a *staged copy in a root-only, non-user-writable directory*
  using `sudoedit`, verify it, then explicitly install it back
  while retaining the original owner and mode. Avoid exposing
  `.env.app` in terminal output or Git.
- The final smoke `--expected-image` failure is expected: the
  running image was still the old one. **Do not rerun the apply
  command or mark restored-backup acknowledgment until the preflight
  and independent recovery drill pass.**

When `SAFE CHECK:` identifies a discrepancy, compare the intended
security property against privately held overlays and inspect Docker
metadata *without dumping environment variables*. A still-functional
service is not sufficient evidence for relaxing or overriding
security checks.

## November 2 Caddy preflight follow-up (no proxy change)

The operator corrected only the reviewed **Compose image selectors**, with
a tag pointing to the **same running VPN image ID**, and cached the private
GHCR web release through a temporary authenticated root Docker session.
The new Panadan, Plane and gateway topology guards **all passed**, but the
original Caddy **text-site-block regex** rejected the actual Caddyfile.
A read-only inspection showed a literal `dan.panafor.com` block while
`plane.panafor.com` was not present as a top-level literal block.
Inside the existing proxy, `caddy adapt --config /etc/caddy/Caddyfile
--adapter caddyfile` returned successfully, and the adapted JSON
contained **explicit host matchers for BOTH domains** (one server; nested
routes). This is a valid configuration form that the textual check missed.

The updated repo preflight now:
- Compares SHA-256 of the **operator-reviewed host Caddyfile** with the
  file mounted inside the running Plane Caddy container, reporting only
  pass/fail and never file contents or hashes;
- Executes `caddy adapt` against that existing mounted file **without
  reloading or restarting Caddy** and validates explicit Plane and Panadan
  host matchers, including nested subroutes;
- Refuses on mismatch, missing routes, invalid adapted JSON or missing
  proxy access. The separate HTTPS health and Plane intake checks remain.
- Does not claim the adapted file is identical to the server's **currently
  loaded runtime configuration**, nor validate all private upstream routing.

**Next read-only VPS checks after this PR is merged:**

```bash
cd /home/panafor/panadan
git pull --ff-only
sudo bash tools/prodctl-production.sh plan
sudo bash tools/prodctl-production.sh check
sudo bash tools/smoke-production-web.sh
sudo docker inspect panadan-web-1 --format '{{.Config.Image}}'
```

Do **not** deploy until the independent encrypted off-VPS **SQLite auth
restore drill** is confirmed and the existing VPS-local
`prodctl.sh`/private overlay behavior has been reconciled.

## 2. Operator-controlled application image update

**Only after** the above passes, an independent SQLite backup/restore drill
has succeeded, and the private overlay image selector has been reviewed:

```bash
cd /home/panafor/panadan
RELEASE='ghcr.io/aliinreallife/panadan-web:sha-cb5d0823aa5d81a72c089375043b32c24d455eaf'

# Pull new image to cache without changing any running container.
sudo docker pull "$RELEASE"

# Back up the existing *private* .env.app on the VPS, mode 600, outside Git.
# Never paste its contents or the original intake/backup keys into issues.
sudo install -d -m 700 /root/panadan-release-backups
sudo cp -p .env.app /root/panadan-release-backups/env.app.before-web-release

# Review existing private overrides and set ONLY the web image to $RELEASE.
# If the private compose.web.release.yaml hard-codes another web image,
# reconcile the override under operator review; do not bypass the guard.
sudoedit .env.app

# Must resolve the exact intended image without printing secret config.
sudo bash tools/prodctl-production.sh plan
sudo bash tools/prodctl-production.sh check

# This is a LIVE web-only recreation; expected short web interruption.
# The flag acknowledges verified off-VPS backup + restore evidence.
sudo bash tools/prodctl-production.sh deploy-web --apply \
  --expect-image "$RELEASE" --ack-restored-backup

# Verify running web actually uses the pinned image.
sudo bash tools/smoke-production-web.sh --expected-image "$RELEASE"
```

The reviewed controller refuses if `$RELEASE` is not the effective
Compose `web.image`, is missing locally, or if the private network/Plane
topology fails. It calls `docker compose ... up -d --no-deps --no-build
--pull never web` with the **full** private ingress+HTTPS overlays and any
existing owned-auth bridge. It does **not** pull, rebuild, restart the
VPN, recreate Plane, or change production auth. The backup acknowledgment
is an operator assertion, **not** an automatic backup verifier.

## November 2 live release outcome and hardened controller follow-up

**Operator-confirmed running state:** The web-only release of
`ghcr.io/aliinreallife/panadan-web:sha-cb5d0823aa5d81a72c089375043b32c24d455eaf`
**succeeded** at the container level. Docker Compose reported `Started`
in less than a second, but the controller's **immediate** first public HTTPS
`/healthz` check returned HTTP 502, causing the controller to report a
deployment failure. The operator checked again after the container had been
running for 47 minutes: HTTPS `/healthz` was **200**, the web container was
running with **zero restarts**, and the independent full
`smoke-production-web.sh --expected-image` **PASSed**. The running VPN remained
`panadan-vpn:local`, healthy and unchanged. **No rollback was executed.**
This evidence fits a transient startup/readiness delay but cannot prove the
specific cause without diagnostics. Authenticated end-to-end browser
acceptance and original Plane intake byte-fingerprint remain separate checks.

### What the updated controller does

After an explicit `deploy-web`, it now allows a **bounded** HTTPS readiness
period (12 attempts, 5 seconds between failed attempts; only exact HTTP 200
passes) before running the full post-deploy smoke. It never interprets
Docker's `Started` message as readiness, and it still fails if the Web
does not become healthy. This does **not** change the baseline healthy check
required before a normal deploy. The wait loop does not authenticate or touch
the databases, shared proxy, VPN or Plane.

A distinct `rollback-web` command is provided for an **unhealthy Panadan
Web**; unlike `deploy-web`, it does *not* require the failing public Panadan
`/healthz` endpoint to be healthy before recovery. All other strict
preflight network/volume/security validations, Caddy adapter checks, cached
commit-pinned image agreement, independent backup acknowledgment and Plane
HTTPS checks remain mandatory.

**Operator review required before a rollback**: restore ONLY the Web
`image:` value in the private
`data/ingress/compose.web.release.yaml` to the exact cached previous pinned
reference (currently `panadan-web:cac4b36`), keep a secured copy of the
current override, then verify with the read-only `plan`. When a rollback
is actually required and authorized:

```bash
cd /home/panafor/panadan
sudo bash tools/prodctl-production.sh plan

sudo bash tools/prodctl-production.sh rollback-web --apply \
  --expect-image panadan-web:cac4b36 --ack-restored-backup

sudo bash tools/smoke-production-web.sh \
  --expected-image panadan-web:cac4b36
```

The rollback command uses `docker compose ... --dry-run up` followed by
`up -d --no-deps --no-build --pull never web` with the existing private
overlays and optional auth bridge, **never** `down` or restart of the VPN,
Caddy, Plane, gateway or PostgreSQL. It verifies HTTPS 200 and runs the
full read-only smoke. It never overwrites `/data/auth.sqlite`.
If the issue is only a transient 502 and the full smoke is already
passing, **do not roll back**.

## 3. Manual user acceptance tests — after successful smoke

In an incognito browser, use the normal real credentials **locally**
(do not enter them into a terminal transcript or this issue):

- Open `https://dan.panafor.com/login`, sign in, check `/dashboard`
  with a real session, then sign out. Re-login and verify an existing
  legitimate account still works (SQLite identity persistence).
- Verify the expected call list, filters, operator profile and stats
  against authorized data; confirm no raw transcript appears to a reader
  lacking the separately granted transcript capability.
- Verify a dedicated, known valid, least-privileged API token still works
  for its allowed endpoint, and that a wrong-scope token cannot retrieve
  sensitive data. Do not paste the bearer token or any response body.
- Verify existing **legacy MCP** manual bearer tools work with an approved
  client. This release does **not** provide working ChatGPT/Claude OAuth.
  `/.well-known/oauth-protected-resource` returning 404 in legacy mode is
  expected; do not switch live auth modes to make it return 200.
- Check `https://plane.panafor.com/` and the original intake page manually.
  Prefer byte-for-byte content comparison to the independently trusted
  original. No Plane Web rebuild is authorized.
- Inspect the app's recent metadata-only errors, VPN health and Odoo
  connectivity without running write queries or sharing real call rows.

**Stop criteria:** mismatched image, failed login, wrong auth scope,
reporting read unavailable, transcript leak, Plane/intake changes, or
non-`tun0` source route. Do not widen permissions or disable security to
force a passing test.

## 4. Deliberate rollback (no automatic destructive actions)

Before deploy record the old `docker inspect panadan-web-1` image reference
and keep the previous image local. On failure, restore only the intended
private `.env.app` web-image selection (or reviewed web release overlay)
to the old pinned image; **re-run the read-only plan** and
`rollback-web --apply --expect-image OLD_PINNED_IMAGE --ack-restored-backup`
during an approved recovery window, then repeat the smoke test. The
recovery path deliberately does not require the failed Panadan baseline
to be healthy. Existing
SQLite volume is **not** removed or overwritten; no automatic database
restore is attempted. Never use broad `docker compose down`, `docker
prune`, `git reset --hard`, shared proxy recreation, or VPN replacement
as a shortcut.

A rollback of the **web image** does not undo any live auth data changes
made by users while the new web image was serving traffic; do not restore a
stale SQLite backup over live accounts just to roll back this release.

## Outstanding production blockers

- #56's former closed state does not prove fresh-host reproduction; existing
  private overlay/controller comparison still needs operator evidence.
- #55 full recurring offsite backup and restoration/monitoring is incomplete.
- #62 Plane intake persistence across Plane Web reconstruction is incomplete.
- #70 PG18 auth remains staging-only; #57/#58/#59/#64 OAuth and client
  interoperability are not completed in the live environment.
