#!/usr/bin/env bash
# Operator-only ONE-page staging bridge. Sensitive JSON passes in a pipe ONLY.
# Never redirect stdout of the exporter or enable bash xtrace (-x).
# Does not alter VPN, proxy, production Web, or Docker networks.
set -euo pipefail
set +x

if [[ "${1:-}" != "first-page" ]]; then
  echo "Usage: $0 first-page --ack-source-contract --ack-retention --ack-copy --ack-sensitive-data" >&2
  exit 2
fi
shift
for required in --ack-source-contract --ack-retention --ack-copy --ack-sensitive-data; do
  seen=0
  for arg in "$@"; do [[ "$arg" != "$required" ]] || seen=$((seen+1)); done
  if (( seen != 1 )); then
    echo "Staging import requires each explicit approval exactly once" >&2
    exit 2
  fi
done
if (( $# != 4 )); then
  echo "Unexpected staging import options" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_ENV="$HOME/panadan/.env.db"
CONF="$HOME/.config/panadan-mirror-staging/writer.dsn"
DB=panadan-mirror-staging-pg18

[[ "$(stat -c %a "$CONF")" == "600" ]] || {
  echo "Staging credential file must have mode 600" >&2
  exit 2
}
[[ -s "$SOURCE_ENV" ]] || {
  echo "Existing source Odoo configuration missing" >&2
  exit 2
}
command -v sudo >/dev/null
sudo -v

PORT="$(sudo docker port "$DB" 5432/tcp)"
[[ "$PORT" == "127.0.0.1:55432" ]] || {
  echo "Staging localhost port is not correctly bound" >&2
  exit 2
}
[[ "$(sudo docker inspect panadan-vpn-1 --format '{{.State.Health.Status}}')" == "healthy" ]] || {
  echo "Existing Odoo VPN is not healthy" >&2
  exit 2
}

# An owner enables this source only AFTER staging approval. Writer has no
# source-registry UPDATE rights, so the importer cannot silently opt in.
IDENTITY="$(sudo docker exec "$DB" psql -X -U panadan_stage_owner -d panadan_ci -Atqc "
SELECT current_database() || '|' || current_setting('server_version_num') || '|' ||
  COALESCE((SELECT enabled::text FROM panadan_ingest.sources
            WHERE source_key='odoo_calls_full_v1'),'missing');
")"
[[ "$IDENTITY" == "panadan_ci|180006|true" ]] || {
  echo "Staging source is not explicitly enabled on PG18" >&2
  exit 2
}
RECORDS="$(sudo docker exec "$DB" psql -X -U panadan_stage_owner -d panadan_ci -Atqc "
SELECT count(*) FROM panadan_ingest.source_records
WHERE source_key='odoo_calls_full_v1';
")"
[[ "$RECORDS" == "0" ]] || {
  echo "This first-page command refuses an existing import; use a reviewed continuation" >&2
  exit 2
}

IMAGE="$(sudo docker inspect panadan-web-1 --format '{{.Image}}')"
sudo docker image inspect "$IMAGE" >/dev/null
echo "Starting a bounded Odoo -> staging transfer (max 25 source rows) ..." >&2

# No intermediate file: VPN-side Python exports one canonically digested JSON
# envelope to STDOUT; host-network writer accepts it on STDIN. Neither binary
# should echo source JSON or write payloads to application/CLI logs.
sudo docker run --rm \
  --name panadan-mirror-vpn-page-export \
  --pull=never --log-driver=none \
  --network container:panadan-vpn-1 \
  --read-only --cap-drop=ALL --security-opt no-new-privileges \
  --user "$(id -u):$(id -g)" --memory=256m --pids-limit=128 \
  --env-file "$SOURCE_ENV" \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/opt/panadan \
  -v "$ROOT:/opt/panadan:ro" \
  -w /opt/panadan --entrypoint python "$IMAGE" \
  -m server.odoo_mirror_transfer export --batch-size 25 --after-id 0 \
| sudo docker run --rm -i \
  --name panadan-mirror-host-page-import \
  --pull=never --log-driver=none --network host \
  --read-only --cap-drop=ALL --security-opt no-new-privileges \
  --user "$(id -u):$(id -g)" --memory=256m --pids-limit=128 \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/opt/panadan \
  -e PANADAN_FULL_MIRROR_TARGET_MODE=isolated-staging \
  -e PANADAN_FULL_MIRROR_STAGING_ISOLATED=YES \
  -e PANADAN_FULL_MIRROR_STAGING_WRITER_DSN_FILE=/run/secrets/writer.dsn \
  -v "$ROOT:/opt/panadan:ro" \
  -v "$CONF:/run/secrets/writer.dsn:ro" \
  -w /opt/panadan --entrypoint python "$IMAGE" \
  -m server.odoo_mirror_transfer import --batch-size 25 \
  --ack-source-contract --ack-retention --ack-copy --ack-sensitive-data

echo "=== Staging row/revision counts, without customer values ==="
sudo docker exec "$DB" psql -X -U panadan_stage_owner -d panadan_ci -Atqc "
SELECT 'records=' || count(*) FROM panadan_ingest.source_records
WHERE source_key='odoo_calls_full_v1';
SELECT 'revisions=' || count(*) FROM panadan_ingest.raw_revisions
WHERE source_key='odoo_calls_full_v1';
"
echo "ONE-PAGE STAGING IMPORT COMPLETED"
