# Admin mirror sync-status card — isolated production rollout

**Status:** web-only PR #98; **not yet deployed**. The aggregate health
publisher is independently installed and scheduled on the VPS.
The ongoing five-minute Odoo mirror sync and one-minute publisher are
not touched by this change.

This guide is deliberately isolated from the 64-file draft mirror PR #97.

## What the card does

On the main admin dashboard only, show aggregate local mirror record/revision
counts, completed timestamp, lag, optional catch-up window, VPN state,
scheduler state and telemetry freshness. The browser refreshes every minute.
It does NOT switch the production dashboard, API, or MCP away from the
existing Odoo reporting read path.

The endpoint is GET /dashboard/mirror-health. It requires an authenticated
admin with users:manage, sends Cache-Control: no-store and returns no
customer records or source identifiers.

## Phase 1 — read-only VPS checks

~~~bash
cd ~/panadan
sudo bash tools/prodctl-production.sh plan
sudo bash tools/prodctl-production.sh check
sudo bash tools/smoke-production-web.sh
sudo systemctl status panadan-mirror-health-publisher.timer --no-pager
sudo test -s /var/lib/panadan-mirror-staging/health/mirror-health.json
sudo docker inspect panadan-web-1 --format '{{.Config.Image}}'
~~~

The publisher's file is a small whitelisted metadata-only JSON snapshot at
/var/lib/panadan-mirror-staging/health/mirror-health.json. Never publish its
parent directory, any staging database volume, secret file or Docker socket.
The web process must not gain staging DSN, VPN or Docker permissions.

## Phase 2 — build/review an immutable web image

- The private GHCR workflow in .github/workflows/images.yml publishes on
  **main push** or manual dispatch. A PR CI docker build does not
  necessarily publish a pullable image.
- Wait for CI, independent review and an authorized merge of this
  small web-only PR, *not PR #97*.
- Pin the resulting image by exact SHA/digest, not :main.
- Confirm the image exists and is pulled locally before deployment.
- Keep the previously running image cached for rollback.
- The production web controller requires independently verified SQLite
  auth recovery/restore acknowledgement. Do not substitute the mirror's
  no-new-backups choice or bypass this protection.

## Phase 3 — reviewed private Compose overlay

Add the following **read-only bind mount** to the *existing* private
web service override, preserving the named SQLite /data volume
and every existing network and ingress setting:

~~~yaml
services:
  web:
    volumes:
      - /var/lib/panadan-mirror-staging/health:/run/panadan:ro
~~~

When editing private Compose overrides, beware that volume merge/override
behavior depends on file order and target paths.
**Never replace the existing /data named volume.**
Verify effective mounts privately with the controller's read-only plan,
rather than printing full rendered Compose (may expose credentials).

**Mount the directory, not the JSON file.** The publisher writes atomically
using rename, so a single-file bind might hold a stale inode.
Verify the production web UID can read the directory and file without
widening unrelated permissions.

## Phase 4 — controlled web-only deployment

After CI, recovery, mount and image gates pass, use the reviewed controller.
The documented verb is:

~~~bash
sudo bash tools/prodctl-production.sh deploy-web --apply \
  --expect-image THE_APPROVED_PINNED_IMAGE --ack-restored-backup
~~~

This is intentionally **not yet ready to run**. It recreates production
web, and requires the exact image to be available and reconciled
with the private Compose selector. Do not run bare panadan.sh up,
base docker compose up, or PR #97 for this dashboard change.

## Phase 5 — acceptance

- Logged out: GET /dashboard/mirror-health returns 401.
- Signed-in non-admin: 403; no sync-status card.
- Signed-in admin: card updates, shows aggregate counts, no customer rows.
- VPN down: warning while telemetry is fresh.
- Publisher stale >3 min: unavailable, never stale green.
- New file replaces are readable inside web container across renames.
- HTTPS/Plane smoke, browser login, API/MCP and existing reporting still pass.

## Rollback

Restore the prior pinned web image in the private release selector,
verify the controller's read-only plan, then use its web-only rollback
verb. The passive telemetry mount is ignored by the old image.
Neither staging sync service changes in a rollback.
