#!/usr/bin/env bash
# Guarded production controller: no bare up/down on hardened Plane/Panadan.
set -euo pipefail
umask 077

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INGRESS="${PANADAN_INGRESS_DIR:-$ROOT/data/ingress}"
PLANE="${PANADAN_PLANE_DIR:-$(dirname "$ROOT")/plane-selfhost/plane-app}"
ORIGIN="https://dan.panafor.com"
AUTH_NETWORK_READY=0

fail() {
  echo "REFUSED: production safety preflight failed ($1)" >&2
  exit 64
}

require_files() {
  local f
  for f in "$ROOT/.env.app" "$ROOT/.env.db" "$ROOT/compose.prod.yaml" \
      "$INGRESS/compose.panadan.yaml" "$INGRESS/compose.web.release.yaml" \
      "$INGRESS/compose.web.https.yaml" "$INGRESS/compose.gateway.yaml" \
      "$INGRESS/compose.plane.yaml" "$INGRESS/Caddyfile" \
      "$INGRESS/nginx.conf" "$PLANE/docker-compose.yaml" "$PLANE/plane.env" \
      "$ROOT/deploy/compose.auth-network.panadan.yaml" \
      "$ROOT/tools/validate_production_compose.py" \
      "$ROOT/tools/check_auth_db_network.py" \
      "$ROOT/tools/check-plane-intake.sh" \
      "$ROOT/tools/smoke-production-web.sh"; do
    [[ -f "$f" && ! -L "$f" ]] || fail "MISSING reviewed deployment component"
  done
  command -v python3 >/dev/null 2>&1 || fail "Python 3 required"
  command -v docker >/dev/null 2>&1 || fail "Docker required"
}

# The private auth network may have been manually attached while running.
# When present, future VPN-related Compose renders MUST retain it.
inspect_auth_network() {
  local names
  names="$(docker network ls --format '{{.Name}}' 2>/dev/null)" ||
    fail "cannot inspect existing Docker networks"
  if grep -Fxq panadan-auth-db <<< "$names"; then
    docker network inspect panadan-auth-db 2>/dev/null |
      python3 "$ROOT/tools/validate_production_compose.py" auth-network >/dev/null ||
        fail "owned auth bridge topology mismatch"
    python3 "$ROOT/tools/check_auth_db_network.py" --stage after >/dev/null ||
      fail "owned PostgreSQL auth alias or source VPN route mismatch"
    AUTH_NETWORK_READY=1
  else
    AUTH_NETWORK_READY=0
  fi
}

panadan_compose() (
  cd "$ROOT"
  local -a files=(
    -f compose.prod.yaml
    -f "$INGRESS/compose.panadan.yaml"
    -f "$INGRESS/compose.web.release.yaml"
    -f "$INGRESS/compose.web.https.yaml"
  )
  if [[ "$AUTH_NETWORK_READY" == 1 ]]; then
    files+=(-f "$ROOT/deploy/compose.auth-network.panadan.yaml")
  fi
  docker compose --env-file .env.app "${files[@]}" "$@"
)
plane_compose() (
  cd "$PLANE"
  docker compose --env-file plane.env \
    -f docker-compose.yaml -f "$INGRESS/compose.plane.yaml" "$@"
)
gateway_compose() (
  cd "$ROOT"
  docker compose --env-file .env.app \
    -f "$INGRESS/compose.gateway.yaml" "$@"
)

# Plan/check only inspect config, networks, and HTTPS endpoints. Compose
# output can include secrets and must NEVER be printed to a shared log.
preflight() {
  require_files
  inspect_auth_network
  docker network inspect panadan-edge panadan-ingress 2>/dev/null |
    python3 "$ROOT/tools/validate_production_compose.py" private-networks >/dev/null ||
      fail "private Plane/Caddy/Panadan bridge topology mismatch"
  panadan_compose config --quiet >/dev/null 2>&1 ||
    fail "invalid Panadan overlay stack"
  plane_compose config --quiet >/dev/null 2>&1 ||
    fail "invalid Plane overlay stack"
  gateway_compose config --quiet >/dev/null 2>&1 ||
    fail "invalid gateway Compose project"

  local -a auth_flag=()
  if [[ "$AUTH_NETWORK_READY" == 1 ]]; then
    auth_flag=(--auth)
  fi
  panadan_compose config --format json 2>/dev/null |
    python3 "$ROOT/tools/validate_production_compose.py" panadan "${auth_flag[@]}" --explain-safe ||
      fail "Panadan production service invariants"
  plane_compose config --format json 2>/dev/null |
    python3 "$ROOT/tools/validate_production_compose.py" plane ||
      fail "Plane proxy volume/network invariants"
  gateway_compose config --format json 2>/dev/null |
    python3 "$ROOT/tools/validate_production_compose.py" gateway ||
      fail "gateway must remain unpublished and isolated"
  python3 "$ROOT/tools/validate_production_compose.py" caddy \
    < "$INGRESS/Caddyfile" ||
      fail "both Plane and Panadan HTTPS site blocks required"
  echo "PASS: Read-only hardened production plan; no containers or networks changed"
}

