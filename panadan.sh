#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
cmd="${1:-help}"
port="${PANADAN_HTTP_PORT:-8508}"
if [[ -f .env.app ]]; then
  value="$(sed -n 's/^PANADAN_HTTP_PORT=//p' .env.app | tail -n 1 | tr -d '\r')"
  [[ "$value" =~ ^[0-9]+$ ]] && port="$value"
fi
check_config() {
  [[ -s .env.db && -s .env.app && -s vpn/client.ovpn ]] || {
    echo 'Missing .env.db / .env.app / vpn/client.ovpn; run ./migrate-from-danf.sh ~/danf-hub' >&2
    exit 1
  }
  grep -Eq '^PANADAN_ADMIN_PASSWORD=.{14,}$' .env.app || {
    echo 'Set PANADAN_ADMIN_PASSWORD to 14+ characters in .env.app first.' >&2
    exit 1
  }
}
compose() { docker compose --env-file .env.app "$@"; }
case "$cmd" in
  up)
    check_config
    compose up -d --build
    compose ps
    echo "Dashboard: http://localhost:${port}/login"
    ;;
  up-local)
    check_config
    for base in danf-v2-vpn:latest danf-v2-python:latest; do
      docker image inspect "$base" >/dev/null 2>&1 || {
        echo "Required local image missing: $base" >&2
        echo 'This offline build uses locally cached images from DANF v2. Restore/rebuild those first, or repair Docker Hub access.' >&2
        exit 1
      }
    done
    if ! compgen -G 'wheelhouse/*.whl' >/dev/null; then
      echo 'Preparing Python wheels through WSL, not Docker Hub ...'
      python3 -m pip download --only-binary=:all: -r requirements.txt -d wheelhouse || {
        echo 'Python wheel download failed. Fix WSL pip access or copy a complete wheelhouse/ here.' >&2
        exit 1
      }
    fi
    echo 'Building web image from the local DANF v2 Python image (no Docker Hub base pull) ...'
    docker build --network=none -f Dockerfile.web.local -t panadan-web:local .
    docker compose -f compose.local.yaml --env-file .env.app up -d --no-build
    docker compose -f compose.local.yaml --env-file .env.app ps
    echo "Dashboard: http://localhost:${port}/login"
    ;;
  wheels)
    mkdir -p wheelhouse
    python3 -m pip download --only-binary=:all: -r requirements.txt -d wheelhouse
    ;;
  down) compose down ;;
  status) compose ps ;;
  logs) compose logs --tail=80 -f web ;;
  vpn-logs) compose logs --tail=80 vpn ;;
  test)
    compose exec -T vpn sh -c 'ip -4 route get 192.168.3.9 && pg_isready -h 192.168.3.9 -p 5432'
    echo 'For API check use: curl -fsS http://localhost:'"$port"'/healthz'
    ;;
  diagnose)
    echo 'Docker context:'; docker context show
    echo 'Local image availability:'
    for i in danf-v2-python:latest danf-v2-vpn:latest python:3.12-slim debian:bookworm-slim; do
      if docker image inspect "$i" >/dev/null 2>&1; then echo "  OK $i"; else echo "  MISSING $i"; fi
    done
    echo 'WSL Docker Hub DNS:'
    getent ahostsv4 registry-1.docker.io | head -3 || true
    ;;
  *) echo 'Usage: ./panadan.sh {up|up-local|wheels|down|status|logs|vpn-logs|test|diagnose}';;
esac
