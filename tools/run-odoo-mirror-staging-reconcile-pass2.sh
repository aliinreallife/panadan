#!/usr/bin/env bash
# Explicit, restartable COMPLETE second reconciliation pass against the
# 37-column read-only Odoo view. Writes only to the isolated PG18 staging
# database with the reviewed append-only digest/CAS importer. Not a daemon.
set -euo pipefail
set +x
umask 077

if [[ "\${1:-}" != reconcile-pass-2 || $# != 5 ]]; then
  echo "Usage: $0 reconcile-pass-2 --ack-source-contract --ack-retention --ack-copy --ack-sensitive-data" >&2
  exit 2
fi
shift
for approval in --ack-source-contract --ack-retention --ack-copy --ack-sensitive-data; do
  seen=0
  for flag in "$@"; do [[ "$flag" != "$approval" ]] || seen=$((seen+1)); done
  if (( seen != 1 )); then
    echo "FAIL: Exactly four unique sensitive-data staging approvals required" >&2
    exit 2
  fi
done

ROOT="$(cd "$(dirname "\${BASH_SOURCE[0]}")/.." && pwd)"
STAGE=panadan-mirror-staging-pg18
RESTORE=panadan-mirror-data-restore-drill-pg18
SOURCE=odoo_calls_full_v1
STREAM=view_reconciliation_v1
CONFIG="$HOME/.config/panadan-mirror-staging"
SOURCE_ENV="$HOME/panadan/.env.db"
BACKUPS=/var/lib/panadan-mirror-staging/backups
KEY=/var/lib/panadan-mirror-staging/backup-identity.txt
MIN_AVAILABLE_KIB=6291456
BACKUP_RESERVE_KIB=131072
BACKUP_EVERY_PAGES=300
PAGE_BUDGET=2600
BASELINE_RECORDS=95912
BASELINE_PAGES=975
RUNNING_CHILD=0

command -v flock >/dev/null
command -v age >/dev/null
command -v age-keygen >/dev/null
command -v df >/dev/null
install -d -m 700 "$CONFIG"
exec 8>"$CONFIG/reconciliation-pass2.lock"
flock -n 8 || { echo "STOP: Pass-2 reconciliation is already running" >&2; exit 2; }
sudo -v

stage_sql() {
  sudo -n docker exec "$STAGE" psql -X -Atq -v ON_ERROR_STOP=1 \
    -U panadan_stage_owner -d panadan_ci -c "$1"
}

on_exit() {
  local result=$?
  trap - EXIT
  if (( result != 0 )); then
    echo "STOP: Reconciliation ended early; committed checkpoints remain intact" >&2
    if (( RUNNING_CHILD )); then
      if ! stage_sql "UPDATE panadan_ingest.sources SET enabled=FALSE
          WHERE source_key='$SOURCE' AND enabled=TRUE;" >/dev/null; then
        echo "URGENT: Check and disable the staging source before resuming" >&2
      fi
    fi
  fi
  exit "$result"
}
trap on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

check_disk() {
  local reserve="\${1:-0}" free
  free="$(df -Pk /var/lib/panadan-mirror-staging | awk 'NR==2 {print $4}')"
  [[ "$free" =~ ^[0-9]+$ ]] || {
    echo "FAIL: Cannot measure staging disk" >&2; return 2;
  }
  if (( free < MIN_AVAILABLE_KIB + reserve )); then
    echo "STOP: Disk space below 6 GiB safety floor + backup reserve" >&2
    return 2
  fi
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
  IFS='|' read -r dbname pg_version enabled records revisions pages pass cursor max_id <<< "$state"
  [[ "$dbname" == panadan_ci && "$pg_version" == 180006 &&
     "$enabled" == false &&
     "$records" =~ ^[0-9]+$ && "$revisions" =~ ^[0-9]+$ &&
     "$pages" =~ ^[0-9]+$ && "$pass" =~ ^[0-9]+$ &&
     "$cursor" =~ ^[0-9]+$ && "$max_id" =~ ^[0-9]+$ &&
     "$records" -ge "$BASELINE_RECORDS" &&
     "$revisions" -ge "$records" &&
     "$pages" -ge "$BASELINE_PAGES" && "$pages" -le "$PAGE_BUDGET" &&
     ( ( "$pass" == 2 && "$cursor" -le "$max_id" ) ||
       ( "$pass" == 3 && "$cursor" == 0 ) ) ]] || {
    echo "FAIL: Stage state, checkpoint or PG18 identity drift" >&2
    return 2
  }
}

integrity_check() {
  local checked
  checked="$(stage_sql "WITH current AS (
    SELECT s.external_id, s.revision_no, s.current_digest, s.is_deleted,
           r.digest, r.operation, r.payload
    FROM panadan_ingest.source_records s
    JOIN panadan_ingest.raw_revisions r
      ON r.source_key=s.source_key
     AND r.external_id=s.external_id
     AND r.revision_no=s.revision_no
    WHERE s.source_key='$SOURCE'
  )
  SELECT CASE WHEN
    (SELECT count(*) FROM current)=$records
    AND (SELECT count(*) FROM panadan_ingest.raw_revisions
         WHERE source_key='$SOURCE')=$revisions
    AND (SELECT bool_and(
      revision_no>=1 AND is_deleted=FALSE AND operation='upsert'
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
    AND (SELECT enabled=FALSE FROM panadan_ingest.sources
         WHERE source_key='$SOURCE') IS TRUE
  THEN 'PASS' ELSE 'FAIL' END;")"
  [[ "$checked" == PASS ]] || {
    echo "FAIL: Full current-record/revision/payload integrity" >&2
    return 2
  }
  echo "PASS: $records current calls, $revisions revisions, $pages pages"
}

check_recovery_baseline() {
  local recovery
  recovery="$(sudo -n docker exec "$RESTORE" \
    psql -X -Atq -v ON_ERROR_STOP=1 \
    -U panadan_stage_owner -d panadan_restore_95912 -c \
    "SELECT (SELECT count(*) FROM panadan_ingest.source_records
             WHERE source_key='$SOURCE')::text || '|' ||
            (SELECT count(*) FROM panadan_ingest.raw_revisions
             WHERE source_key='$SOURCE')::text || '|' ||
            (SELECT cursor->>'pass' FROM panadan_ingest.sync_checkpoints
             WHERE source_key='$SOURCE' AND stream='$STREAM');")"
  [[ "$recovery" == '95912|95912|2' ]] || {
    echo "FAIL: Verified first-pass restore baseline unavailable" >&2
    return 2
  }
}

backup_checkpoint() {
  local recipient archive
  check_disk "$BACKUP_RESERVE_KIB"
  recipient="$(sudo -n age-keygen -y "$KEY")"
  [[ "$recipient" == age1* ]] || {
    echo "FAIL: Invalid encrypted-backup recipient" >&2
    return 2
  }
  archive="$BACKUPS/odoo-mirror-reconcile-$records-pass$pass-$(date -u +%Y%m%dT%H%M%S%N)-$$.dump.age"
  sudo -n test ! -e "$archive"
  echo "=== Encrypt reconciliation checkpoint: $records calls / pass $pass ==="
  if sudo -n docker exec "$STAGE" \
      pg_dump -U panadan_stage_owner -d panadan_ci -Fc |
     sudo -n age -r "$recipient" -o "$archive"; then
    sudo -n chmod 600 "$archive"
  else
    echo "FAIL: Encrypted checkpoint creation" >&2
    sudo -n rm -f -- "$archive"
    return 2
  fi
  # Drain entire source stream after pg_restore reads the TOC: no SIGPIPE.
  if ! (sudo -n age -d -i "$KEY" "$archive" |
        sudo -n docker exec -i "$STAGE" sh -c \
          'pg_restore -l >/dev/null && cat >/dev/null'); then
    echo "FAIL: Encrypted checkpoint decryption/catalog verification" >&2
    return 2
  fi
  [[ "$(sudo -n stat -c %a "$archive")" == 600 ]] || {
    echo "FAIL: Encrypted backup permissions changed" >&2
    return 2
  }
  LAST_BACKUP_PAGES="$pages"
  echo "PASS: Encrypted private reconciliation checkpoint verified"
}

echo "=== Pass-2 reconciliation preflight ==="
[[ "$(sudo -n docker port "$STAGE" 5432/tcp)" == 127.0.0.1:55432 ]] || {
  echo "FAIL: Staging loopback isolation changed" >&2; exit 2;
}
[[ "$(sudo -n docker inspect "$RESTORE" \
  --format '{{.HostConfig.NetworkMode}}')" == none ]] || {
  echo "FAIL: Independent restore no longer network-isolated" >&2; exit 2;
}
[[ "$(sudo -n docker inspect panadan-vpn-1 \
  --format '{{.State.Health.Status}}')" == healthy ]] || {
  echo "FAIL: Odoo source VPN unhealthy" >&2; exit 2;
}
[[ -f "$CONFIG/writer.dsn" && ! -L "$CONFIG/writer.dsn" &&
   "$(stat -c %a "$CONFIG/writer.dsn")" == 600 &&
   -s "$SOURCE_ENV" ]] || {
  echo "FAIL: Private restricted source/staging configuration unavailable" >&2
  exit 2
}
sudo -n test -f "$KEY"
sudo -n test ! -L "$KEY"
[[ "$(sudo -n stat -c %a "$KEY")" == 600 ]] || {
  echo "FAIL: Backup identity key is not private" >&2; exit 2;
}
sudo -n install -d -m 700 "$BACKUPS"
check_disk "$BACKUP_RESERVE_KIB"
read_state
integrity_check
check_recovery_baseline
echo "PASS: Completed first-pass independent restore still available"
echo "PASS: Pass $pass / cursor metadata verified, source disabled"

# Every invocation checkpoints the CURRENT DB before adding new revisions.
# This also protects a partial reconciliation run after an SSH interruption.
backup_checkpoint

while (( pass == 2 )); do
  check_disk
  read_state
  before_records="$records"
  before_revisions="$revisions"
  before_pages="$pages"
  if (( pages + 3 > PAGE_BUDGET )); then
    echo "STOP: Reconciliation exceeded 2600-page guardrail" >&2
    exit 2
  fi
  echo "=== Reconciliation pass 2: $records calls, $revisions revisions, $pages pages ==="
  RUNNING_CHILD=1
  PANADAN_MIRROR_EXPECTED_PASS=2 \
  PANADAN_MIRROR_PAGE_LIMIT=3 \
  PANADAN_MIRROR_MIN_AVAILABLE_KIB="$MIN_AVAILABLE_KIB" \
    bash "$ROOT/tools/run-odoo-mirror-staging-next.sh" \
      next-batch \
      --ack-source-contract --ack-retention \
      --ack-copy --ack-sensitive-data
  RUNNING_CHILD=0
  read_state
  (( pages > before_pages && pages <= before_pages + 3 )) || {
    echo "FAIL: Committed page count did not advance" >&2
    exit 2
  }
  (( records >= before_records && records <= before_records + 300 &&
     revisions >= before_revisions && revisions <= before_revisions + 300 )) || {
    echo "FAIL: Unexpected source record/revision growth" >&2
    exit 2
  }
  if (( pages - LAST_BACKUP_PAGES >= BACKUP_EVERY_PAGES || pass == 3 )); then
    integrity_check
    backup_checkpoint
  fi
done

read_state
[[ "$pass" == 3 && "$cursor" == 0 && "$enabled" == false ]] || {
  echo "FAIL: Reconciliation pass 2 incomplete" >&2
  exit 2
}
integrity_check
echo "COMPLETE ODOO SECOND RECONCILIATION PASS: records=$records revisions=$revisions pages=$pages"
echo "Checkpoint pass=3 last_id=0; staging source disabled; encrypted recovery checkpoint verified"
