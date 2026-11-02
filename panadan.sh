#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
cmd="${1:-help}"; shift || true
umask 077
# Dispatch the platform DB CLI before even reading source/app configuration.
if [[ "$cmd" == "platform-db" ]]; then
  exec bash tools/platform-db.sh "$@"
fi
# Source-controlled, guarded owned-PostgreSQL auth and network bootstrap.
# Dispatch before loading Odoo credentials or legacy production compose.
if [[ "$cmd" == "owned-pg" ]]; then
  exec bash tools/setup-owned-auth-pg.sh "$@"
fi
# This VPS has private HTTPS overlays and a fragile shared Plane Caddy proxy.
# Refuse the unmodified production compose, which would silently drop them.
if [[ "$cmd" == "up" || "$cmd" == "down" ]]; then
  for marker in data/ingress/compose.panadan.yaml \
                data/ingress/compose.web.release.yaml \
                data/ingress/compose.web.https.yaml; do
    if [[ -e "$marker" ]]; then
      echo "REFUSED: hardened production overlays detected; bare up/down is unsafe." >&2
      echo "Use the reviewed production deployment controller tools/prodctl-production.sh with all private overlays; review VPS-local prodctl.sh before deployment." >&2
      exit 64
    fi
  done
  # File-presence checks alone can be bypassed if operator-local overlays
  # are moved or lost while the hardened Docker topology is still running.
  # Read Docker network NAMES only; do not inspect secret environment values,
  # modify networks, or touch the source VPN.
  command -v docker >/dev/null 2>&1 || {
    echo 'REFUSED: Cannot verify Docker networks for production up/down.' >&2
    exit 64
  }
  existing_networks="$(docker network ls --format '{{.Name}}' 2>/dev/null)" || {
    echo 'REFUSED: Docker network inspection failed; bare up/down is unsafe.' >&2
    exit 64
  }
  for protected in panadan-edge panadan-ingress panadan-auth-db; do
    if grep -Fxq -- "$protected" <<< "$existing_networks"; then
      echo 'REFUSED: Hardened Panadan/Plane network exists; bare up/down would omit private overlays.' >&2
      echo 'Use the reviewed production controller and all required private Compose overlays.' >&2
      exit 64
    fi
  done
fi
# Local quality verification never even reads existing source credentials.
if [[ "$cmd" == "verify" ]]; then
  exec bash tools/verify-local.sh "$@"
