#!/usr/bin/env bash
# One bounded incremental Odoo -> isolated PG18 staging cycle.
# Selects ONLY by create_date/write_date; id is not a new-call watermark.
# No full-view reconciliation, backups, deletions, production read-path changes,
# or stored plaintext payloads. Safe for scheduled invocation after deployment.
set -euo pipefail
set +x
umask 077

[[ "${1:-}" == cycle && $# -eq 1 ]] || {
  echo "Usage: $0 cycle" >&2
  exit 2
}

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOME_DIR=/home/panafor
CONF="$HOME_DIR/.config/panadan-mirror-staging"
SOURCE_ENV="$HOME_DIR/panadan/.env.db"
STAGE=panadan-mirror-staging-pg18
RESTORE=panadan-mirror-data-restore-drill-pg18
SOURCE=odoo_calls_full_v1
STREAM=created_or_modified_v1
MAX_PAGES=10
MIN_AVAILABLE_KIB=6291456
RUNNING_CHILD=0
SOURCE_ENABLED=0

command -v flock >/dev/null
command -v python3 >/dev/null
command -v df >/dev/null
install -d -m 700 "$CONF"
exec 9>"$CONF/continuation.lock"
flock -n 9 || { echo "SKIP: Another Odoo mirror transfer holds the lock"; exit 0; }
sudo -n -v || {
  echo "FAIL: Non-interactive sudo unavailable; install via approved system service" >&2
  exit 2
}

stage_sql() {
  sudo -n docker exec "$STAGE" psql -X -Atq -v ON_ERROR_STOP=1 \
    -U panadan_stage_owner -d panadan_ci -c "$1"
}

disable_source() {
  stage_sql "UPDATE panadan_ingest.sources SET enabled=FALSE
    WHERE source_key='$SOURCE' AND enabled=TRUE;" >/dev/null
}

cleanup() {
  local rc=$?
  trap - EXIT
  if (( SOURCE_ENABLED || RUNNING_CHILD )); then
    if ! disable_source; then
      echo "URGENT: Staging source could not be disabled" >&2
      rc=2
    fi
  fi
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

check_disk() {
  local kib
  kib="$(df -Pk /var/lib/panadan-mirror-staging | awk 'NR==2 {print $4}')"
  [[ "$kib" =~ ^[0-9]+$ && "$kib" -ge "$MIN_AVAILABLE_KIB" ]] || {
    echo "STOP: Incremental staging disk below 6 GiB floor" >&2
    return 2
  }
}

[[ "$(sudo -n docker port "$STAGE" 5432/tcp)" == 127.0.0.1:55432 ]] || {
  echo "STOP: Staging port is not isolated loopback" >&2
  exit 2
}
[[ "$(sudo -n docker inspect "$RESTORE" --format '{{.HostConfig.NetworkMode}}')" == none ]] || {
  echo "STOP: Existing verified recovery database is not isolated" >&2
  exit 2
}
[[ "$(sudo -n docker inspect panadan-vpn-1 --format '{{.State.Health.Status}}')" == healthy ]] || {
  echo "STOP: Odoo read-only VPN is unhealthy" >&2
  exit 2
}
[[ -f "$CONF/writer.dsn" && ! -L "$CONF/writer.dsn" &&
   "$(stat -c %a "$CONF/writer.dsn")" == 600 && -s "$SOURCE_ENV" ]] || {
  echo "STOP: Staging writer/source secrets must be private" >&2
  exit 2
}
IMAGE="$(sudo -n docker inspect panadan-web-1 --format '{{.Image}}')"
sudo -n docker image inspect "$IMAGE" >/dev/null
USER_ID="$(id -u panafor)"
GROUP_ID="$(id -g panafor)"
check_disk

read_state() {
  local state
  state="$(stage_sql "SELECT current_database() || '|' ||
    current_setting('server_version_num') || '|' ||
    (SELECT count(*) FROM panadan_ingest.source_records
      WHERE source_key='$SOURCE')::text || '|' ||
    COALESCE((SELECT enabled::text FROM panadan_ingest.sources
      WHERE source_key='$SOURCE'), 'missing') || '|' ||
    COALESCE((SELECT cursor->>'pass' FROM panadan_ingest.sync_checkpoints
      WHERE source_key='$SOURCE' AND stream='view_reconciliation_v1'), 'missing') || '|' ||
    COALESCE((SELECT cursor->>'last_id' FROM panadan_ingest.sync_checkpoints
      WHERE source_key='$SOURCE' AND stream='view_reconciliation_v1'), 'missing');")"
  IFS='|' read -r dbname pg_version records enabled snapshot_pass snapshot_id <<< "$state"
  [[ "$dbname" == panadan_ci && "$pg_version" == 180006 &&
     "$records" =~ ^[0-9]+$ && "$records" -ge 96022 &&
     "$snapshot_pass" =~ ^[0-9]+$ && "$snapshot_pass" -ge 3 &&
     "$snapshot_id" == 0 &&
     ( "$enabled" == true || "$enabled" == false ) ]] || {
    echo "STOP: Completed 37-field mirror baseline/staging identity missing" >&2
    return 2
  }
}
read_state

# The continuation.lock excludes all reviewed page writers. If the prior
# SSH process died between activation and cleanup, reclaim this stale flag
# before touching the source. An active writer cannot hold the lock here.
if [[ "$enabled" == true ]]; then
  echo "RECOVER: Disabling abandoned staging source under exclusive lock"
  disable_source
fi
read_state
[[ "$enabled" == false ]] || exit 2

get_cursor() {
  stage_sql "SELECT COALESCE((
      SELECT cursor::text FROM panadan_ingest.sync_checkpoints
      WHERE source_key='$SOURCE' AND stream='$STREAM'
    ), 'null');"
}
has_window() {
  stage_sql "SELECT COALESCE((
      SELECT (cursor ? 'window')::text
      FROM panadan_ingest.sync_checkpoints
      WHERE source_key='$SOURCE' AND stream='$STREAM'
    ), 'false');"
}
previous="$(get_cursor)"
[[ -n "$previous" ]] || {
  echo "STOP: Could not inspect incremental cursor" >&2
  exit 2
}
# Validate that the cursor is JSON and is never the legacy ID-backfill cursor.
python3 -c 'import json,sys; c=json.loads(sys.argv[1]); assert c is None or (type(c) is dict and c.get("kind") == "write_create_v1")' "$previous" || {
  echo "STOP: Unexpected incremental checkpoint" >&2
  exit 2
}

