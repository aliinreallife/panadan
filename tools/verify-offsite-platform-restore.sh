#!/usr/bin/env bash
# Restore an age-encrypted Panadan-owned PostgreSQL backup into a disposable,
# network-isolated PostgreSQL 18 Docker container on a TRUSTED LOCAL COMPUTER.
# No source Odoo connection, no VPS changes, no host ports or volume mounts.
set -euo pipefail
umask 077

ARCHIVE="${1:-}"
IDENTITY="${2:-}"
IMAGE="postgres:18.6-alpine3.24@sha256:10a5c69a83035ab5239f5620d708520e8b28f5aa1f2b20143e6024532edadfb5"
NAME="panadan-restore-test-$$"
DB_USER="panadan_owner"
DB_NAME="panadan"

if [[ "$#" != 2 || ! -f "$ARCHIVE" || ! -f "$IDENTITY" ]]; then
  printf 'Usage: bash %s /path/to/panadan.dump.age /path/to/age-identity.txt\n' "$0" >&2
  exit 2
fi

for exe in age docker openssl; do
  command -v "$exe" >/dev/null || {
    echo "Missing local command: $exe" >&2
    exit 1
  }
done
docker info >/dev/null || { echo 'Local Docker daemon unavailable' >&2; exit 1; }
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo 'Required pinned PostgreSQL 18.6 image is missing locally.' >&2
  echo "Run: docker pull $IMAGE" >&2
  exit 1
fi

cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

# No --publish, no --volume. Data and socket live only in the disposable
# container; cluster files are in an ephemeral tmpfs and are discarded.
docker run -d --rm --pull never --name "$NAME" \
  --network none \
  --tmpfs /var/lib/postgresql:rw,nosuid,size=512m \
  -e POSTGRES_USER="$DB_USER" \
  -e POSTGRES_DB="$DB_NAME" \
  -e POSTGRES_PASSWORD="$(openssl rand -hex 24)" \
  "$IMAGE" >/dev/null

healthy=0
for attempt in $(seq 1 40); do
  if docker exec "$NAME" pg_isready -q -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1; then
    healthy=1
    break
  fi
  sleep 1
done
[[ "$healthy" == 1 ]] || { echo 'Disposable PostgreSQL did not become ready' >&2; exit 1; }

# The decrypted archive is streamed into pg_restore's stdin. The only
# reconstructed plaintext database is inside an ephemeral isolated container.
# --no-owner/--no-acl accommodates roles not defined on this empty cluster.
age --decrypt -i "$IDENTITY" "$ARCHIVE" |
  docker exec -i "$NAME" pg_restore --single-transaction --exit-on-error \
    --no-owner --no-acl -U "$DB_USER" -d "$DB_NAME"

result="$(docker exec "$NAME" psql -X -A -t -v ON_ERROR_STOP=1 \
  -U "$DB_USER" -d "$DB_NAME" -c "
SELECT
  current_setting('server_version_num')::integer / 10000,
  count(*)
FROM information_schema.tables
WHERE table_schema='panadan_ingest' AND table_type='BASE TABLE';
")"
[[ "$result" == "18|7" ]] || {
  echo "Restored database has unexpected schema/version metadata" >&2
  exit 1
}
counts="$(docker exec "$NAME" psql -X -A -t -v ON_ERROR_STOP=1 \
  -U "$DB_USER" -d "$DB_NAME" -c "
SELECT (SELECT count(*) FROM panadan_ingest.sources),
       (SELECT count(*) FROM panadan_ingest.sources WHERE enabled),
       (to_regnamespace('panadan_auth') IS NULL);
")"
[[ "$counts" == "0|0|t" ]] || {
  echo "Restored database contents differ from verified pre-migration snapshot" >&2
  exit 1
}
echo "PASS: off-VPS PostgreSQL 18 restore succeeded: 7 ingest tables, 0 sources, no auth schema"
echo "PASS: local disposable database is destroyed automatically after check"
