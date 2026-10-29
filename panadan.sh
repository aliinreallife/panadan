#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
cmd="${1:-help}"; shift || true
umask 077
if [[ -f .env.app ]]; then
  port="$(sed -n 's/^PANADAN_HTTP_PORT=//p' .env.app | tail -1 | tr -d '\r')"
  proxy_port="$(sed -n 's/^PANADAN_PG_PROXY_PORT=//p' .env.app | tail -1 | tr -d '\r')"
fi
port="${port:-8508}"
proxy_port="${proxy_port:-15432}"
check_config() {
  [[ -s .env.db && -s .env.app && -s vpn/client.ovpn ]] || {
    echo 'Missing .env.db, .env.app or vpn/client.ovpn. See README.md.' >&2
    exit 1
  }
  grep -Eq '^PANADAN_ADMIN_PASSWORD=.{14,}$' .env.app || {
    echo 'PANADAN_ADMIN_PASSWORD must be 14+ characters in .env.app.' >&2; exit 1;
  }
}
require_uv() {
  command -v uv >/dev/null 2>&1 || { echo 'uv is required. Install uv on WSL; no system pip is needed.' >&2; exit 1; }
}
lock_if_needed() {
  if [[ ! -s uv.lock ]]; then
    echo 'First setup: resolving dependencies with uv and creating uv.lock ...'
    uv lock
    echo 'Commit uv.lock before deploying or publishing the repository.'
  fi
}
compose_dev() { docker compose --env-file .env.app -f compose.dev.yaml "$@"; }
compose_prod() { docker compose --env-file .env.app -f compose.prod.yaml "$@"; }
case "$cmd" in
  setup)
    require_uv
    lock_if_needed
    uv sync --locked --dev
    echo 'uv environment ready; uv.lock is the source of truth.'
    if command -v npm >/dev/null 2>&1; then
      npm install --no-audit --no-fund && npm run build
    else
      echo 'Node 20+ is needed to build Doran and Vazirmatn assets.' >&2
      exit 1
    fi
    ;;
  dev)
    check_config; require_uv; lock_if_needed
    for image in danf-v2-vpn:latest danf-v2-python:latest; do
      docker image inspect "$image" >/dev/null 2>&1 || { echo "Local image $image unavailable. See README." >&2; exit 1; }
    done
    [[ -s static/vendor/panadan-bundle.js && -s static/vendor/panadan-bundle.css ]] || { echo 'Run ./panadan.sh setup to generate dashboard assets.' >&2; exit 1; }
    compose_dev up -d --no-build
    echo 'Using uv-managed Python on WSL; DB via isolated Docker VPN proxy.'
    export PGHOST=127.0.0.1
    export PGPORT="$proxy_port"
    export PANADAN_AUTH_DB="$(pwd)/data/auth.sqlite"
    export PANADAN_COOKIE_SECURE=false
    uv run --locked --env-file .env.db --env-file .env.app \
      uvicorn server.main:app --host 127.0.0.1 --port "$port" --no-proxy-headers "$@"
    ;;
  vpn-up) check_config; compose_dev up -d --no-build; compose_dev ps ;;
  vpn-down) compose_dev down ;;
  up)
    check_config
    # Production: prebuilt images from GHCR; requires registry access for first pull.
    compose_prod up -d --no-build
    compose_prod ps
    echo "Dashboard: http://localhost:$port/login"
    ;;
  down) compose_prod down ;;
  status) compose_dev ps || true; compose_prod ps || true ;;
  logs) compose_dev logs --tail=80 pgrelay vpn ;;
  prod-logs) compose_prod logs --tail=80 web vpn ;;
  test)
    require_uv; check_config; lock_if_needed
    uv sync --locked --dev
    uv run --locked python -m pytest -q
    ;;
  check)
    check_config
    echo 'VPN route:'
    compose_dev exec -T vpn ip -4 route get 192.168.3.9
    echo 'Local proxy (TCP reachability only):'
    uv run --no-project --python 3.12 python -c 'import socket,sys; c=socket.create_connection(("127.0.0.1",int(sys.argv[1])),timeout=5); c.close(); print("local relay reachable")' "$proxy_port"
    ;;
  diagnose)
    echo "uv: $(command -v uv || echo missing)"
    echo 'Docker:'; docker context show
    for image in danf-v2-vpn:latest danf-v2-python:latest; do
      docker image inspect "$image" >/dev/null 2>&1 && echo "OK $image" || echo "MISSING $image"
    done
    ;;
  *)
    echo 'Usage: ./panadan.sh {setup|dev|vpn-up|vpn-down|up|down|status|logs|prod-logs|test|check|diagnose}'
    echo 'dev = native WSL uv FastAPI + Docker-isolated VPN; up = GHCR production images'
    ;;
esac
