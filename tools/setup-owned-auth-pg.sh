#!/usr/bin/env bash
# One entry point for owned Panadan PostgreSQL auth infrastructure.
# Never deploys/recreates Plane, VPN or Panadan application containers.
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 tools/setup_owned_auth_pg.py "$@"
