#!/usr/bin/env bash
# Restore an age-encrypted Panadan-owned PostgreSQL backup into a disposable,
# network-isolated PostgreSQL 18 Docker container on a TRUSTED LOCAL COMPUTER.
# No source Odoo connection, no VPS changes, no host ports or volume mounts.
set -euo pipefail
umask 077

ARCHIVE="${1:-}"
IDENTITY="${2:-}"
IMAGE="postgres:18.6-alpine3.24@sha256:10a5c69a83035ab5239f5620d708520e8b28f5aa1f2b20143e6024532edadfb5"
NAME="panadan-restore-test-$(openssl rand -hex 12)"
DB_USER="panadan_owner"
DB_NAME="panadan"

SCHEMA_SQL=""
GRANTS_SQL=""
if [[ "$#" == 6 && "${3:-}" == "--auth-schema" && "${5:-}" == "--auth-grants" &&
      -f "${4:-}" && -f "${6:-}" ]]; then
  SCHEMA_SQL="$4"
  GRANTS_SQL="$6"
elif [[ "$#" == 4 && "${3:-}" == "--auth-schema" && -f "${4:-}" ]]; then
  SCHEMA_SQL="$4"
elif [[ "$#" != 2 ]]; then
  echo "Usage: bash $0 /path/to/panadan.dump.age /path/to/age-identity.txt [--auth-schema /path/to/003_auth_foundation.sql [--auth-grants /path/to/003_auth_runtime_role.sql]]" >&2
  exit 2
fi
if [[ ! -f "$ARCHIVE" || ! -f "$IDENTITY" ]]; then
  echo "Backup archive or age identity file not found" >&2
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

started=0
cleanup() {
  if [[ "$started" == "1" ]]; then
    docker rm -f "$NAME" >/dev/null 2>&1 || true
  fi
}
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
started=1

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

if [[ -n "$SCHEMA_SQL" ]]; then
  # Apply only inside the disposable no-network cluster, with SQL errors fatal.
  docker exec -i "$NAME" psql -X -v ON_ERROR_STOP=1 -1 \
    -U "$DB_USER" -d "$DB_NAME" < "$SCHEMA_SQL" >/dev/null

  auth_tables="$(docker exec "$NAME" psql -X -A -t -v ON_ERROR_STOP=1 \
    -U "$DB_USER" -d "$DB_NAME" -c "
SELECT count(*)
FROM information_schema.tables
WHERE table_schema='panadan_auth' AND table_type='BASE TABLE';
")"
  [[ "$auth_tables" == "8" ]] || {
    echo "FAIL: expected exactly eight auth tables after local migration" >&2
    exit 1
  }

  ingest_tables="$(docker exec "$NAME" psql -X -A -t -v ON_ERROR_STOP=1 \
    -U "$DB_USER" -d "$DB_NAME" -c "
SELECT count(*)
FROM information_schema.tables
WHERE table_schema='panadan_ingest' AND table_type='BASE TABLE';
")"
  [[ "$ingest_tables" == "7" ]] || {
    echo "FAIL: existing ingestion tables changed during local migration" >&2
    exit 1
  }
  echo "PASS: additive auth schema applied ONLY in disposable restore (8 auth + 7 ingest tables)"

  if [[ -n "$GRANTS_SQL" ]]; then
    # NOLOGIN test role is only created inside this isolated ephemeral cluster.
    # Do not create or grant roles on the VPS as part of this validation.
    docker exec "$NAME" psql -X -v ON_ERROR_STOP=1 -U "$DB_USER" \
      -d "$DB_NAME" -c \
      "CREATE ROLE panadan_auth_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS" \
      >/dev/null
    docker exec -i "$NAME" psql -X -v ON_ERROR_STOP=1 -1 \
      -U "$DB_USER" -d "$DB_NAME" < "$GRANTS_SQL" >/dev/null

    # Check individual privileges rather than a comma-separated list:
    # has_table_privilege(..., 'SELECT,INSERT') succeeds with ANY listed
    # permission, which would mask partial grants.
    rights="$(docker exec "$NAME" psql -X -A -t -v ON_ERROR_STOP=1 \
      -U "$DB_USER" -d "$DB_NAME" -c "
SELECT
  has_schema_privilege('panadan_auth_runtime','panadan_auth','USAGE'),
  has_schema_privilege('panadan_auth_runtime','panadan_auth','CREATE'),
  has_table_privilege('panadan_auth_runtime','panadan_auth.users','SELECT'),
  has_table_privilege('panadan_auth_runtime','panadan_auth.users','INSERT'),
  has_table_privilege('panadan_auth_runtime','panadan_auth.users','UPDATE'),
  has_table_privilege('panadan_auth_runtime','panadan_auth.users','DELETE'),
  has_table_privilege('panadan_auth_runtime','panadan_auth.users','TRUNCATE'),
  has_table_privilege('panadan_auth_runtime','panadan_auth.users','REFERENCES'),
  has_table_privilege('panadan_auth_runtime','panadan_auth.users','TRIGGER'),
  has_schema_privilege('panadan_auth_runtime','panadan_ingest','USAGE'),
  has_table_privilege('panadan_auth_runtime','panadan_ingest.sources','SELECT'),
  has_database_privilege('panadan_auth_runtime',current_database(),'CREATE');
")"
    [[ "$rights" == "t|f|t|t|t|t|f|f|f|f|f|f" ]] || {
      echo "FAIL: auth runtime privileges are too broad or too narrow" >&2
      exit 1
    }

    # Execute a real SELECT under the restricted role. Never print records.
    docker exec -i "$NAME" psql -X -v ON_ERROR_STOP=1 \
      -U "$DB_USER" -d "$DB_NAME" >/dev/null <<'SQL'
SET ROLE panadan_auth_runtime;
SELECT count(*) FROM panadan_auth.users;
RESET ROLE;
SQL

    echo "PASS: disposable auth runtime role can read auth but cannot access ingestion, DDL or dangerous table actions"
  fi
fi

echo "PASS: local disposable database is destroyed automatically after check"
