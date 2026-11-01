#!/usr/bin/env bash
# Read-only HTTPS fingerprint / exact-content check for Plane's custom intake page.
# Never accesses Plane Docker, its volumes, or the shared reverse proxy.
set -euo pipefail
umask 077

URL="https://plane.panafor.com/intake.html"
fail() { echo "PLANE INTAKE CHECK FAILED: $*" >&2; exit 1; }
usage() {
  echo "Usage: bash tools/check-plane-intake.sh {fingerprint|verify /path/to/trusted-original-intake.html}" >&2
  exit 2
}
[[ $# -ge 1 ]] || usage
case "$1" in
  fingerprint) [[ $# -eq 1 ]] || usage ;;
  verify)
    [[ $# -eq 2 ]] || usage
    [[ -s "$2" && -f "$2" && ! -L "$2" ]] ||
      fail "Trusted original intake HTML file is missing, empty, or symlinked"
    ;;
  *) usage ;;
esac

for exe in curl sha256sum mktemp cut; do
  command -v "$exe" >/dev/null 2>&1 || fail "Missing command: $exe"
done

TEMP="$(mktemp -t panadan-plane-intake-XXXXXXXX)" || fail "Cannot create private temporary file"
trap 'rm -f -- "$TEMP"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Do not follow redirects: a login page or other redirect is not intake.html.
# Only this fixed public HTTPS URL is fetched. No credentials/cookies are sent.
HTTP_CODE="$(curl --fail --silent --show-error --proto '=https' --max-time 15 \
  --max-redirs 0 --output "$TEMP" --write-out '%{http_code}' "$URL")" ||
  fail "Cannot fetch Plane intake over HTTPS"
[[ "$HTTP_CODE" == "200" && -s "$TEMP" ]] ||
  fail "Plane intake did not return a nonempty HTTP 200 response"
CURRENT="$(sha256sum "$TEMP" | cut -d' ' -f1)"
if [[ "$1" == "fingerprint" ]]; then
  echo "Plane intake current SHA-256: $CURRENT"
  echo "NOTE: A fingerprint is NOT a backup of the original HTML file"
  exit 0
fi

REFERENCE="$(sha256sum "$2" | cut -d' ' -f1)"
[[ "$CURRENT" == "$REFERENCE" ]] ||
  fail "Public intake content differs from the trusted original backup (SHA-256 mismatch)"
echo "PASS: Plane /intake.html returns exactly the trusted original HTML bytes"
