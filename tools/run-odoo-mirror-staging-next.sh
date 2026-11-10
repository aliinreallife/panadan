#!/usr/bin/env bash
# Manual, resumable, finite Odoo -> isolated staging continuation.
# Source is READ ONLY in the existing VPN namespace. Customer JSON travels
# directly through an anonymous stdout/stdin pipe, never to disk or logs.
# Target is the existing restricted localhost staging writer, NOT production.
set -euo pipefail
set +x
umask 077

if [[ "${1:-}" != "next-batch" ]]; then
  echo "Usage: $0 next-batch --ack-source-contract --ack-retention --ack-copy --ack-sensitive-data" >&2
  exit 2
fi
shift
if (( $# != 4 )); then
  echo "Exactly four staging approvals required" >&2
  exit 2
fi
for approval in --ack-source-contract --ack-retention --ack-copy --ack-sensitive-data; do
  n=0
  for arg in "$@"; do [[ "$arg" != "$approval" ]] || n=$((n+1)); done
  if (( n != 1 )); then
    echo "Missing or duplicate staging approval" >&2
    exit 2
  fi
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONF="$HOME/.config/panadan-mirror-staging/writer.dsn"
SOURCE_ENV="$HOME/panadan/.env.db"
DB="panadan-mirror-staging-pg18"
SOURCE="odoo_calls_full_v1"
PAGES=3
# A supervisor may request 1 or 2 pages to finish an interrupted
# 300-row recovery interval. Never permit more than the reviewed 3.
if [[ -n "${PANADAN_MIRROR_PAGE_LIMIT:-}" ]]; then
  case "$PANADAN_MIRROR_PAGE_LIMIT" in
    1|2|3) PAGES="$PANADAN_MIRROR_PAGE_LIMIT" ;;
    *) echo "Only 1, 2 or 3 staging pages are permitted" >&2; exit 2 ;;
  esac
fi
PAGE_SIZE=100
# Pass 1 remains the default for legacy scripts. Pass 2 requires a separate
# explicit opt-in and may start with a zero cursor (the completed first pass).
PASS_TO_RUN=1
if [[ -n "${PANADAN_MIRROR_EXPECTED_PASS:-}" ]]; then
  case "$PANADAN_MIRROR_EXPECTED_PASS" in
    2) PASS_TO_RUN=2 ;;
    *) echo "Only reconciliation pass 2 is a valid explicit override" >&2; exit 2 ;;
  esac
fi
NEXT_PASS=$((PASS_TO_RUN + 1))
ENABLED=0

command -v flock >/dev/null
install -d -m 700 "$HOME/.config/panadan-mirror-staging"
exec 9>"$HOME/.config/panadan-mirror-staging/continuation.lock"
flock -n 9 || { echo "Another staging continuation is running" >&2; exit 2; }
[[ "$(stat -c '%a' "$CONF")" == 600 && -s "$SOURCE_ENV" ]] || {
  echo "Private staging writer and source configuration required" >&2
  exit 2
}
sudo -v

dbquery() {
  sudo -n docker exec "$DB" psql -X -v ON_ERROR_STOP=1 \
    -U panadan_stage_owner -d panadan_ci -Atqc "$1"
}
disable() {
  local got
  got="$(dbquery "UPDATE panadan_ingest.sources SET enabled=FALSE
    WHERE source_key='$SOURCE' RETURNING enabled::text;")"
  [[ "$got" == "false" ]]
}
on_exit() {
  local rc=$?
  trap - EXIT
  if (( ENABLED )); then
    if ! disable; then
      echo "URGENT: Could not disable staging source; disable it manually" >&2
      rc=1
    else
      echo "PASS: Staging source disabled after interruption" >&2
    fi
  fi
  exit "$rc"
}
trap on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

[[ "$(sudo -n docker port "$DB" 5432/tcp)" == "127.0.0.1:55432" ]] || {
  echo "Unexpected staging port" >&2; exit 2;
}
[[ "$(sudo -n docker inspect panadan-vpn-1 --format '{{.State.Health.Status}}')" == healthy ]] || {
  echo "Source VPN is not healthy" >&2; exit 2;
}

IMAGE="$(sudo -n docker inspect panadan-web-1 --format '{{.Image}}')"
sudo -n docker image inspect "$IMAGE" >/dev/null

# Query only control metadata; never read or print customer payloads here.
read_state() {
  local data
  data="$(dbquery "SELECT current_database() || '|' ||
    current_setting('server_version_num') || '|' ||
    COALESCE((SELECT enabled::text FROM panadan_ingest.sources
              WHERE source_key='$SOURCE'), 'missing') || '|' ||
    (SELECT count(*) FROM panadan_ingest.source_records
     WHERE source_key='$SOURCE')::text || '|' ||
    (SELECT count(*) FROM panadan_ingest.raw_revisions
     WHERE source_key='$SOURCE')::text || '|' ||
    COALESCE((SELECT cursor->>'pass'
              FROM panadan_ingest.sync_checkpoints
              WHERE source_key='$SOURCE' AND stream='view_reconciliation_v1'),
             'missing') || '|' ||
    COALESCE((SELECT cursor->>'last_id'
              FROM panadan_ingest.sync_checkpoints
              WHERE source_key='$SOURCE' AND stream='view_reconciliation_v1'),
             'missing') || '|' ||
    COALESCE((SELECT MAX(external_id::bigint)::text
              FROM panadan_ingest.source_records WHERE source_key='$SOURCE'),
             'missing');")"
  IFS='|' read -r database version enabled records revisions pass cursor max_id <<< "$data"
  [[ "$database" == panadan_ci && "$version" == 180006 &&
     "$enabled" == false && "$records" =~ ^[0-9]+$ &&
     "$revisions" =~ ^[0-9]+$ && "$pass" =~ ^[0-9]+$ &&
     "$cursor" =~ ^[0-9]+$ && "$max_id" =~ ^[0-9]+$ &&
     "$records" -ge 275 && "$revisions" -ge "$records" &&
     ( "$pass" != 1 || "$cursor" == "$max_id" ) &&
     ( "$pass" != 2 || "$cursor" -le "$max_id" ) ]] || {
    echo "Unexpected staging checkpoint or source state" >&2
    exit 2
  }
}

