#!/usr/bin/env bash
# Read-only aggregate incremental synchronization diagnostics.
# No customer payloads, names, phones, transcripts, credentials or source IDs.
set -euo pipefail
set +x
umask 077

[[ "${1:-}" == status && $# -eq 1 ]] || {
  echo "Usage: $0 status" >&2
  exit 2
}
STAGE=panadan-mirror-staging-pg18
sudo -v
[[ "$(sudo -n docker port "$STAGE" 5432/tcp)" == 127.0.0.1:55432 ]] || {
  echo "FAIL: Stage is not isolated loopback" >&2
  exit 2
}
echo "=== Staging Odoo mirror incremental health ==="
sudo -n docker exec "$STAGE" psql -X -Atq -v ON_ERROR_STOP=1 \
  -U panadan_stage_owner -d panadan_ci -c "
SELECT 'records=' || count(*)
FROM panadan_ingest.source_records
WHERE source_key='odoo_calls_full_v1';

SELECT 'revisions=' || count(*)
FROM panadan_ingest.raw_revisions
WHERE source_key='odoo_calls_full_v1';

SELECT 'source_enabled=' || enabled::text
FROM panadan_ingest.sources
WHERE source_key='odoo_calls_full_v1';

SELECT 'full_reconciliation_checkpoint=' || cursor::text
FROM panadan_ingest.sync_checkpoints
WHERE source_key='odoo_calls_full_v1'
  AND stream='view_reconciliation_v1';

SELECT 'incremental_checkpoint=' || COALESCE(cursor::text, 'not_started')
FROM panadan_ingest.sync_checkpoints
WHERE source_key='odoo_calls_full_v1'
  AND stream='created_or_modified_v1';

SELECT 'incremental_pages=' || count(*)
FROM panadan_ingest.sync_runs
WHERE source_key='odoo_calls_full_v1'
  AND stream='created_or_modified_v1';

SELECT 'last_incremental_commit=' ||
       COALESCE(max(finished_at)::text, 'never')
FROM panadan_ingest.sync_runs
WHERE source_key='odoo_calls_full_v1'
  AND stream='created_or_modified_v1';
"
echo "=== Scheduled service state ==="
systemctl is-enabled panadan-mirror-incremental.timer || true
systemctl is-active panadan-mirror-incremental.timer || true
echo "=== Available disk ==="
df -h /var/lib/panadan-mirror-staging
