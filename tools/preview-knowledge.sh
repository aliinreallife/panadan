#!/usr/bin/env bash
# Explicit local synthetic preview. Never loads .env or connects to source DB.
set -euo pipefail
cd "$(dirname "$0")/.."
for binary in docker uv npm; do
  command -v "$binary" >/dev/null || { echo "$binary is required" >&2; exit 2; }
done
uv sync --locked --dev
npm ci --no-audit --no-fund
npm run build
scratch="$(mktemp -d)"
container=""
cleanup() {
  if [[ -n "$container" ]]; then docker rm -fv "$container" >/dev/null 2>&1 || true; fi
  rm -rf -- "$scratch"
}
trap cleanup EXIT
trap 'exit 130' INT TERM
container="$(docker run -d --name "panadan-knowledge-preview-${BASHPID}" \
  -e POSTGRES_DB=panadan_ci -e POSTGRES_USER=panadan_ci \
  -e POSTGRES_PASSWORD=synthetic_ci_password_only \
  -p 127.0.0.1::5432 \
  postgres:18.6-alpine3.24@sha256:10a5c69a83035ab5239f5620d708520e8b28f5aa1f2b20143e6024532edadfb5)"
endpoint="$(docker port "$container" 5432/tcp | grep '^127.0.0.1:' | head -1 || true)"
[[ "$endpoint" =~ ^127\.0\.0\.1:([0-9]+)$ ]] || { echo "Loopback port unavailable" >&2; exit 2; }
port="${BASH_REMATCH[1]}"
ready=false
for _ in {1..35}; do
  if docker exec "$container" pg_isready -U panadan_ci -d panadan_ci >/dev/null 2>&1; then ready=true; break; fi
  sleep 1
done
[[ "$ready" == true ]] || { echo "Disposable database not ready" >&2; exit 2; }
# No inherited auth, OAuth, source, production or libpq environment.
env -i PATH="$PATH" HOME="$HOME" PYTHONUTF8=1 PANADAN_KNOWLEDGE_PREVIEW_BOOTSTRAP=YES \
  "$(command -v uv)" run --locked python -m tools.knowledge_preview "$port" "$scratch"
