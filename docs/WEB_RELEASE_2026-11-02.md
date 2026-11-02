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
`deploy-web --apply --expect-image OLD_PINNED_IMAGE --ack-restored-backup`
during an approved recovery window, then repeat the smoke test. Existing
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
