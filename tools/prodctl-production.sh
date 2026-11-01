#!/usr/bin/env bash
# Production controller for the hardened Panadan ingress. Run with bash;
# never use ./panadan.sh up/down on this installation.
set -euo pipefail
umask 077

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INGRESS="${PANADAN_INGRESS_DIR:-$ROOT/data/ingress}"
PLANE="${PANADAN_PLANE_DIR:-$(dirname "$ROOT")/plane-selfhost/plane-app}"
ORIGIN="${PANADAN_EXPECTED_ORIGIN:-https://dan.panafor.com}"

require_files() {
  local f
  for f in "$ROOT/.env.app" "$ROOT/.env.db" "$ROOT/compose.prod.yaml" \
      "$INGRESS/compose.panadan.yaml" "$INGRESS/compose.web.release.yaml" \
      "$INGRESS/compose.web.https.yaml" "$INGRESS/compose.plane.yaml" \
      "$INGRESS/Caddyfile" "$PLANE/docker-compose.yaml" "$PLANE/plane.env"; do
    if [[ ! -f "$f" ]]; then
      printf 'MISSING required private production file: %s\n' "$f" >&2
      return 1
    fi
  done
}

panadan_compose() (
  cd "$ROOT"
  docker compose --env-file .env.app \
    -f compose.prod.yaml \
    -f "$INGRESS/compose.panadan.yaml" \
    -f "$INGRESS/compose.web.release.yaml" \
    -f "$INGRESS/compose.web.https.yaml" "$@"
)
plane_compose() (
  cd "$PLANE"
  docker compose --env-file plane.env \
    -f docker-compose.yaml -f "$INGRESS/compose.plane.yaml" "$@"
)

preflight() {
  require_files
  panadan_compose config --quiet
  plane_compose config --quiet
  # Parse the effective merged config without printing .env values or credentials.
  panadan_compose config --format json | \
    PANADAN_EXPECTED_ORIGIN="$ORIGIN" python3 -c '
import json, os, sys
c=json.load(sys.stdin)
web=c["services"]["web"]
env=web.get("environment") or {}
assert str(env.get("PANADAN_COOKIE_SECURE","")).lower()=="true", "insecure cookies"
assert env.get("PANADAN_PUBLIC_ORIGIN")==os.environ["PANADAN_EXPECTED_ORIGIN"], "origin mismatch"
assert web.get("network_mode")=="service:vpn", "unexpected web network"
image=web.get("image","")
assert image and ":" in image and not image.endswith((":main",":latest")), "mutable or missing web image tag"
print("PASS: Hardened Panadan config (cookie/origin/network/image)")
'
  plane_compose config --format json | python3 -c '
import json,sys
c=json.load(sys.stdin)
p=c["services"]["proxy"]
assert "edge" in p.get("networks", {}), "private edge network missing"
vols=p.get("volumes",[])
mounts={v.get("target"):v for v in vols}
for target in ("/data","/config","/etc/caddy/Caddyfile"):
    assert target in mounts, f"proxy mount missing: {target}"
assert mounts["/etc/caddy/Caddyfile"]["type"]=="bind", "Caddyfile must be bind-mounted"
assert mounts["/etc/caddy/Caddyfile"].get("read_only") is True, "Caddyfile must be read-only"
print("PASS: Plane proxy ingress / Caddy TLS volumes")
'
}

check_endpoints() {
  curl --fail --silent --show-error --max-time 10 "$ORIGIN/healthz" >/dev/null
  curl --fail --silent --show-error --max-time 10 https://plane.panafor.com/intake.html >/dev/null
  echo "PASS: HTTPS Panadan and Plane intake"
}

cmd="${1:-help}"
case "$cmd" in
  check)
    preflight
    check_endpoints
    ;;
  status)
    require_files
    panadan_compose ps
    plane_compose ps proxy
    docker ps --filter name=panadan-edge-gateway
    ;;
  deploy-web|deploy-proxy)
    if [[ "${2:-}" != "--apply" || "$#" -ne 2 ]]; then
      echo "REFUSED: $cmd requires an explicit --apply (and a reviewed maintenance window for proxy)" >&2
      exit 64
    fi
    preflight
    if [[ "$cmd" == "deploy-web" ]]; then
      panadan_compose --dry-run up -d --no-deps --no-build --pull never web
      panadan_compose up -d --no-deps --no-build --pull never web
    else
      echo "NOTICE: proxy recreation may briefly interrupt Plane and Panadan HTTPS." >&2
      plane_compose --dry-run up -d --no-deps --no-build --pull never proxy
      plane_compose up -d --no-deps --no-build --pull never proxy
    fi
    check_endpoints
    ;;
  *)
    echo "Usage: bash tools/prodctl-production.sh {check|status|deploy-web --apply|deploy-proxy --apply}"
    exit 2
    ;;
esac
