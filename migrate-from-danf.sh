#!/usr/bin/env bash
set -euo pipefail
umask 077
source_dir="${1:-$HOME/danf-hub}"
cd "$(dirname "$0")"
if [[ ! -s "$source_dir/.env.db" || ! -s "$source_dir/vpn/client.ovpn" ]]; then
  echo "Expected .env.db and vpn/client.ovpn in $source_dir" >&2
  exit 1
fi
if [[ ! -e .env.db ]]; then cp "$source_dir/.env.db" .env.db; else echo 'Preserved existing .env.db'; fi
mkdir -p vpn
cp -an "$source_dir/vpn/." vpn/
if [[ ! -e .env.app ]]; then
  if [[ -f "$source_dir/.env.app" ]]; then
    sed 's/DANF_/PANADAN_/g' "$source_dir/.env.app" > .env.app
  else
    cp .env.app.example .env.app
  fi
else
  echo 'Preserved existing .env.app'
fi
chmod 600 .env.db .env.app
find vpn -type f -exec chmod 600 {} +
echo "Copied secrets from $source_dir (private). Source unchanged."
echo 'NEXT: nano .env.app; ./panadan.sh up-local  (or ./panadan.sh up when Docker Hub works)'
