#!/usr/bin/env bash
# One-shot, READ ONLY all-view Odoo-to-isolated-staging parity census.
# No stage/source writes, file spooling, raw data logs or production cutover.
set -euo pipefail
set +x
umask 077

[[ "${1:-}" == audit && $# -eq 1 ]] || {
  echo "Usage: $0 audit" >&2
  exit 2
}

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="$HOME/.config/panadan-mirror-staging"
SOURCE_ENV="$HOME/panadan/.env.db"
STAGE="panadan-mirror-staging-pg18"
RESTORE="panadan-mirror-data-restore-drill-pg18"
KEY="/var/lib/panadan-mirror-staging/backup-identity.txt"

sudo -v
command -v flock >/dev/null
install -d -m 700 "$CONFIG"
# Take exactly the same lock as the Odoo staging importer; the audit must
# NOT overlap with source activation or any reviewed importer.
exec 9>"$CONFIG/continuation.lock"
flock -n 9 || {
  echo "STOP: Another staging continuation/scan holds the source lock" >&2
  exit 2
}

[[ "$(sudo -n docker port "$STAGE" 5432/tcp)" == 127.0.0.1:55432 ]] || {
  echo "STOP: Staging is not the isolated loopback endpoint" >&2
  exit 2
}
[[ "$(sudo -n docker inspect "$RESTORE" --format '{{.HostConfig.NetworkMode}}')" == none ]] || {
  echo "STOP: Restore container isolation changed" >&2
  exit 2
}
[[ "$(sudo -n docker inspect panadan-vpn-1 --format '{{.State.Health.Status}}')" == healthy ]] || {
  echo "STOP: Existing read-only Odoo VPN unhealthy" >&2
  exit 2
}
[[ -f "$CONFIG/writer.dsn" && ! -L "$CONFIG/writer.dsn" &&
   "$(stat -c %a "$CONFIG/writer.dsn")" == 600 &&
   -s "$SOURCE_ENV" ]] || {
  echo "STOP: Private staging-only and read-only source config required" >&2
  exit 2
}
[[ "$(sudo -n stat -c %a "$KEY")" == 600 ]] || {
  echo "STOP: Private backup recovery key changed" >&2
  exit 2
}
stage_state="$(sudo -n docker exec "$STAGE" psql -X -Atq -v ON_ERROR_STOP=1 \
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
[[ "$stage_state" == 95912\|false\|2\|0 ]] || {
  echo "STOP: Audit requires verified 95,912-row completed pass-1 baseline" >&2
  exit 2
}
IMAGE="$(sudo -n docker inspect panadan-web-1 --format '{{.Image}}')"
sudo -n docker image inspect "$IMAGE" >/dev/null

echo "=== Whole-view read-only parity scan; no source/staging writes ==="
echo "=== Comparing all 37 source fields with stored SHA-256 digests ==="

# Important: no tee of this pipe, no -t pseudo-terminal, no container logging.
# Docker source stdout contains personal data and goes ONLY to the verifier.
sudo -n docker run --rm \
  --name panadan-parity-census-source \
  --pull=never --log-driver=none \
  --network container:panadan-vpn-1 \
  --read-only --cap-drop=ALL --security-opt no-new-privileges \
  --user "$(id -u):$(id -g)" --memory=512m --pids-limit=128 \
  --env-file "$SOURCE_ENV" \
  -e PYTHONPATH=/opt/panadan -e PYTHONDONTWRITEBYTECODE=1 \
  -e PANADAN_MIRROR_PARITY_SOURCE_PIPE=YES \
  -v "$ROOT:/opt/panadan:ro" -w /opt/panadan \
  --entrypoint python "$IMAGE" \
  -m server.odoo_mirror_parity_stream source \
| sudo -n docker run --rm -i \
  --name panadan-parity-census-staging \
  --pull=never --log-driver=none --network host \
  --read-only --cap-drop=ALL --security-opt no-new-privileges \
  --user "$(id -u):$(id -g)" --memory=512m --pids-limit=128 \
  -e PYTHONPATH=/opt/panadan -e PYTHONDONTWRITEBYTECODE=1 \
  -e PANADAN_FULL_MIRROR_TARGET_MODE=isolated-staging \
  -e PANADAN_FULL_MIRROR_STAGING_ISOLATED=YES \
  -e PANADAN_FULL_MIRROR_STAGING_WRITER_DSN_FILE=/run/secrets/writer.dsn \
  -v "$ROOT:/opt/panadan:ro" -v "$CONFIG/writer.dsn:/run/secrets/writer.dsn:ro" \
  -w /opt/panadan --entrypoint python "$IMAGE" \
  -m server.odoo_mirror_parity_stream staging

echo "PASS: Whole-view comparison completed; no source/staging writes"
