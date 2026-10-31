#!/usr/bin/env bash
# Repeatable local quality gate without GitHub Actions minutes or Odoo access.
# --docker runs an EXTRA disposable PostgreSQL 18 synthetic-only test container.
set -euo pipefail
cd "$(dirname "$0")/.."

usage() {
  cat <<'HELP'
Usage: ./panadan.sh verify [--docker] [--assets]
  (default)  Locked Python tests, Node tests and each shell/JS syntax check.
  --docker   Also run disposable synthetic PostgreSQL 18 integration tests.
  --assets   Also install locked npm packages and build frontend assets.
Never loads .env.db, .env.app, vpn/client.ovpn or the persistent platform DB.
No remote Odoo queries and no changes to existing platform DB volumes.
HELP
}
with_docker=false
with_assets=false
for arg in "$@"; do
  case "$arg" in
    --docker) with_docker=true ;;
    --assets) with_assets=true ;;
    help|-h|--help) usage; exit 0 ;;
    *) usage >&2; echo "Unexpected verify argument: $arg" >&2; exit 2 ;;
  esac
done

command -v uv >/dev/null 2>&1 || { echo "uv is required." >&2; exit 2; }
command -v node >/dev/null 2>&1 || { echo "Node.js is required." >&2; exit 2; }
command -v npm >/dev/null 2>&1 || { echo "npm is required." >&2; exit 2; }
[[ -s uv.lock ]] || { echo "Missing uv.lock; refusing to resolve unlocked dependencies." >&2; exit 2; }

# A developer shell may have source credentials set for an unrelated session.
# Remove connection variables for unit tests to prevent unintended access.
echo "[1/5] Locked Python dependencies"
uv sync --locked --dev
echo "[2/5] Offline Python tests (source and platform DB credentials unset)"
env -u PGHOST -u PGPORT -u PGUSER -u PGPASSWORD -u PGDATABASE \
    -u PANADAN_PLATFORM_TEST_DSN -u PANADAN_PLATFORM_TEST_ALLOW_RESET \
    uv run --locked python -m pytest -q
echo "[3/5] Node dashboard tests"
npm test
echo "[4/5] JavaScript syntax checks"
for script in static/*.js; do
  node --check "$script"
done
echo "[5/5] Shell syntax checks (one file per invocation)"
for script in panadan.sh migrate-from-danf.sh start-vpn.sh tools/*.sh; do
  bash -n "$script"
done
if [[ "$with_assets" == true ]]; then
  echo "[optional] Installing and compiling browser assets"
  npm ci --no-audit --no-fund
  npm run build
fi
if [[ "$with_docker" == true ]]; then
  # The test helper creates and destroys its own loopback-only PG18 container.
  # It never uses Compose's persistent panadan-platform database/volume.
  echo "[optional] Disposable PostgreSQL 18 integration"
  bash tools/test-platform-integration.sh
fi
echo "Local verification PASSED."
