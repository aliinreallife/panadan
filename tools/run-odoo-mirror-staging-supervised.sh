#!/usr/bin/env bash
# Finite, operator-invoked Odoo -> isolated Panadan staging supervisor.
# No source writes, no plaintext export/backup files, no background service.
# Each child invocation is the existing CI-reviewed 3 x 100 page pipe runner.
set -euo pipefail
set +x
umask 077

if [[ "${1:-}" != supervised || $# != 5 ]]; then
  echo "Usage: $0 supervised --ack-source-contract --ack-retention --ack-copy --ack-sensitive-data" >&2
  exit 2
fi
shift
for ack in --ack-source-contract --ack-retention --ack-copy --ack-sensitive-data; do
  count=0
  for arg in "$@"; do [[ "$arg" != "$ack" ]] || count=$((count+1)); done
  if (( count != 1 )); then
    echo "Exactly four distinct source/retention/copy/sensitive-data approvals required" >&2
    exit 2
  fi
done

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DB=panadan-mirror-staging-pg18
RESTORE=panadan-mirror-data-restore-drill-pg18
SOURCE=odoo_calls_full_v1
STREAM=view_reconciliation_v1
BASE=/var/lib/panadan-mirror-staging
BACKUPS="$BASE/backups"
KEY="$BASE/backup-identity.txt"
CONFIG="$HOME/.config/panadan-mirror-staging"
# First supervised pilot is intentionally short and interactive (not a daemon).
CHUNKS=3
ROWS_PER_CHUNK=300
MIN_AVAILABLE_KIB=$((6 * 1024 * 1024))
START_MIN=825
COMMITTED_MIN=24
lock_file="$CONFIG/supervised.lock"

command -v flock >/dev/null
command -v age >/dev/null
command -v age-keygen >/dev/null
install -d -m 700 "$CONFIG"
exec 8>"$lock_file"
flock -n 8 || { echo "Another supervised staging run is active" >&2; exit 2; }
sudo -v
[[ "$(sudo -n docker port "$DB" 5432/tcp)" == 127.0.0.1:55432 ]] || {
  echo "FAIL: Staging port isolation changed" >&2
  exit 2
}
[[ "$(sudo -n docker inspect "$RESTORE" --format '{{.HostConfig.NetworkMode}}')" == none ]] || {
  echo "FAIL: Recovery drill network isolation changed" >&2
  exit 2
}
[[ "$(sudo -n docker inspect panadan-vpn-1 --format '{{.State.Health.Status}}')" == healthy ]] || {
  echo "FAIL: Source VPN unhealthy" >&2
  exit 2
}
[[ -f "$CONFIG/writer.dsn" && ! -L "$CONFIG/writer.dsn" &&
   "$(stat -c %a "$CONFIG/writer.dsn")" == 600 ]] || {
  echo "FAIL: Private staging writer config required" >&2
  exit 2
}
[[ -s "$HOME/panadan/.env.db" ]] || {
  echo "FAIL: Existing private source env required" >&2
  exit 2
}
sudo -n test -f "$KEY"
sudo -n test ! -L "$KEY"
[[ "$(sudo -n stat -c %a "$KEY")" == 600 ]] || {
  echo "FAIL: Encryption identity must be private (0600)" >&2
  exit 2
}
sudo -n install -d -m 700 "$BACKUPS"

# If the operator interrupts between pages, the child's EXIT trap disables
# ingestion. This outer trap is a staging-only second line of defense.
emergency_disable() {
  local rc=$?
  trap - EXIT
  if (( rc != 0 )); then
    echo "STOP: Supervisor interrupted or failed; checking staging source" >&2
    if ! sudo -n docker exec "$DB" psql -X -Atq -v ON_ERROR_STOP=1 \
      -U panadan_stage_owner -d panadan_ci -c \
      "UPDATE panadan_ingest.sources SET enabled=FALSE
       WHERE source_key='$SOURCE' AND enabled=TRUE;" >/dev/null; then
      echo "URGENT: Could not verify/disable staging ingestion" >&2
    fi
  fi
  exit "$rc"
}
trap emergency_disable EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

stage_sql() {
  sudo -n docker exec "$DB" psql -X -Atq -v ON_ERROR_STOP=1 \
    -U panadan_stage_owner -d panadan_ci -c "$1"
}

free_disk_check() {
  local available
  available="$(df -Pk "$BASE" | awk 'NR==2 {print $4}')"
  [[ "$available" =~ ^[0-9]+$ ]] || {
    echo "FAIL: Cannot determine staging disk space" >&2
    exit 2
  }
  if (( available < MIN_AVAILABLE_KIB )); then
    echo "STOP: Free disk below the 6 GiB staging safety floor" >&2
    exit 2
  fi
  echo "PASS: Disk safety floor met ($(( available / 1024 )) MiB available)"
}

read_state() {
  local state
  state="$(stage_sql "SELECT current_database() || '|' ||
    current_setting('server_version_num') || '|' ||
    COALESCE((SELECT enabled::text FROM panadan_ingest.sources
              WHERE source_key='$SOURCE'), 'missing') || '|' ||
    (SELECT count(*) FROM panadan_ingest.source_records
     WHERE source_key='$SOURCE')::text || '|' ||
    (SELECT count(*) FROM panadan_ingest.raw_revisions
     WHERE source_key='$SOURCE')::text || '|' ||
    (SELECT count(*) FROM panadan_ingest.sync_runs
     WHERE source_key='$SOURCE' AND stream='$STREAM')::text || '|' ||
    COALESCE((SELECT cursor->>'pass' FROM panadan_ingest.sync_checkpoints
              WHERE source_key='$SOURCE' AND stream='$STREAM'), 'missing') || '|' ||
    COALESCE((SELECT cursor->>'last_id' FROM panadan_ingest.sync_checkpoints
              WHERE source_key='$SOURCE' AND stream='$STREAM'), 'missing') || '|' ||
    COALESCE((SELECT max(external_id::bigint)::text
              FROM panadan_ingest.source_records WHERE source_key='$SOURCE'), 'missing');")"
  IFS='|' read -r database pg_version enabled records revisions pages pass cursor max_id <<< "$state"
  [[ "$database" == panadan_ci && "$pg_version" == 180006 &&
     "$enabled" == false && "$records" =~ ^[0-9]+$ &&
     "$revisions" =~ ^[0-9]+$ && "$pages" =~ ^[0-9]+$ &&
     "$pass" == 1 && "$cursor" =~ ^[0-9]+$ &&
     "$max_id" =~ ^[0-9]+$ && "$cursor" == "$max_id" &&
     "$records" -ge "$START_MIN" && "$revisions" == "$records" &&
     "$pages" -ge "$COMMITTED_MIN" ]] || {
    echo "FAIL: Unexpected staging state or pass-1 cursor" >&2
    exit 2
  }
}

integrity_check() {
  local result
  result="$(stage_sql "WITH current AS (
    SELECT s.external_id, s.revision_no, s.current_digest, s.is_deleted,
           r.digest, r.operation, r.payload
    FROM panadan_ingest.source_records s
    JOIN panadan_ingest.raw_revisions r
      ON r.source_key=s.source_key
     AND r.external_id=s.external_id AND r.revision_no=s.revision_no
    WHERE s.source_key='$SOURCE'
  )
  SELECT CASE WHEN
    (SELECT count(*) FROM current)=$records
    AND (SELECT count(*) FROM panadan_ingest.raw_revisions
         WHERE source_key='$SOURCE')=$revisions
    AND (SELECT COALESCE(sum(examined),0) FROM panadan_ingest.sync_runs
         WHERE source_key='$SOURCE' AND stream='$STREAM')=$records
    AND (SELECT bool_and(
      revision_no=1 AND is_deleted=FALSE AND operation='upsert'
      AND current_digest=digest AND current_digest ~ '^[0-9a-f]{64}$'
      AND payload->>'source_schema'='odoo_view_37_v1'
      AND jsonb_typeof(payload->'source_rows')='array'
    ) FROM current) IS TRUE
    AND NOT EXISTS (
      SELECT 1 FROM current c
      CROSS JOIN LATERAL jsonb_array_elements(c.payload->'source_rows') v(row)
      WHERE jsonb_typeof(v.row)<>'object'
         OR (SELECT count(*) FROM jsonb_object_keys(v.row))<>37
         OR v.row->>'id'<>c.external_id
    )
    AND (SELECT COALESCE(sum(jsonb_array_length(payload->'source_rows')),0)
         FROM current) >= $records
    AND (SELECT enabled=FALSE FROM panadan_ingest.sources
         WHERE source_key='$SOURCE') IS TRUE
  THEN 'PASS' ELSE 'FAIL' END;")"
  [[ "$result" == PASS ]] || {
    echo "FAIL: Staging integrity check" >&2
    exit 2
  }
  echo "PASS: $records records / $revisions revisions / $pages pages; 37 fields"
}

# A backup is mandatory for the exact current checkpoint before any writes.
# The backup may have been created by a prior supervised run or manually.
find_prior_backup() {
  local prior
  prior="$(sudo -n find "$BACKUPS" -maxdepth 1 -type f \
    -name "odoo-mirror-$records-*.dump.age" \
    -printf '%T@ %p\n' | sort -nr | sed -n '1s/^[^ ]* //p')"
  [[ -n "$prior" ]] && sudo -n test -s "$prior" && \
    [[ "$(sudo -n stat -c %a "$prior")" == 600 ]] || {
    echo "FAIL: No private encrypted backup matching current count" >&2
    exit 2
  }
  sudo -n age -d -i "$KEY" "$prior" |
    sudo -n docker exec -i "$DB" pg_restore -l >/dev/null
  echo "PASS: Encrypted recovery archive present for $records records"
}

create_backup() {
  local recipient output
  free_disk_check
  recipient="$(sudo -n age-keygen -y "$KEY")"
  output="$BACKUPS/odoo-mirror-$records-$(date -u +%Y%m%dT%H%M%SZ).dump.age"
  sudo -n test ! -e "$output"
  if sudo -n docker exec "$DB" \
    pg_dump -U panadan_stage_owner -d panadan_ci -Fc |
    sudo -n age -r "$recipient" -o "$output"; then
    sudo -n chmod 600 "$output"
  else
    sudo -n rm -f -- "$output"
    echo "FAIL: Encrypted recovery checkpoint creation" >&2
    exit 2
  fi
  sudo -n age -d -i "$KEY" "$output" |
    sudo -n docker exec -i "$DB" pg_restore -l >/dev/null
  echo "PASS: New encrypted backup validated for $records records"
}

echo "=== Verify isolated staging starting state ==="
free_disk_check
read_state
[[ "$records" == 825 && "$pages" == 24 ]] || {
  echo "FAIL: First supervised pilot requires the verified 825-row / 24-page baseline" >&2
  exit 2
}
integrity_check
find_prior_backup
# Confirm independent recovery of the known baseline, not just an archive TOC.
restored="$(sudo -n docker exec "$RESTORE" \
  psql -X -Atq -v ON_ERROR_STOP=1 \
  -U panadan_stage_owner -d panadan_restore_825 -c \
  "SELECT (SELECT count(*) FROM panadan_ingest.source_records
           WHERE source_key='$SOURCE')::text || '|' ||
          (SELECT count(*) FROM panadan_ingest.raw_revisions
           WHERE source_key='$SOURCE')::text;")"
[[ "$restored" == 825\|825 ]] || {
  echo "FAIL: Independent 825-record recovery point unavailable" >&2
  exit 2
}
echo "PASS: Independent restore checkpoint verified"

for ((chunk=1; chunk<=CHUNKS; chunk++)); do
  free_disk_check
  read_state
  before_records="$records"
  before_pages="$pages"
  echo "=== Supervised chunk $chunk/$CHUNKS (up to $ROWS_PER_CHUNK source rows) ==="
  bash "$ROOT/tools/run-odoo-mirror-staging-next.sh" \
    next-batch --ack-source-contract --ack-retention \
    --ack-copy --ack-sensitive-data
  read_state
  (( records > before_records && records <= before_records + ROWS_PER_CHUNK )) || {
    echo "FAIL: Unexpected staged record increment" >&2
    exit 2
  }
  (( pages > before_pages && pages <= before_pages + 3 )) || {
    echo "FAIL: Unexpected committed page increment" >&2
    exit 2
  }
  integrity_check
  create_backup
  echo "PASS: Chunk $chunk committed, checked and encrypted"
done

read_state
echo "SUPERVISED STAGING PILOT COMPLETE: records=$records revisions=$revisions pages=$pages"
echo "Staging source disabled; maximum $((CHUNKS * ROWS_PER_CHUNK)) new source rows"
