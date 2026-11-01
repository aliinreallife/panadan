#!/usr/bin/env bash
# Opt-in encrypted off-site backups of Panadan's OWN PostgreSQL 18 database.
# Nothing touches source Odoo, source VPN, live SQLite, or existing containers.
set -euo pipefail
set +x
umask 077

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PRIVATE_ENV="$ROOT/.env.platform"
COMPOSE="$ROOT/compose.platform.yaml"
LOCAL_DIR="$ROOT/data/platform-backups/encrypted"

die() { echo "PLATFORM BACKUP FAILED: $*" >&2; exit 1; }
usage() { echo "Usage: bash tools/backup-platform-offsite.sh [--check]" >&2; exit 2; }

if [[ $# -gt 1 || ( $# -eq 1 && "$1" != "--check" ) ]]; then usage; fi

require_config() {
  for exe in docker age rclone flock openssl sha256sum mktemp stat; do
    command -v "$exe" >/dev/null 2>&1 || die "Missing required command: $exe"
  done
  docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is required"
  [[ -s "$PRIVATE_ENV" && ! -L "$PRIVATE_ENV" ]] || die "Missing, empty or symlinked .env.platform"
  local perms
  perms="$(stat -c '%a' "$PRIVATE_ENV")" || die "Cannot inspect private platform configuration"
  (( (8#$perms & 8#077) == 0 )) || die ".env.platform must not be group/world accessible"
  [[ -f "$COMPOSE" && ! -L "$COMPOSE" ]] || die "Expected owned PostgreSQL Compose file missing"
  [[ "$(grep -Ec '^PANADAN_PLATFORM_DB_PASSWORD=' "$PRIVATE_ENV")" == 1 ]] ||
    die "Expected exactly one platform database password in private configuration"
  grep -Eq '^PANADAN_PLATFORM_DB_PASSWORD=[[:xdigit:]]{64}
  [[ "${PANADAN_BACKUP_AGE_RECIPIENT:-}" == age1* ]] || die "Missing age PUBLIC recipient"
  [[ "${PANADAN_PLATFORM_BACKUP_RCLONE_DEST:-}" =~ ^[A-Za-z0-9_-]+:.+ ]] ||
    die "Set PANADAN_PLATFORM_BACKUP_RCLONE_DEST to a separately hosted rclone REMOTE:path"
  [[ "$PANADAN_PLATFORM_BACKUP_RCLONE_DEST" != *$'\n'* ]] || die "Invalid remote destination"
}

compose() {
  env -u PANADAN_PLATFORM_DB_PASSWORD docker compose --env-file "$PRIVATE_ENV" -f "$COMPOSE" "$@"
}

require_server() {
  local cid status identity
  cid="$(compose ps -q db 2>/dev/null)" || die "Could not inspect the owned PostgreSQL service"
  [[ -n "$cid" ]] || die "Owned PostgreSQL service is not running"
  status="$(docker inspect --format '{{.State.Running}}' "$cid" 2>/dev/null)" ||
    die "Could not inspect the owned PostgreSQL container"
  [[ "$status" == true ]] || die "Owned PostgreSQL service is not running"
  # All queries are fixed metadata-only reads, against the separate panadan-platform service.
  identity="$(docker exec "$cid" psql -X -At -v ON_ERROR_STOP=1 \
    -U panadan_owner -d panadan -c "
SELECT current_setting('server_version_num')::integer / 10000,
       current_database(), current_user,
       (SELECT count(*) FROM information_schema.tables
        WHERE table_schema='panadan_ingest' AND table_type='BASE TABLE');" 2>/dev/null)" ||
    die "Cannot validate owned PostgreSQL identity and schema"
  [[ "$identity" == "18|panadan|panadan_owner|7" ]] ||
    die "Unexpected PostgreSQL major, database owner, database name or ingestion schema"
  CONTAINER_ID="$cid"
}

require_config
require_server
rclone lsf "$PANADAN_PLATFORM_BACKUP_RCLONE_DEST" >/dev/null 2>&1 ||
  die "Configured off-site destination is unavailable"

if [[ $# -eq 1 ]]; then
  echo "PASS: Owned PostgreSQL identity, encryption recipient and off-site destination preflight"
  exit 0
fi

# Prevent parallel timer/manual snapshots. Never alter database deployment state.
LOCK_FILE="${PANADAN_PLATFORM_BACKUP_LOCK_FILE:-/run/lock/panadan-platform-offsite.lock}"
[[ ! -L "$LOCK_FILE" ]] || die "Backup lock file must not be a symlink"
exec 9>"$LOCK_FILE"
flock -n 9 || die "Another owned PostgreSQL backup is running"

WORK="$(mktemp -d -t panadan-platform-backup-XXXXXXXX)" || die "Cannot create protected temporary directory"
cleanup() { rm -rf -- "$WORK"; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

STAMP="$(date -u +%Y%m%dT%H%M%SZ)-$(openssl rand -hex 8)"
NAME="panadan-$STAMP.dump.age"
DUMP="$WORK/panadan.dump"
CIPHER="$WORK/$NAME"
REMOTE="$PANADAN_PLATFORM_BACKUP_RCLONE_DEST/$NAME"

# Streaming from pg_dump leaves NO durable plaintext dump in the repository.
# It includes all owned schemas (including future panadan_auth), not source Odoo.
docker exec "$CONTAINER_ID" pg_dump -U panadan_owner -d panadan -Fc > "$DUMP" 2>/dev/null ||
  die "Owned PostgreSQL pg_dump failed"
[[ -s "$DUMP" ]] || die "Owned PostgreSQL archive was empty"
docker exec -i "$CONTAINER_ID" pg_restore --list < "$DUMP" >/dev/null 2>&1 ||
  die "Owned PostgreSQL archive TOC check failed"

age -r "$PANADAN_BACKUP_AGE_RECIPIENT" -o "$CIPHER" "$DUMP" >/dev/null 2>&1 ||
  die "Public-key encryption failed"
[[ -s "$CIPHER" ]] || die "Encrypted archive was empty"
chmod 600 "$CIPHER"
# Immutable remote object names; never silently replace an existing backup.
rclone copyto "$CIPHER" "$REMOTE" --immutable --no-traverse >/dev/null 2>&1 ||
  die "Off-site encrypted transfer failed"
EXPECTED="$(sha256sum "$CIPHER" | cut -d' ' -f1)"
ACTUAL="$(rclone cat "$REMOTE" 2>/dev/null | sha256sum | cut -d' ' -f1)" ||
  die "Could not read back encrypted off-site object"
[[ "$EXPECTED" == "$ACTUAL" ]] || die "Encrypted off-site checksum mismatch"

[[ ! -L "$LOCAL_DIR" ]] || die "Local encrypted-backup destination must not be a symlink"
install -d -m 700 "$LOCAL_DIR"
install -m 600 "$CIPHER" "$LOCAL_DIR/$NAME"
echo "PASS: Encrypted owned PostgreSQL backup uploaded and byte-verified: $NAME"
echo "NOTE: Restore validation, independent key escrow and failure alerts are still required"
 "$PRIVATE_ENV" ||
    die "Malformed owned PostgreSQL configuration"
  [[ "${PANADAN_BACKUP_AGE_RECIPIENT:-}" == age1* ]] || die "Missing age PUBLIC recipient"
  [[ "${PANADAN_PLATFORM_BACKUP_RCLONE_DEST:-}" =~ ^[A-Za-z0-9_-]+:.+ ]] ||
    die "Set PANADAN_PLATFORM_BACKUP_RCLONE_DEST to a separately hosted rclone REMOTE:path"
  [[ "$PANADAN_PLATFORM_BACKUP_RCLONE_DEST" != *$'\n'* ]] || die "Invalid remote destination"
}

compose() {
  env -u PANADAN_PLATFORM_DB_PASSWORD docker compose --env-file "$PRIVATE_ENV" -f "$COMPOSE" "$@"
}

require_server() {
  local cid status identity
  cid="$(compose ps -q db 2>/dev/null)" || die "Could not inspect the owned PostgreSQL service"
  [[ -n "$cid" ]] || die "Owned PostgreSQL service is not running"
  status="$(docker inspect --format '{{.State.Running}}' "$cid" 2>/dev/null)" ||
    die "Could not inspect the owned PostgreSQL container"
  [[ "$status" == true ]] || die "Owned PostgreSQL service is not running"
  # All queries are fixed metadata-only reads, against the separate panadan-platform service.
  identity="$(docker exec "$cid" psql -X -At -v ON_ERROR_STOP=1 \
    -U panadan_owner -d panadan -c "
SELECT current_setting('server_version_num')::integer / 10000,
       current_database(), current_user,
       (SELECT count(*) FROM information_schema.tables
        WHERE table_schema='panadan_ingest' AND table_type='BASE TABLE');" 2>/dev/null)" ||
    die "Cannot validate owned PostgreSQL identity and schema"
  [[ "$identity" == "18|panadan|panadan_owner|7" ]] ||
    die "Unexpected PostgreSQL major, database owner, database name or ingestion schema"
  CONTAINER_ID="$cid"
}

require_config
require_server
rclone lsf "$PANADAN_PLATFORM_BACKUP_RCLONE_DEST" >/dev/null 2>&1 ||
  die "Configured off-site destination is unavailable"

if [[ $# -eq 1 ]]; then
  echo "PASS: Owned PostgreSQL identity, encryption recipient and off-site destination preflight"
  exit 0
fi

# Prevent parallel timer/manual snapshots. Never alter database deployment state.
exec 9>"$ROOT/data/.panadan-platform-offsite.lock"
flock -n 9 || die "Another owned PostgreSQL backup is running"

WORK="$(mktemp -d -t panadan-platform-backup-XXXXXXXX)" || die "Cannot create protected temporary directory"
cleanup() { rm -rf -- "$WORK"; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

STAMP="$(date -u +%Y%m%dT%H%M%SZ)-$(openssl rand -hex 8)"
NAME="panadan-$STAMP.dump.age"
DUMP="$WORK/panadan.dump"
CIPHER="$WORK/$NAME"
REMOTE="$PANADAN_PLATFORM_BACKUP_RCLONE_DEST/$NAME"

# Streaming from pg_dump leaves NO durable plaintext dump in the repository.
# It includes all owned schemas (including future panadan_auth), not source Odoo.
docker exec "$CONTAINER_ID" pg_dump -U panadan_owner -d panadan -Fc > "$DUMP" 2>/dev/null ||
  die "Owned PostgreSQL pg_dump failed"
[[ -s "$DUMP" ]] || die "Owned PostgreSQL archive was empty"
docker exec -i "$CONTAINER_ID" pg_restore --list < "$DUMP" >/dev/null 2>&1 ||
  die "Owned PostgreSQL archive TOC check failed"

age -r "$PANADAN_BACKUP_AGE_RECIPIENT" -o "$CIPHER" "$DUMP" >/dev/null 2>&1 ||
  die "Public-key encryption failed"
[[ -s "$CIPHER" ]] || die "Encrypted archive was empty"
chmod 600 "$CIPHER"
# Immutable remote object names; never silently replace an existing backup.
rclone copyto "$CIPHER" "$REMOTE" --immutable --no-traverse >/dev/null 2>&1 ||
  die "Off-site encrypted transfer failed"
EXPECTED="$(sha256sum "$CIPHER" | cut -d' ' -f1)"
ACTUAL="$(rclone cat "$REMOTE" 2>/dev/null | sha256sum | cut -d' ' -f1)" ||
  die "Could not read back encrypted off-site object"
[[ "$EXPECTED" == "$ACTUAL" ]] || die "Encrypted off-site checksum mismatch"

[[ ! -L "$LOCAL_DIR" ]] || die "Local encrypted-backup destination must not be a symlink"
install -d -m 700 "$LOCAL_DIR"
install -m 600 "$CIPHER" "$LOCAL_DIR/$NAME"
echo "PASS: Encrypted owned PostgreSQL backup uploaded and byte-verified: $NAME"
echo "NOTE: Restore validation, independent key escrow and failure alerts are still required"