echo "=== Bounded Odoo create_date/write_date incremental cycle ==="
echo "No full-view scan; at most $MAX_PAGES x 80 source call groups"

for (( i=1; i<=MAX_PAGES; i++ )); do
  check_disk
  read_state
  [[ "$enabled" == false ]] || {
    echo "STOP: Source enabled unexpectedly outside transfer" >&2
    exit 2
  }
  previous="$(get_cursor)"

  # Enable only for the one atomic import. The source export connection is
  # always read-only and its entire 37-field payload goes through a pipe.
  RUNNING_CHILD=1
  SOURCE_ENABLED=1
  changed="$(stage_sql "UPDATE panadan_ingest.sources SET enabled=TRUE
    WHERE source_key='$SOURCE' AND enabled=FALSE RETURNING enabled::text;")"
  [[ "$changed" == true ]] || {
    echo "STOP: Could not acquire staging source activation" >&2
    exit 2
  }

  sudo -n docker run --rm \
    --name panadan-incremental-source \
    --pull=never --log-driver=none \
    --network container:panadan-vpn-1 \
    --read-only --cap-drop=ALL --security-opt no-new-privileges \
    --user "$USER_ID:$GROUP_ID" --memory=512m --pids-limit=128 \
    --env-file "$SOURCE_ENV" \
    -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/opt/panadan \
    -e PANADAN_MIRROR_INCREMENTAL_PIPE=YES \
    -v "$ROOT:/opt/panadan:ro" -w /opt/panadan \
    --entrypoint python "$IMAGE" \
    -m server.odoo_mirror_incremental export --cursor-json "$previous" \
  | sudo -n docker run --rm -i \
    --name panadan-incremental-stage \
    --pull=never --log-driver=none --network host \
    --read-only --cap-drop=ALL --security-opt no-new-privileges \
    --user "$USER_ID:$GROUP_ID" --memory=512m --pids-limit=128 \
    -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/opt/panadan \
    -e PANADAN_FULL_MIRROR_TARGET_MODE=isolated-staging \
    -e PANADAN_FULL_MIRROR_STAGING_ISOLATED=YES \
    -e PANADAN_FULL_MIRROR_STAGING_WRITER_DSN_FILE=/run/secrets/writer.dsn \
    -v "$ROOT:/opt/panadan:ro" \
    -v "$CONF/writer.dsn:/run/secrets/writer.dsn:ro" \
    -w /opt/panadan --entrypoint python "$IMAGE" \
    -m server.odoo_mirror_incremental import

  disable_source
  SOURCE_ENABLED=0
  RUNNING_CHILD=0
  read_state
  [[ "$enabled" == false ]] || {
    echo "STOP: Source did not return to disabled" >&2
    exit 2
  }
  current="$(get_cursor)"
  if [[ "$current" == "$previous" ]]; then
    echo "PASS: No newer source timestamp window available"
    break
  fi
  if [[ "$(has_window)" != true ]]; then
    echo "PASS: Incremental timestamp window fully committed"
    break
  fi
done

echo "PASS: Incremental cycle complete; staging ingestion disabled"