check_endpoints() {
  curl --fail --silent --show-error --max-time 10 "$ORIGIN/healthz" >/dev/null ||
    fail "Panadan HTTPS health failed"
  curl --fail --silent --show-error --max-time 10 https://plane.panafor.com/ >/dev/null ||
    fail "Plane HTTPS health failed"
  curl --fail --silent --show-error --max-time 10 https://plane.panafor.com/intake.html >/dev/null ||
    fail "Plane intake HTTPS failed"
  echo "PASS: Panadan, Plane, and intake HTTPS reachable"
}

# A web-only deployment may use only a reviewed, already downloaded,
# commit-pinned web image. Never let a movable :main tag or private override
# silently substitute another build. Only the *image name* is emitted here,
# never the full effective Compose JSON with interpolated secrets.
require_release_image() {
  local expected="$1" configured
  [[ "$expected" =~ ^(ghcr\.io/aliinreallife/panadan-web:sha-[a-f0-9]{40}|panadan-web:[a-f0-9]{7,40}|ghcr\.io/aliinreallife/panadan-web@sha256:[a-f0-9]{64})$ ]] ||
    fail "web release needs a commit-pinned image (not main or latest)"
  configured="$(panadan_compose config --format json 2>/dev/null |
    python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["services"]["web"]["image"])')" ||
    fail "cannot resolve current effective web image"
  [[ "$configured" == "$expected" ]] ||
    fail "effective web image differs from reviewed release; inspect private Compose override"
  docker image inspect "$expected" >/dev/null 2>&1 ||
    fail "reviewed image is not already pulled locally"
}

# Before any proxy recreate require operator's independently saved original
# intake HTML and separate original Caddy rollback configuration.
verify_plane_recovery_material() {
  local original="${PANADAN_TRUSTED_INTAKE_FILE:-}"
  local rollback="${PANADAN_CADDY_ROLLBACK_FILE:-$INGRESS/rollback/Caddyfile.live}"
  [[ -n "$original" && -s "$original" && -f "$original" && ! -L "$original" ]] ||
    fail "original Plane intake file required before proxy recreation"
  [[ -s "$rollback" && -f "$rollback" && ! -L "$rollback" ]] ||
    fail "original Caddy rollback copy required before proxy recreation"
  bash "$ROOT/tools/check-plane-intake.sh" verify "$original" >/dev/null ||
    fail "Plane intake differs from original or is unavailable"
}

cmd="${1:-help}"
case "$cmd" in
  plan)
    [[ $# -eq 1 ]] || fail "plan accepts no extra arguments"
    preflight
    ;;
  check)
    [[ $# -eq 1 ]] || fail "check accepts no extra arguments"
    preflight
    check_endpoints
    ;;
  status)
    [[ $# -eq 1 ]] || fail "status accepts no extra arguments"
    require_files
    inspect_auth_network
    panadan_compose ps
    plane_compose ps proxy
    gateway_compose ps gateway
    ;;
  deploy-web)
    [[ $# -eq 5 && "${2:-}" == "--apply" && "${3:-}" == "--expect-image" && "${5:-}" == "--ack-restored-backup" ]] ||
      fail "deploy-web requires --apply --expect-image PINNED_IMAGE --ack-restored-backup"
    preflight
    require_release_image "$4"
    # Baseline must be healthy before modifying the single web service.
    check_endpoints
    bash "$ROOT/tools/smoke-production-web.sh" >/dev/null ||
      fail "baseline smoke failed; no changes made"
    echo "NOTICE: recreating Panadan web only, preserving Plane, VPN and owned PostgreSQL" >&2
    panadan_compose --dry-run up -d --no-deps --no-build --pull never web
    panadan_compose up -d --no-deps --no-build --pull never web
    check_endpoints
    bash "$ROOT/tools/smoke-production-web.sh" --expected-image "$4" ||
      fail "post-release smoke failed; stop and use reviewed previous image rollback"
    ;;
  deploy-proxy)
    [[ $# -eq 3 && "${2:-}" == "--apply" && "${3:-}" == "--ack-plane-impact" ]] ||
      fail "deploy-proxy requires --apply --ack-plane-impact"
    preflight
    verify_plane_recovery_material
    echo "NOTICE: shared proxy recreation affects Plane and Panadan HTTPS" >&2
    plane_compose --dry-run up -d --no-deps --no-build --pull never proxy
    plane_compose up -d --no-deps --no-build --pull never proxy
    check_endpoints
    verify_plane_recovery_material
    ;;
  *)
    echo "Usage: bash tools/prodctl-production.sh {plan|check|status|deploy-web --apply --expect-image PINNED_IMAGE --ack-restored-backup|deploy-proxy --apply --ack-plane-impact}"
    exit 2
    ;;
esac