fi
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
# The normal production Compose omits hardened ingress/HTTPS overrides.
# Never silently revert an already deployed public installation.
refuse_unhardened_production() {
  if [[ -f data/ingress/compose.panadan.yaml ||
        -f data/ingress/compose.web.https.yaml ||
        -f data/ingress/compose.web.release.yaml ]]; then
    echo 'REFUSED: this installation has hardened production overlays.' >&2
    echo 'Use the reviewed tools/prodctl-production.sh workflow instead of panadan.sh up/down.' >&2
    return 64
  fi
}
compose_dev() { docker compose --env-file .env.app -f compose.dev.yaml "$@"; }
compose_prod() { docker compose --env-file .env.app -f compose.prod.yaml "$@"; }
case "$cmd" in
  setup)
    require_uv
    lock_if_needed
    uv sync --locked --dev --python 3.13
    echo 'uv environment ready; uv.lock is the source of truth.'
    if command -v npm >/dev/null 2>&1; then
      [[ -s package-lock.json ]] || { echo 'Missing package-lock.json: pull the committed lockfile first.' >&2; exit 1; }
      npm ci --no-audit --no-fund && npm run build
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
  relay-recreate)
    # Recreate only the relay; Git updates can invalidate single-file WSL bind
    # mounts. The VPN service should already be running.
    check_config
    compose_dev up -d --no-deps --force-recreate pgrelay
    ;;
  vpn-down) compose_dev down ;;
  up)
    refuse_unhardened_production
    check_config
    # Production: prebuilt images from GHCR; requires registry access for first pull.
    compose_prod up -d --no-build
    compose_prod ps
    echo "Dashboard: http://localhost:$port/login"
    ;;
  down) refuse_unhardened_production; compose_prod down ;;
  status) compose_dev ps || true; compose_prod ps || true ;;
  logs) compose_dev logs --tail=80 pgrelay vpn ;;
  prod-logs) compose_prod logs --tail=80 web vpn ;;
  test)
    # Offline unit tests work without Odoo/VPN secrets in a detached worktree.
    require_uv; lock_if_needed
    uv sync --locked --dev
    uv run --locked python -m pytest -q "$@"
    ;;
  audit-db)
    # Does not modify PostgreSQL permissions or read customer records.
    check_config; require_uv; lock_if_needed
    compose_dev up -d --no-build
    export PGHOST=127.0.0.1
    export PGPORT="$proxy_port"
    uv run --locked --env-file .env.db --env-file .env.app \
      python -m server.readonly_audit
    ;;
  audit-fields)
    # Uses only read-only source-view aggregates; never prints customer records.
    check_config; require_uv; lock_if_needed
    compose_dev up -d --no-build
    export PGHOST=127.0.0.1
    export PGPORT="$proxy_port"
    uv run --locked --env-file .env.db --env-file .env.app \
      python -m server.data_dictionary_audit "$@"
    ;;
  audit-semantics)
    # Compare clock/phone hypotheses using bounded read-only aggregates.
    check_config; require_uv; lock_if_needed
    compose_dev up -d --no-build
    export PGHOST=127.0.0.1
    export PGPORT="$proxy_port"
    uv run --locked --env-file .env.db --env-file .env.app \
      python -m server.source_semantics_audit "$@"
    ;;
  audit-sync)
    # Read-only catalog metadata, <=300 ID samples and optional EXPLAIN (never ANALYZE).
    check_config; require_uv; lock_if_needed
    compose_dev up -d --no-build
    export PGHOST=127.0.0.1
    export PGPORT="$proxy_port"
    uv run --locked --env-file .env.db --env-file .env.app \
      python -m server.sync_readiness_audit "$@"
    ;;
  diagnose-db)
    # Distinguish a healthy tunnel from an actually reachable PostgreSQL server.
    # Never emit DB credentials or customer reporting rows.
    check_config; require_uv; lock_if_needed
    compose_dev up -d --no-build
    echo "[VPN route to PostgreSQL]"
    compose_dev exec -T vpn ip -4 route get 192.168.3.9 || true
    echo "[VPN -> PostgreSQL server: TCP readiness only; no login]"
    compose_dev exec -T vpn pg_isready -h 192.168.3.9 -p 5432 -t 5 || true
    export PGHOST=127.0.0.1
    export PGPORT="$proxy_port"
    uv run --locked --env-file .env.db --env-file .env.app \
      python -m server.connection_diagnostics
    ;;
  check)
    check_config
    echo 'VPN route:'
    compose_dev exec -T vpn ip -4 route get 192.168.3.9
    echo 'Local proxy (TCP reachability only):'
    uv run --no-project --python 3.13 python -c 'import socket,sys; c=socket.create_connection(("127.0.0.1",int(sys.argv[1])),timeout=5); c.close(); print("local relay reachable")' "$proxy_port"
    ;;
  diagnose)
    echo "uv: $(command -v uv || echo missing)"
    echo 'Docker:'; docker context show
    for image in danf-v2-vpn:latest danf-v2-python:latest; do
      docker image inspect "$image" >/dev/null 2>&1 && echo "OK $image" || echo "MISSING $image"
    done
    ;;
  *)
    echo 'Usage: ./panadan.sh {setup|platform-db|owned-pg|dev|vpn-up|vpn-down|up|down|status|logs|prod-logs|test|verify|check|audit-db|audit-fields|audit-semantics|audit-sync|diagnose-db|relay-recreate|diagnose}'
    echo 'dev = native WSL uv FastAPI + Docker-isolated VPN; up = GHCR production images'
    ;;
esac
