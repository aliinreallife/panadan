#!/usr/bin/env bash
# One operator-initiated, resumable first-pass Odoo -> isolated PG18 staging
# backfill. Source remains READ ONLY; customer JSON only travels by pipe.
# No production DB/dashboard/MCP changes, no background scheduler.
set -euo pipefail
set +x
umask 077

if [[ "${1:-}" != full-pass || $# != 5 ]]; then
  echo "Usage: $0 full-pass --ack-source-contract --ack-retention --ack-copy --ack-sensitive-data" >&2
  exit 2
fi
shift
for ack in --ack-source-contract --ack-retention --ack-copy --ack-sensitive-data; do
  found=0
  for arg in "$@"; do [[ "$arg" != "$ack" ]] || found=$((found + 1)); done
  if (( found != 1 )); then
    echo "FAIL: Four unique staging approvals are required" >&2
    exit 2
  fi
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB=panadan-mirror-staging-pg18
RESTORE=panadan-mirror-data-restore-drill-pg18
SOURCE=odoo_calls_full_v1
STREAM=view_reconciliation_v1
BACKUPS=/var/lib/panadan-mirror-staging/backups
KEY=/var/lib/panadan-mirror-staging/backup-identity.txt
CONFIG="$HOME/.config/panadan-mirror-staging"
SOURCE_ENV="$HOME/panadan/.env.db"
MIN_AVAILABLE_KIB=6291456
BACKUP_RESERVE_KIB=131072
BACKUP_EVERY_RECORDS=5000
PAGE_BUDGET=2000
INITIAL_RECORDS=825
INITIAL_PAGES=24
active_child=0

command -v flock >/dev/null
command -v age >/dev/null
command -v age-keygen >/dev/null
command -v df >/dev/null
install -d -m 700 "$CONFIG"
exec 8>"$CONFIG/full-pass.lock"
flock -n 8 || { echo "FAIL: Another full-pass backfill is running" >&2; exit 2; }
sudo -v

stage_sql() {
  sudo -n docker exec "$DB" psql -X -Atq -v ON_ERROR_STOP=1 \
    -U panadan_stage_owner -d panadan_ci -c "$1"
}

on_exit() {
  local rc=$?
  trap - EXIT
  if (( rc != 0 )); then
    echo "STOP: Full-pass runner failed; the last committed checkpoint remains intact" >&2
    if (( active_child )); then
      if ! stage_sql "UPDATE panadan_ingest.sources SET enabled=FALSE
          WHERE source_key='$SOURCE' AND enabled=TRUE;" >/dev/null; then
        echo "URGENT: Could not disable staging ingestion; inspect it before resuming" >&2
      fi
    fi
  fi
  exit "$rc"
}
trap on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

disk_floor() {
  local available reserve="${1:-0}"
  available="$(df -Pk /var/lib/panadan-mirror-staging | awk 'NR==2 {print $4}')"
  [[ "$available" =~ ^[0-9]+$ ]] || {
    echo "FAIL: Cannot measure staging disk space" >&2
    return 2
  }
  if (( available < MIN_AVAILABLE_KIB + reserve )); then
    echo "STOP: Disk free space is below the 6 GiB safety floor plus backup reserve" >&2
    return 2
  fi
}

read_state() {
  local result
  result="$(stage_sql "SELECT current_database() || '|' ||
    current_setting('server_version_num') || '|' ||
    COALESCE((SELECT enabled::text FROM panadan_ingest.sources
              WHERE source_key='$SOURCE'), 'missing') || '|' ||
    (SELECT count(*) FROM panadan_ingest.source_records
     WHERE source_key='$SOURCE')::text || '|' ||
    (SELECT count(*) FROM panadan_ingest.raw_revisions
     WHERE source_key='$SOURCE')::text || '|' ||
    (SELECT count(*) FROM panadan_ingest.sync_runs
     WHERE source_key='$SOURCE' AND stream='$STREAM')::text || '|' ||
    COALESCE((SELECT sum(examined)::text FROM panadan_ingest.sync_runs
              WHERE source_key='$SOURCE' AND stream='$STREAM'), 'missing') || '|' ||
    COALESCE((SELECT cursor->>'pass' FROM panadan_ingest.sync_checkpoints
              WHERE source_key='$SOURCE' AND stream='$STREAM'), 'missing') || '|' ||
    COALESCE((SELECT cursor->>'last_id' FROM panadan_ingest.sync_checkpoints
              WHERE source_key='$SOURCE' AND stream='$STREAM'), 'missing') || '|' ||
    COALESCE((SELECT max(external_id::bigint)::text
              FROM panadan_ingest.source_records WHERE source_key='$SOURCE'),
             'missing');")"
  IFS='|' read -r dbname pg_version enabled records revisions pages examined pass cursor max_id <<< "$result"
  [[ "$dbname" == panadan_ci && "$pg_version" == 180006 &&
     "$enabled" == false && "$records" =~ ^[0-9]+$ &&
     "$revisions" =~ ^[0-9]+$ && "$pages" =~ ^[0-9]+$ &&
     "$examined" =~ ^[0-9]+$ && "$pass" =~ ^[0-9]+$ &&
     "$cursor" =~ ^[0-9]+$ && "$max_id" =~ ^[0-9]+$ &&
     "$records" -ge "$INITIAL_RECORDS" &&
     "$pages" -ge "$INITIAL_PAGES" &&
     "$pages" -le "$PAGE_BUDGET" &&
     "$revisions" == "$records" && "$examined" == "$records" &&
     ( ( "$pass" == 1 && "$cursor" == "$max_id" ) ||
       ( "$pass" == 2 && "$cursor" == 0 ) ) ]] || {
    echo "FAIL: Unexpected staging identity, source state, count, or cursor" >&2
    return 2
  }
}

integrity_check() {
  local verdict
  verdict="$(stage_sql "WITH current AS (
    SELECT s.external_id,s.revision_no,s.current_digest,s.is_deleted,
           r.digest,r.operation,r.payload
    FROM panadan_ingest.source_records s
    JOIN panadan_ingest.raw_revisions r
      ON r.source_key=s.source_key
     AND r.external_id=s.external_id AND r.revision_no=s.revision_no
    WHERE s.source_key='$SOURCE'
  )
  SELECT CASE WHEN (SELECT count(*) FROM current)=$records
   AND (SELECT bool_and(
     revision_no=1 AND is_deleted=FALSE AND operation='upsert'
     AND current_digest=digest AND current_digest ~ '^[0-9a-f]{64}$'
     AND payload->>'source_schema'='odoo_view_37_v1'
     AND payload->>'id'=external_id
     AND jsonb_typeof(payload->'source_rows')='array'
     AND jsonb_array_length(payload->'source_rows')>=1
   ) FROM current) IS TRUE
   AND NOT EXISTS (
     SELECT 1 FROM current c
     CROSS JOIN LATERAL jsonb_array_elements(c.payload->'source_rows') v(row)
     WHERE jsonb_typeof(v.row)<>'object'
       OR (SELECT count(*) FROM jsonb_object_keys(v.row))<>37
       OR v.row->>'id'<>c.external_id
   )
   AND (SELECT COALESCE(sum(jsonb_array_length(payload->'source_rows')),0)
        FROM current)>=$records
   AND (SELECT enabled=FALSE FROM panadan_ingest.sources
        WHERE source_key='$SOURCE') IS TRUE
  THEN 'PASS' ELSE 'FAIL' END;")"
  [[ "$verdict" == PASS ]] || {
    echo "FAIL: Complete staging payload/digest/schema validation" >&2
    return 2
  }
}

backup_checkpoint() {
  # A backup file is always unique; an earlier interrupted .age archive
  # is never reused or overwritten. Failure messages are deliberately explicit.
  local recipient archive
  disk_floor "$BACKUP_RESERVE_KIB" || return 2
  if ! recipient="$(sudo -n age-keygen -y "$KEY")"; then
    echo "FAIL: Cannot derive encrypted-backup recipient" >&2
    return 2
  fi
  [[ "$recipient" == age1* ]] || {
    echo "FAIL: Invalid encrypted-backup recipient" >&2
    return 2
  }
  archive="$BACKUPS/odoo-mirror-$records-pass$pass-$(date -u +%Y%m%dT%H%M%S%N)-$$.dump.age"
  if sudo -n test -e "$archive"; then
    echo "FAIL: Refusing to overwrite an existing encrypted archive" >&2
    return 2
  fi

  echo "=== Encrypt checkpoint: $records records, pass $pass ==="
  if sudo -n docker exec "$DB" pg_dump \
        -U panadan_stage_owner -d panadan_ci -Fc |
     sudo -n age -r "$recipient" -o "$archive"; then
    sudo -n chmod 600 "$archive" || return 2
  else
    echo "FAIL: pg_dump-to-age encrypted backup pipeline" >&2
    sudo -n rm -f -- "$archive"
    return 2
  fi
  if ! (sudo -n age -d -i "$KEY" "$archive" |
        sudo -n docker exec -i "$DB" pg_restore -l >/dev/null); then
    echo "FAIL: Encrypted archive cannot be decrypted and indexed" >&2
    return 2
  fi
  [[ "$(sudo -n stat -c %a "$archive")" == 600 ]] || {
    echo "FAIL: Archive file permissions are not 0600" >&2
    return 2
  }
  last_backed_records="$records"
  echo "PASS: Encrypted, decryptable archive for $records records"
  disk_floor
}

echo "=== Full first-pass staging preflight ==="
[[ "$(sudo -n docker port "$DB" 5432/tcp)" == 127.0.0.1:55432 ]] || {
  echo "FAIL: Unexpected staging port" >&2; exit 2;
}
[[ "$(sudo -n docker inspect "$RESTORE" --format '{{.HostConfig.NetworkMode}}')" == none ]] || {
  echo "FAIL: Restore network isolation changed" >&2; exit 2;
}
[[ "$(sudo -n docker inspect panadan-vpn-1 --format '{{.State.Health.Status}}')" == healthy ]] || {
  echo "FAIL: Odoo source VPN unhealthy" >&2; exit 2;
}
[[ -f "$CONFIG/writer.dsn" && ! -L "$CONFIG/writer.dsn" &&
   "$(stat -c %a "$CONFIG/writer.dsn")" == 600 ]] || {
  echo "FAIL: Restricted staging writer DSN configuration changed" >&2; exit 2;
}
[[ -s "$SOURCE_ENV" ]] || {
  echo "FAIL: Private Odoo source environment missing" >&2; exit 2;
}
sudo -n test -f "$KEY"
sudo -n test ! -L "$KEY"
[[ "$(sudo -n stat -c %a "$KEY")" == 600 ]] || {
  echo "FAIL: Encryption private identity must be mode 0600" >&2; exit 2;
}
sudo -n install -d -m 700 "$BACKUPS"
disk_floor "$BACKUP_RESERVE_KIB"
read_state
integrity_check
echo "PASS: Current $records records, $pages pages, pass $pass; 37-column payloads"
echo "PASS: Staging source disabled, checkpoint consistent, 6 GiB floor"

# Previous 825-record restore is the known good rollback baseline.
restored="$(sudo -n docker exec "$RESTORE" psql -X -Atq -v ON_ERROR_STOP=1 \
  -U panadan_stage_owner -d panadan_restore_825 -c \
  "SELECT (SELECT count(*) FROM panadan_ingest.source_records
   WHERE source_key='$SOURCE')::text || '|' ||
   (SELECT count(*) FROM panadan_ingest.raw_revisions
   WHERE source_key='$SOURCE')::text;")"
[[ "$restored" == '825|825' ]] || {
  echo "FAIL: Independent 825-record restore missing" >&2; exit 2;
}
echo "PASS: Independent 825-record restore preserved"

# Backup the CURRENT point before proceeding. At the known 1,125-record
# interruption this recovers the previously unarchived 300-row chunk.
backup_checkpoint
if (( pass == 2 )); then
  echo "FIRST SOURCE PASS ALREADY COMPLETE: records=$records pages=$pages"
  exit 0
fi

while (( pass == 1 )); do
  disk_floor
  read_state
  before_records="$records"
  before_pages="$pages"
  if (( pages + 3 > PAGE_BUDGET )); then
    echo "STOP: 2000-page safety ceiling reached before source exhausted" >&2
    exit 2
  fi

  echo "=== Odoo first-pass continuation; $records calls / $pages pages ==="
  active_child=1
  PANADAN_MIRROR_PAGE_LIMIT=3 \
  PANADAN_MIRROR_MIN_AVAILABLE_KIB="$MIN_AVAILABLE_KIB" \
    bash "$ROOT/tools/run-odoo-mirror-staging-next.sh" \
      next-batch --ack-source-contract --ack-retention \
      --ack-copy --ack-sensitive-data
  active_child=0

  read_state
  (( pages > before_pages && pages <= before_pages + 3 )) || {
    echo "FAIL: Import page counter did not advance safely" >&2
    exit 2
  }
  (( records >= before_records && records <= before_records + 300 )) || {
    echo "FAIL: Import record counter exceeded page budget" >&2
    exit 2
  }
  if (( pass == 1 && records == before_records )); then
    echo "FAIL: Import made no progress" >&2
    exit 2
  fi

  if (( records - last_backed_records >= BACKUP_EVERY_RECORDS || pass == 2 )); then
    integrity_check
    echo "PASS: Full stored-payload integrity and checkpoint consistent"
    backup_checkpoint
  fi
done

read_state
[[ "$pass" == 2 && "$cursor" == 0 && "$enabled" == false ]] || {
  echo "FAIL: First pass did not complete" >&2
  exit 2
}
integrity_check
echo "COMPLETE FIRST SOURCE PASS: records=$records revisions=$revisions pages=$pages"
echo "Latest encrypted recovery checkpoint verified; staging source disabled"
