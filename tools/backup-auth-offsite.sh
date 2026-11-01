#!/usr/bin/env bash
# Online SQLite auth backup -> age public-key encryption -> independently
# verified rclone off-site object. No private age key on this host.
set -euo pipefail
umask 077

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_CONTAINER="${PANADAN_BACKUP_WEB_CONTAINER:-panadan-web-1}"
LOCAL_DIR="${PANADAN_BACKUP_LOCAL_DIR:-$ROOT/data/auth-backups/encrypted}"

fail() { echo "BACKUP FAILED: $*" >&2; exit 1; }
require_config() {
  command -v docker >/dev/null || fail "Docker missing"
  command -v python3 >/dev/null || fail "Python 3 missing"
  command -v age >/dev/null || fail "age encryption command missing"
  command -v rclone >/dev/null || fail "rclone off-site client missing"
  command -v flock >/dev/null || fail "flock lock command missing"
  [[ "${PANADAN_BACKUP_AGE_RECIPIENT:-}" == age1* ]] || fail "PANADAN_BACKUP_AGE_RECIPIENT must be an age public key"
  [[ "${PANADAN_BACKUP_RCLONE_DEST:-}" =~ ^[A-Za-z0-9_-]+:.+ ]] || fail "PANADAN_BACKUP_RCLONE_DEST must be an rclone REMOTE:path, not a local directory"
  [[ -f "$ROOT/compose.prod.yaml" ]] || fail "Panadan repository missing"
}

require_config
if [[ "${1:-}" == "--check" ]]; then
  docker inspect "$DB_CONTAINER" --format '{{.State.Running}}' | grep -qx 'true' \
    || fail "Panadan web container not running"
  rclone lsf "$PANADAN_BACKUP_RCLONE_DEST" >/dev/null || fail "Off-site remote unreachable"
  echo "PASS: Backup prerequisites and independent remote available"
  exit 0
fi
[[ "$#" -eq 0 ]] || fail "Usage: bash tools/backup-auth-offsite.sh [--check]"

# Prevent overlapping timer/manual runs and ambiguous cleanup.
exec 9>"${PANADAN_BACKUP_LOCK_FILE:-/run/lock/panadan-auth-backup.lock}"
flock -n 9 || fail "another Panadan auth backup is running"
docker inspect "$DB_CONTAINER" --format '{{.State.Running}}' | grep -qx 'true' \
  || fail "Panadan web container not running"
WORK="$(mktemp -d -t panadan-auth-XXXXXXXX)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)-${RANDOM}${RANDOM}"
NAME="auth-${STAMP}.sqlite"
CONTAINER_TMP="/data/.${NAME}.tmp"
PLAIN="$WORK/$NAME"
CIPHER="$WORK/$NAME.age"
REMOTE="${PANADAN_BACKUP_RCLONE_DEST%/}/$NAME.age"

cleanup() {
  docker exec "$DB_CONTAINER" rm -f -- "$CONTAINER_TMP" >/dev/null 2>&1 || true
  rm -rf -- "$WORK"
}
trap cleanup EXIT HUP INT TERM

# The backup() API ensures a consistent snapshot while Panadan keeps serving.
docker exec -e PANADAN_BACKUP_TEMP="$CONTAINER_TMP" "$DB_CONTAINER" python -c '
import os,sqlite3
source=sqlite3.connect("file:/data/auth.sqlite?mode=ro",uri=True)
try:
    target=sqlite3.connect(os.environ["PANADAN_BACKUP_TEMP"])
    try:
        source.backup(target)
    finally:
        target.close()
finally:
    source.close()
'
docker cp "$DB_CONTAINER:$CONTAINER_TMP" "$PLAIN" >/dev/null
chmod 600 "$PLAIN"

# Detect corruption and missing/empty schema before encrypting or uploading.
python3 - "$PLAIN" <<'PY'
import sqlite3,sys
path=sys.argv[1]
db=sqlite3.connect(f"file:{path}?mode=ro",uri=True)
try:
    assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok", "SQLite integrity failed"
    count=db.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone()[0]
    assert count > 0, "SQLite schema unexpectedly empty"
finally:
    db.close()
PY

age -r "$PANADAN_BACKUP_AGE_RECIPIENT" -o "$CIPHER" "$PLAIN"
chmod 600 "$CIPHER"
# Write to the remote before retaining a local encrypted recovery copy.
rclone copyto "$CIPHER" "$REMOTE" --no-traverse
# Verify actual remote bytes, not just object presence / last-modified metadata.
expected="$(sha256sum "$CIPHER" | cut -d' ' -f1)"
actual="$(rclone cat "$REMOTE" | sha256sum | cut -d' ' -f1)"
[[ "$expected" == "$actual" ]] || fail "Remote encrypted object checksum mismatch"

install -d -m 700 "$LOCAL_DIR"
install -m 600 "$CIPHER" "$LOCAL_DIR/$NAME.age"
echo "PASS: Encrypted off-site backup verified: $NAME.age"
echo "NOTE: Verify recovery independently with the private age key kept off the VPS"