# The supervised pilot sets a fixed 6 GiB floor. Check it BEFORE
# every source activation, not only between three-page chunks.
check_disk_floor() {
  [[ -n "${PANADAN_MIRROR_MIN_AVAILABLE_KIB:-}" ]] || return 0
  [[ "$PANADAN_MIRROR_MIN_AVAILABLE_KIB" == 6291456 ]] || {
    echo "Unsupported staging disk floor" >&2
    exit 2
  }
  local available
  available="$(df -Pk /var/lib/panadan-mirror-staging | awk 'NR==2 {print $4}')"
  [[ "$available" =~ ^[0-9]+$ ]] || {
    echo "Could not check staging disk space" >&2
    exit 2
  }
  if (( available < PANADAN_MIRROR_MIN_AVAILABLE_KIB )); then
    echo "STOP: Staging disk below supervised 6 GiB floor" >&2
    exit 2
  fi
}

read_state
if (( PASS_TO_RUN == 1 )); then
  [[ "$pass" == 1 && "$cursor" -gt 0 ]] || {
    echo "Expected an active pass-1 checkpoint; refusing new reconciliation pass" >&2
    exit 2
  }
else
  [[ "$pass" == 2 && "$cursor" -ge 0 ]] || {
    echo "Expected a pass-2 checkpoint; refusing any other reconciliation pass" >&2
    exit 2
  }
fi
echo "PASS: Existing pass-$PASS_TO_RUN checkpoint detected; staging source disabled"
echo "=== Resume for up to $PAGES pages x $PAGE_SIZE source rows ==="

for ((i=1; i<=PAGES; i++)); do
  check_disk_floor
  read_state
  if [[ "$pass" == "$NEXT_PASS" && "$cursor" == 0 ]]; then
    echo "PASS: Source reconciliation pass $PASS_TO_RUN completed"
    break
  fi
  [[ "$pass" == "$PASS_TO_RUN" &&
     ( "$PASS_TO_RUN" == 2 || "$cursor" -gt 0 ) ]] || {
    echo "Unexpected reconciliation checkpoint" >&2; exit 2;
  }
  before="$cursor"
  # Setting ENABLED before owner UPDATE ensures the EXIT trap always attempts
  # to disable even if output checks or the subsequent pipeline fail.
  ENABLED=1
  changed="$(dbquery "UPDATE panadan_ingest.sources SET enabled=TRUE
     WHERE source_key='$SOURCE' AND enabled=FALSE RETURNING enabled::text;")"
  [[ "$changed" == true ]] || {
    echo "Could not exclusively enable staging source" >&2; exit 2;
  }

  echo "=== Page $i/$PAGES ==="
  sudo -n docker run --rm \
    --name panadan-mirror-vpn-continue-export \
    --pull=never --log-driver=none \
    --network container:panadan-vpn-1 \
    --read-only --cap-drop=ALL --security-opt no-new-privileges \
    --user "$(id -u):$(id -g)" --memory=512m --pids-limit=128 \
    --env-file "$SOURCE_ENV" \
    -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/opt/panadan \
    -v "$ROOT:/opt/panadan:ro" -w /opt/panadan \
    --entrypoint python "$IMAGE" \
    -m server.odoo_mirror_transfer export \
    --batch-size "$PAGE_SIZE" --after-id "$before" \
  | sudo -n docker run --rm -i \
    --name panadan-mirror-host-continue-import \
    --pull=never --log-driver=none --network host \
    --read-only --cap-drop=ALL --security-opt no-new-privileges \
    --user "$(id -u):$(id -g)" --memory=512m --pids-limit=128 \
    -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/opt/panadan \
    -e PANADAN_FULL_MIRROR_TARGET_MODE=isolated-staging \
    -e PANADAN_FULL_MIRROR_STAGING_ISOLATED=YES \
    -e PANADAN_FULL_MIRROR_STAGING_WRITER_DSN_FILE=/run/secrets/writer.dsn \
    -v "$ROOT:/opt/panadan:ro" \
    -v "$CONF:/run/secrets/writer.dsn:ro" \
    -w /opt/panadan --entrypoint python "$IMAGE" \
    -m server.odoo_mirror_transfer import --batch-size "$PAGE_SIZE" \
    --ack-source-contract --ack-retention --ack-copy --ack-sensitive-data

  disable || { echo "Could not disable staging source" >&2; exit 2; }
  ENABLED=0
  read_state
  if [[ "$pass" == "$NEXT_PASS" && "$cursor" == 0 ]]; then
    echo "PASS: Completed reconciliation pass $PASS_TO_RUN"
    break
  fi
  [[ "$pass" == "$PASS_TO_RUN" && "$cursor" -gt "$before" ]] || {
    echo "Checkpoint failed to advance" >&2; exit 2;
  }
done

read_state
echo "PASS: Staging source remains disabled"
echo "STAGING CONTINUATION OK: current_records=$records revisions=$revisions pass=$pass"
