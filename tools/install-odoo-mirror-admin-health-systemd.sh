#!/usr/bin/env bash
# Create-only installer for read-only, aggregate-only admin telemetry publisher.
# Never touches the existing sync timer, Odoo, production network or web.
# Installation does NOT deploy/replace the production web image or mount.
set -euo pipefail
set +x
umask 077

[[ "${1:-}" == install && "${2:-}" == --ack-admin-health-publisher &&
   $# -eq 2 ]] || {
  echo "Usage: $0 install --ack-admin-health-publisher" >&2
  exit 2
}

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE=/etc/systemd/system/panadan-mirror-health-publisher.service
TIMER=/etc/systemd/system/panadan-mirror-health-publisher.timer
RELEASES=/opt/panadan-mirror-health/releases
STAGE=panadan-mirror-staging-pg18

command -v git >/dev/null
command -v python3 >/dev/null
command -v sudo >/dev/null
command -v systemctl >/dev/null
sudo -v

[[ -z "$(git -C "$ROOT" status --porcelain)" ]] || {
  echo "STOP: Only a reviewed clean Git release may be installed" >&2
  exit 2
}
REV="$(git -C "$ROOT" rev-parse HEAD)"
[[ "$REV" =~ ^[0-9a-f]{40}$ ]] || exit 2
[[ "$(git -C "$ROOT" config --get remote.origin.url)" == *panadan* ]] || exit 2
[[ -f "$ROOT/tools/publish-odoo-mirror-admin-health.py" ]] || exit 2

[[ "$(sudo -n docker port "$STAGE" 5432/tcp)" == "127.0.0.1:55432" ]] || {
  echo "STOP: Isolated staging database required" >&2
  exit 2
}
[[ "$(sudo -n docker exec "$STAGE" psql -X -Atq -v ON_ERROR_STOP=1 \
  -U panadan_stage_owner -d panadan_ci -c \
  "SELECT current_database() || ':' || current_setting('server_version_num');")" == "panadan_ci:180006" ]] || {
  echo "STOP: Staging database identity drift" >&2
  exit 2
}
if sudo -n test -e "$SERVICE" || sudo -n test -e "$TIMER"; then
  echo "STOP: Health publisher systemd units already exist; no overwrite" >&2
  exit 2
fi
DEST="$RELEASES/$REV"
if sudo -n test -e "$DEST"; then
  echo "STOP: Immutable health release exists; no overwrite" >&2
  exit 2
fi
echo "=== Install pinned root-owned publisher ==="
sudo -n install -d -m 0755 -o root -g root "$RELEASES"
sudo -n install -d -m 0755 -o root -g root "$DEST"
git -C "$ROOT" archive --format=tar "$REV" \
  tools/publish-odoo-mirror-admin-health.py |
  sudo -n tar -xf - -C "$DEST" --no-same-owner
sudo -n chown -R root:root "$DEST"
sudo -n chmod -R go-w "$DEST"
sudo -n chmod -R a+rX "$DEST"

echo "=== Install aggregate-only 1-minute metadata timer ==="
sudo -n tee "$SERVICE" >/dev/null <<UNIT
[Unit]
Description=Panadan Odoo mirror aggregate admin-health snapshot publisher
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=oneshot
User=root
Group=root
UMask=0022
ExecStart=/usr/bin/python3 $DEST/tools/publish-odoo-mirror-admin-health.py publish
TimeoutStartSec=60s
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
UNIT
sudo -n chmod 644 "$SERVICE"

sudo -n tee "$TIMER" >/dev/null <<'TIMER_UNIT'
[Unit]
Description=Publish Panadan mirror admin health every minute

[Timer]
OnCalendar=*:0/1
AccuracySec=20s
Persistent=true
Unit=panadan-mirror-health-publisher.service

[Install]
WantedBy=timers.target
TIMER_UNIT
sudo -n chmod 644 "$TIMER"
sudo -n systemctl daemon-reload
sudo -n systemd-analyze verify "$SERVICE" "$TIMER"

# Require a healthy first publication before enabling unattended operation.
sudo -n systemctl start panadan-mirror-health-publisher.service
sudo -n test -s /var/lib/panadan-mirror-staging/health/mirror-health.json

sudo -n systemctl enable --now panadan-mirror-health-publisher.timer
echo "PASS: Aggregate admin health published; one-minute timer enabled"
echo "Production web unchanged. Mount the publisher's HEALTH DIRECTORY read-only"
echo "through the separately reviewed production deployment controller."
