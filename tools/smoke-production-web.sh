#!/usr/bin/env bash
# Read-only production release smoke. Never logs in, writes databases,
# deploys/restarts containers, touches Plane, or accesses customer records.
set -euo pipefail
umask 077

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXPECTED=""
fail() {
  printf 'FAIL: production smoke (%s)\n' "$1" >&2
  exit 1
}
usage() {
  echo "Usage: bash tools/smoke-production-web.sh [--expected-image IMAGE]" >&2
  exit 2
}
if [[ $# -gt 0 ]]; then
  [[ $# -eq 2 && "$1" == "--expected-image" ]] || usage
  EXPECTED="$2"
  [[ "$EXPECTED" =~ ^(ghcr\.io/aliinreallife/panadan-web:sha-[a-f0-9]{40}|panadan-web:[a-f0-9]{7,40}|ghcr\.io/aliinreallife/panadan-web@sha256:[a-f0-9]{64})$ ]] ||
    fail "expected web image must be a pinned commit tag or digest"
fi
for exe in docker curl grep mktemp; do
  command -v "$exe" >/dev/null 2>&1 || fail "missing required test executable"
done

# Inspect only narrowly selected metadata; never print Docker's full config,
# environment values, bearer headers, SQLite state or customer information.
[[ "$(docker inspect --format '{{.State.Running}}' panadan-web-1 2>/dev/null)" == true ]] ||
  fail "Panadan web not running"
[[ "$(docker inspect --format '{{.State.Health.Status}}' panadan-vpn-1 2>/dev/null)" == healthy ]] ||
  fail "Panadan VPN not healthy"

if [[ -n "$EXPECTED" ]]; then
  actual="$(docker inspect --format '{{.Config.Image}}' panadan-web-1 2>/dev/null)" ||
    fail "cannot verify running web image"
  [[ "$actual" == "$EXPECTED" ]] ||
    fail "running web image does not match reviewed release"
fi

# This is a Linux kernel route lookup only; it performs no DB connection.
docker exec panadan-vpn-1 ip -4 route get 192.168.3.9 2>/dev/null |
  grep -Eq 'dev tun[[:alnum:]_.-]*' ||
  fail "Odoo source route is not confined to VPN tunnel"

code() {
  curl --silent --show-error --proto '=https' --max-redirs 0 \
    --max-time 12 --output /dev/null --write-out '%{http_code}' "$1" ||
    fail "HTTPS request failed"
}
[[ "$(code https://dan.panafor.com/healthz)" == 200 ]] ||
  fail "Panadan healthz did not return 200"
[[ "$(code https://plane.panafor.com/)" == 200 ]] ||
  fail "Plane homepage did not return 200"
[[ "$(code https://plane.panafor.com/intake.html)" == 200 ]] ||
  fail "Plane original intake path did not return 200"
[[ "$(code https://dan.panafor.com/api/v1/calls)" == 401 ]] ||
  fail "unauthenticated reporting API did not return 401"
[[ "$(code https://dan.panafor.com/mcp/)" == 401 ]] ||
  fail "unauthenticated MCP did not return 401"

HEADERS="$(mktemp -t panadan-login-headers-XXXXXXXX)" ||
  fail "cannot allocate private header temp file"
trap 'rm -f -- "$HEADERS"' EXIT
login_status="$(curl --silent --show-error --proto '=https' --max-redirs 0 \
  --max-time 12 --dump-header "$HEADERS" --output /dev/null \
  --write-out '%{http_code}' https://dan.panafor.com/login)" ||
  fail "login page HTTPS request failed"
[[ "$login_status" == 200 ]] || fail "login page did not return 200"
# Match a single cookie header without displaying cookie value.
grep -Eiq '^set-cookie:[[:space:]]*panadan_login_nonce=.*;[[:space:]]*.*secure([;[:space:]]|$)' "$HEADERS" ||
  fail "login nonce cookie missing Secure attribute"
grep -Eiq '^set-cookie:[[:space:]]*panadan_login_nonce=.*;[[:space:]]*.*httponly([;[:space:]]|$)' "$HEADERS" ||
  fail "login nonce cookie missing HttpOnly attribute"

if [[ -n "${PANADAN_TRUSTED_INTAKE_FILE:-}" ]]; then
  bash "$ROOT/tools/check-plane-intake.sh" verify "$PANADAN_TRUSTED_INTAKE_FILE" >/dev/null ||
    fail "Plane intake bytes differ from trusted original"
  echo "PASS: Original Plane intake byte-for-byte verification"
else
  echo "NOTE: Intake HTTP 200 verified; original content hash not verified (set PANADAN_TRUSTED_INTAKE_FILE)"
fi
echo "PASS: Production web, VPN route, Plane, HTTPS login, API/MCP auth boundaries"
if [[ -n "$EXPECTED" ]]; then
  echo "PASS: Running web container references the reviewed image"
fi
