#!/usr/bin/env bash
# Verify a POPULATED Panadan-owned PostgreSQL 18 backup in an offline Docker container.
# No VPN, source Odoo, live Compose service, published ports or persistent volumes.
set -euo pipefail
set +x
umask 077

usage() {
  echo "Usage: bash tools/verify-populated-platform-restore.sh ARCHIVE.dump.age AGE_IDENTITY AUTH_GRANTS.sql" >&2
  exit 2
}
[[ $# -eq 3 ]] || usage
ARCHIVE="$1"; IDENTITY="$2"; GRANTS="$3"
for f in "$ARCHIVE" "$IDENTITY" "$GRANTS"; do
  [[ -f "$f" && -s "$f" && ! -L "$f" ]] || {
    echo "Missing, empty or symlinked restore input" >&2; exit 2;
  }
done
for cmd in docker age openssl; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "Required local command is missing: $cmd" >&2; exit 2;
  }
done

# Operators can explicitly allocate enough temporary RAM on the trusted
# RESTORE computer; the script never falls back to an unencrypted disk volume.
MEM_MIB="$(printenv PANADAN_RESTORE_TMPFS_MIB || true)"
MEM_MIB="$MEM_MIB"
[[ -n "$MEM_MIB" ]] || MEM_MIB=1024
[[ "$MEM_MIB" =~ ^[1-9][0-9]*$ ]] &&
  (( MEM_MIB >= 128 && MEM_MIB <= 8192 )) || {
    echo "PANADAN_RESTORE_TMPFS_MIB must be 128-8192" >&2; exit 2;
  }

IMAGE="postgres:18.6-alpine3.24@sha256:10a5c69a83035ab5239f5620d708520e8b28f5aa1f2b20143e6024532edadfb5"
docker info >/dev/null 2>&1 || { echo "Docker daemon unavailable" >&2; exit 1; }
docker image inspect "$IMAGE" >/dev/null 2>&1 || {
  echo "Pinned PostgreSQL 18.6 image must be downloaded separately" >&2; exit 1;
}

NAME="panadan-populated-restore-$(openssl rand -hex 12)"
STARTED=0
cleanup() {
  if [[ "$STARTED" -eq 1 ]]; then
    docker rm -f "$NAME" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

docker run -d --rm --pull never --name "$NAME" \
  --network none \
  --tmpfs "/var/lib/postgresql:rw,nosuid,size=$MEM_MIB""m" \
  -e POSTGRES_USER=panadan_owner \
  -e POSTGRES_DB=panadan \
  -e "POSTGRES_PASSWORD=$(openssl rand -hex 24)" \
  "$IMAGE" >/dev/null
STARTED=1
READY=0
for _ in {1..40}; do
  if docker exec "$NAME" pg_isready -q -U panadan_owner -d panadan >/dev/null 2>&1; then
    READY=1; break
  fi
  sleep 1
done
[[ "$READY" -eq 1 ]] || { echo "Disposable PostgreSQL did not become ready" >&2; exit 1; }

# Decryption streams directly to a RESTORE-ONLY container.
age --decrypt -i "$IDENTITY" "$ARCHIVE" |
  docker exec -i "$NAME" pg_restore --single-transaction --exit-on-error \
    --no-owner --no-acl -U panadan_owner -d panadan >/dev/null || {
      echo "Disposable archive restore or decryption failed" >&2; exit 1;
    }

# Counts only, no account names, passwords, token digests or transcript contents.
SCHEMA="$(docker exec "$NAME" psql -X -At -v ON_ERROR_STOP=1 \
  -U panadan_owner -d panadan -c "
SELECT current_setting('server_version_num')::integer / 10000,
       (SELECT count(*) FROM information_schema.tables
        WHERE table_schema='panadan_ingest' AND table_type='BASE TABLE'),
       (SELECT count(*) FROM information_schema.tables
        WHERE table_schema='panadan_auth' AND table_type='BASE TABLE'),
       (SELECT count(*) FROM pg_catalog.pg_constraint
        WHERE connamespace='panadan_auth'::regnamespace AND NOT convalidated);
" 2>/dev/null)" || {
    echo "Cannot inspect restored database schemas" >&2; exit 1;
  }
[[ "$SCHEMA" == "18|7|8|0" ]] || {
  echo "Unexpected PG18 auth/ingest schema or unvalidated constraints" >&2; exit 1;
}

CHECK="$(docker exec "$NAME" psql -X -At -v ON_ERROR_STOP=1 \
  -U panadan_owner -d panadan -c "
SELECT (SELECT count(*) FROM panadan_auth.users) >= 1,
       to_regclass('panadan_auth.sessions') IS NOT NULL,
       to_regclass('panadan_auth.access_tokens') IS NOT NULL,
       to_regclass('panadan_auth.oauth_identities') IS NOT NULL,
       to_regclass('panadan_auth.transcript_access_audit') IS NOT NULL,
       to_regclass('panadan_auth.activity_events') IS NOT NULL,
       to_regclass('panadan_auth.login_throttle') IS NOT NULL,
       to_regclass('panadan_auth.operator_directory') IS NOT NULL,
       to_regclass('panadan_ingest.sources') IS NOT NULL;
" 2>/dev/null)" || {
    echo "Cannot query restored auth schema" >&2; exit 1;
  }
[[ "$CHECK" == "t|t|t|t|t|t|t|t|t" ]] || {
  echo "Populated auth backup lacks expected data or tables" >&2; exit 1;
}

# pg_dump excludes cluster-global roles. Reconstruct a temporary NOLOGIN role
# only in this disposable database and apply the explicitly supplied grants.
docker exec "$NAME" psql -X -v ON_ERROR_STOP=1 -U panadan_owner -d panadan \
  -c "CREATE ROLE panadan_auth_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS" \
  >/dev/null
docker exec -i "$NAME" psql -X -v ON_ERROR_STOP=1 -1 \
  -U panadan_owner -d panadan < "$GRANTS" >/dev/null

RIGHTS="$(docker exec "$NAME" psql -X -At -v ON_ERROR_STOP=1 \
  -U panadan_owner -d panadan -c "
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
" 2>/dev/null)" || {
  echo "Cannot inspect restricted auth role" >&2; exit 1;
}
[[ "$RIGHTS" == "t|f|t|t|t|t|f|f|f|f|f|f" ]] || {
  echo "Restored role permissions too broad or too narrow" >&2; exit 1;
}

# Prove the role can read the restored accounts without printing any rows.
docker exec -i "$NAME" psql -X -v ON_ERROR_STOP=1 -U panadan_owner \
  -d panadan >/dev/null <<'SQL'
SET ROLE panadan_auth_runtime;
SELECT count(*) FROM panadan_auth.users;
SELECT count(*) FROM panadan_auth.sessions;
RESET ROLE;
SQL

echo "PASS: Offline PG18 restore has 8 auth tables, 7 ingestion tables, populated users, valid constraints, and restricted auth permissions"
echo "NOTE: Application login, independent key escrow, and disaster recovery remain unverified"
