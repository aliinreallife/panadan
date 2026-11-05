#!/usr/bin/env bash
# Deploy a pinned, ROOT-OWNED copy of the opt-in incremental STAGING worker.
# Never run a privileged systemd service directly from a user-writable git
# checkout. Create-only install; upgrades require a reviewed new release.
# No backups, no full-view scans, no production dashboard/API/MCP changes.
set -euo pipefail
set +x
umask 077

[[ "${1:-}" == install && "${2:-}" == --ack-scheduled-sensitive-sync &&
   $# -eq 2 ]] || {
  echo "Usage: $0 install --ack-scheduled-sensitive-sync" >&2
  exit 2
}

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXPECTED_REPO=aliinreallife/panadan
STAGE=panadan-mirror-staging-pg18
SERVICE=/etc/systemd/system/panadan-mirror-incremental.service
TIMER=/etc/systemd/system/panadan-mirror-incremental.timer
RELEASES=/opt/panadan-mirror-incremental/releases

command -v git >/dev/null
command -v tar >/dev/null
command -v sudo >/dev/null
command -v df >/dev/null
command -v systemctl >/dev/null
sudo -v

[[ -z "$(git -C "$ROOT" status --porcelain)" ]] || {
  echo "STOP: The reviewed working tree is not clean" >&2
  exit 2
}
REV="$(git -C "$ROOT" rev-parse HEAD)"
[[ "$REV" =~ ^[0-9a-f]{40}$ ]] || exit 2
[[ "$(git -C "$ROOT" config --get remote.origin.url)" == *panadan* ]] || {
  echo "STOP: Repo does not match the expected Panadan project" >&2
  exit 2
}
[[ -f "$ROOT/server/odoo_mirror_incremental.py" &&
   -f "$ROOT/tools/run-odoo-mirror-incremental-cycle.sh" ]] || {
  echo "STOP: Approved incremental runtime is missing" >&2
  exit 2
}
bash -n "$ROOT/tools/run-odoo-mirror-incremental-cycle.sh"
if git -C "$ROOT" ls-files -s server tools/run-odoo-mirror-incremental-cycle.sh |
   grep -q '^120000 '; then
  echo "STOP: Refusing symlink entries in privileged runtime" >&2
  exit 2
fi

[[ "$(sudo -n docker port "$STAGE" 5432/tcp)" == 127.0.0.1:55432 ]] || {
  echo "STOP: Staging endpoint is not isolated" >&2
  exit 2
}
STATE="$(sudo -n docker exec "$STAGE" psql -X -Atq -v ON_ERROR_STOP=1 \
  -U panadan_stage_owner -d panadan_ci -c \
  "SELECT (SELECT count(*) FROM panadan_ingest.source_records
          WHERE source_key='odoo_calls_full_v1')::text || '|' ||
          (SELECT enabled::text FROM panadan_ingest.sources
          WHERE source_key='odoo_calls_full_v1') || '|' ||
          (SELECT cursor->>'pass' FROM panadan_ingest.sync_checkpoints
          WHERE source_key='odoo_calls_full_v1'
            AND stream='view_reconciliation_v1') || '|' ||
          (SELECT cursor->>'last_id' FROM panadan_ingest.sync_checkpoints
          WHERE source_key='odoo_calls_full_v1'
            AND stream='view_reconciliation_v1');")"
IFS='|' read -r records enabled pass last_id <<< "$STATE"
[[ "$records" =~ ^[0-9]+$ && "$records" -ge 96022 &&
   "$enabled" == false &&
   "$pass" =~ ^[0-9]+$ && "$pass" -ge 3 &&
   "$last_id" == 0 ]] || {
  echo "STOP: Full mirror is not at a completed pass with source disabled" >&2
  exit 2
}

AVAILABLE="$(df -Pk /var/lib/panadan-mirror-staging | awk 'NR==2 {print $4}')"
[[ "$AVAILABLE" =~ ^[0-9]+$ && "$AVAILABLE" -ge 6291456 ]] || {
  echo "STOP: Less than the 6 GiB staging disk safety floor" >&2
  exit 2
}
[[ -f /home/panafor/.config/panadan-mirror-staging/writer.dsn &&
   -s /home/panafor/panadan/.env.db ]] || {
  echo "STOP: Private approved staging/source configuration missing" >&2
  exit 2
}

if sudo -n test -e "$SERVICE" || sudo -n test -e "$TIMER"; then
  echo "STOP: Existing systemd units require separate review; will not overwrite" >&2
  exit 2
fi
DEST="$RELEASES/$REV"
if sudo -n test -e "$DEST"; then
  echo "STOP: Immutable release exists; refusing overwrite" >&2
  exit 2
fi

echo "=== Install root-owned, immutable approved runtime ==="
sudo -n install -d -m 0755 -o root -g root "$RELEASES"
sudo -n install -d -m 0755 -o root -g root "$DEST"
# Archive exactly tracked source files, no .env or untracked/private files.
git -C "$ROOT" archive --format=tar "$REV" \
  server tools/run-odoo-mirror-incremental-cycle.sh |
  sudo -n tar -xf - -C "$DEST" --no-same-owner
sudo -n chown -R root:root "$DEST"
sudo -n chmod -R go-w "$DEST"
sudo -n chmod -R a+rX "$DEST"

echo "=== Register isolated-staging service and five-minute timer ==="
sudo -n tee "$SERVICE" >/dev/null <<UNIT
[Unit]
Description=Panadan Odoo create_date/write_date incremental mirror (isolated staging only)
Documentation=https://github.com/$EXPECTED_REPO
After=network-online.target docker.service
Wants=network-online.target
ConditionPathExists=/home/panafor/panadan/.env.db
ConditionPathExists=/home/panafor/.config/panadan-mirror-staging/writer.dsn

[Service]
Type=oneshot
User=root
Group=root
UMask=0077
Environment=HOME=/home/panafor
ExecStart=/usr/bin/bash $DEST/tools/run-odoo-mirror-incremental-cycle.sh cycle
TimeoutStartSec=15min
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
UNIT
sudo -n chmod 644 "$SERVICE"

sudo -n tee "$TIMER" >/dev/null <<'TIMER_UNIT'
[Unit]
Description=Panadan Odoo timestamp-only incremental mirror every five minutes

[Timer]
OnCalendar=*:0/5
AccuracySec=30s
Persistent=true
Unit=panadan-mirror-incremental.service

[Install]
WantedBy=timers.target
TIMER_UNIT
sudo -n chmod 644 "$TIMER"

sudo -n systemctl daemon-reload
sudo -n systemd-analyze verify "$SERVICE" "$TIMER" || {
  echo "STOP: systemd unit failed validation; do not enable timer" >&2
  exit 2
}

# This action explicitly authorizes activation in isolated STAGING. Neither
# the live web service nor production data source is restarted.
sudo -n systemctl enable --now panadan-mirror-incremental.timer

echo "PASS: Five-minute isolated-staging incremental timer enabled"
echo "PASS: Runtime pinned to approved git revision $REV"
echo "Inspect: systemctl status panadan-mirror-incremental.timer"
echo "Logs: journalctl -u panadan-mirror-incremental.service -n 50 --no-pager"
echo "Pause: sudo systemctl disable --now panadan-mirror-incremental.timer"
