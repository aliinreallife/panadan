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

# Distinct name, no shared data, loopback-only ephemeral port, no mounted volumes.
container="panadan-ci-pg-$$"
cleanup() {
  docker rm -f "$container" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

echo "Starting disposable PostgreSQL 18.6 with synthetic test credentials only ..."
docker run --rm -d \
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
docker exec "$container" postgres -V | grep -qE '^postgres \(PostgreSQL\) 18\\.6($| )' || {
  echo "Unexpected PostgreSQL version in disposable test container." >&2
  exit 2
}

export PANADAN_PLATFORM_TEST_DSN="postgresql://panadan_ci:synthetic_ci_password_only@127.0.0.1:${port}/panadan_ci"
export PANADAN_PLATFORM_TEST_ALLOW_RESET=YES
echo "Running synthetic-only ingestion, Odoo adapter and checkpoint tests ..."
uv sync --locked --dev
uv run --locked python -m pytest -q \
  tests/test_platform_ingest.py tests/test_odoo_sync_adapter.py \
  tests/test_sync_readiness_audit.py
echo "Integration test finished. Disposable database will be deleted."
