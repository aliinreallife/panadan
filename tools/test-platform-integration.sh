#!/usr/bin/env bash
# Local, fully synthetic PostgreSQL integration test. Never uses Odoo or .env.
# Run explicitly: bash tools/test-platform-integration.sh
set -euo pipefail
cd "$(dirname "$0")/.."

command -v docker >/dev/null 2>&1 || {
  echo "Docker is required for the disposable PostgreSQL integration test." >&2
  exit 2
}
command -v uv >/dev/null 2>&1 || {
  echo "uv is required for the locked Python test environment." >&2
  exit 2
}

# Distinct name, loopback-only ephemeral port, no persistent volume.
# Do NOT use docker run --rm here: an intentional database restart is part
# of this test, and --rm may delete the stopped container.
container="panadan-ci-pg-${BASHPID}"
archive=""
cleanup() {
  [[ -z "$archive" ]] || rm -f -- "$archive"
  # Remove the synthetic container AND any anonymous volume it created.
  # Never use this command on the separately named panadan-platform volume.
  docker rm -fv "$container" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

echo "Starting disposable PostgreSQL 18.6 with synthetic test credentials only ..."
docker run -d \
  --name "$container" \
  -e POSTGRES_DB=panadan_ci \
  -e POSTGRES_USER=panadan_ci \
  -e POSTGRES_PASSWORD=synthetic_ci_password_only \
  -p 127.0.0.1::5432 \
  postgres:18.6-alpine3.24@sha256:10a5c69a83035ab5239f5620d708520e8b28f5aa1f2b20143e6024532edadfb5 >/dev/null

# docker port is displayed as 127.0.0.1:HOST_PORT on Docker Desktop/WSL.
endpoint="$(docker port "$container" 5432/tcp | grep '^127.0.0.1:' | head -1 || true)"
[[ "$endpoint" =~ ^127\.0\.0\.1:([0-9]+)$ ]] || {
  echo "Docker did not publish a loopback PostgreSQL port." >&2
  exit 2
}
port="${BASH_REMATCH[1]}"

ready=false
for _ in {1..35}; do
  if docker exec "$container" pg_isready -U panadan_ci -d panadan_ci >/dev/null 2>&1; then
    ready=true
    break
  fi
  sleep 1
done
[[ "$ready" == true ]] || {
  echo "Disposable PostgreSQL did not become ready." >&2
  exit 2
}

# Check the binary too: failures should never silently fall back to PG17.
docker exec "$container" postgres -V | grep -qE '^postgres \(PostgreSQL\) 18\.6($| )' || {
  echo "Unexpected PostgreSQL version in disposable test container." >&2
  exit 2
}

export PANADAN_PLATFORM_TEST_DSN="postgresql://panadan_ci:synthetic_ci_password_only@127.0.0.1:${port}/panadan_ci"
export PANADAN_PLATFORM_TEST_ALLOW_RESET=YES
echo "Running synthetic-only ingestion and checkpoint tests ..."
uv sync --locked --dev
tests=(tests/test_platform_ingest.py tests/test_sync_readiness_audit.py tests/test_platform_scram_auth.py)
# The Odoo adapter is in a separate feature PR; include it when present.
if [[ -f tests/test_odoo_sync_adapter.py ]]; then
  tests+=(tests/test_odoo_sync_adapter.py)
fi
uv run --locked python -m pytest -q "${tests[@]}"
echo "Testing idempotent schema initialization and custom-format backup/restore ..."
for _ in 1 2; do
  docker exec -i "$container" psql -X -v ON_ERROR_STOP=1 -1 \
    -U panadan_ci -d panadan_ci \
    < database/migrations/001_multisource_foundation.sql >/dev/null
done
docker exec "$container" psql -X -v ON_ERROR_STOP=1 -U panadan_ci \
  -d panadan_ci -c \
  "INSERT INTO panadan_ingest.sources(source_key,kind,label) VALUES ('smoke_fixture','manual','Synthetic smoke fixture')" \
  >/dev/null
# Real PostgreSQL restart must preserve the schema and the synthetic test row.
docker restart "$container" >/dev/null
ready=false
for _ in {1..35}; do
  if docker exec "$container" pg_isready -U panadan_ci -d panadan_ci >/dev/null 2>&1; then
    ready=true
    break
  fi
  sleep 1
done
[[ "$ready" == true ]] || {
  echo "PostgreSQL did not come back after restart." >&2
  exit 2
}
persisted="$(docker exec "$container" psql -X -At -U panadan_ci -d panadan_ci \
  -c "SELECT source_key FROM panadan_ingest.sources WHERE source_key = 'smoke_fixture' AND enabled = FALSE")"
[[ "$persisted" == "smoke_fixture" ]] || {
  echo "Synthetic metadata was not retained across PostgreSQL restart." >&2
  exit 2
}
archive="$(mktemp)"
docker exec "$container" pg_dump -U panadan_ci -d panadan_ci -Fc > "$archive"
[[ -s "$archive" ]] || { echo "Synthetic backup is empty." >&2; exit 2; }
docker exec -i "$container" pg_restore --list < "$archive" >/dev/null
docker exec "$container" createdb -U panadan_ci panadan_restore_ci
docker exec -i "$container" pg_restore --no-owner --no-acl \
  -U panadan_ci -d panadan_restore_ci < "$archive"
restored="$(docker exec "$container" psql -X -At -U panadan_ci -d panadan_restore_ci \
  -c "SELECT source_key FROM panadan_ingest.sources WHERE source_key = 'smoke_fixture' AND enabled = FALSE")"
[[ "$restored" == "smoke_fixture" ]] || {
  echo "Restored backup did not preserve synthetic metadata." >&2
  exit 2
}
echo "PG18 migration, restart persistence, backup and restore verified using synthetic data."
echo "Integration test finished. Disposable database will be deleted."
