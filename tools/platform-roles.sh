#!/usr/bin/env bash
# Explicit least-privilege role provisioning for Panadan's OWN PostgreSQL 18.
# Never connects to remote Odoo. No password is displayed or passed as argv.
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."

ROLES_FILE=.env.platform.roles
PLATFORM_FILE=.env.platform
COMPOSE=compose.platform.yaml
SQL_FILE=database/permissions/002_platform_runtime_roles.sql
FOUNDATION_SQL=database/migrations/001_multisource_foundation.sql

die() { echo "Panadan roles: $*" >&2; exit 1; }
need_runtime() {
  command -v docker >/dev/null || die "Docker required."
  docker compose version >/dev/null || die "Docker Compose v2 required."
  [[ -s "$PLATFORM_FILE" ]] || die "Initialize the Panadan-owned DB first."
}
check_permissions() {
  local file="$1" mode
  [[ -s "$file" && ! -L "$file" ]] || die "Missing or symlinked role credentials: $file"
  mode="$(stat -c '%a' "$file")"
  (( (8#$mode & 8#077) == 0 )) || die "Credentials must have permissions 600: $file"
}
compose() {
  env -u PANADAN_PLATFORM_DB_PASSWORD docker compose \
    --env-file "$PLATFORM_FILE" -f "$COMPOSE" "$@"
}
admin_psql() {
  compose exec -T db psql -X -v ON_ERROR_STOP=1 -U panadan_owner -d panadan "$@"
}
confirm_target() {
  local dbname major
  dbname="$(admin_psql -A -t -c 'SELECT current_database()')"
  major="$(admin_psql -A -t -c 'SHOW server_version_num')"
  # Separate psql invocations avoid ambiguous multiple-result formatting.
  [[ "$dbname" == "panadan" ]] ||
    die "Wrong target database: expected panadan."
  [[ "$major" =~ ^18[0-9]{4}$ ]] ||
    die "Wrong PostgreSQL major: expected 18."
}
check_roles_file() {
  check_permissions "$ROLES_FILE"
  [[ "$(grep -Ec '^PANADAN_WRITER_PASSWORD=' "$ROLES_FILE")" == "1" ]] ||
    die "Expected exactly one writer password."
  [[ "$(grep -Ec '^PANADAN_READER_PASSWORD=' "$ROLES_FILE")" == "1" ]] ||
    die "Expected exactly one reader password."
  writer="$(sed -n 's/^PANADAN_WRITER_PASSWORD=//p' "$ROLES_FILE")"
  reader="$(sed -n 's/^PANADAN_READER_PASSWORD=//p' "$ROLES_FILE")"
  [[ "$writer" =~ ^[0-9a-f]{64}$ && "$reader" =~ ^[0-9a-f]{64}$ && "$writer" != "$reader" ]] ||
    die "Each role password must be distinct, exactly 64 hexadecimal characters."
}
audit_roles() {
  # Treat any unexpected grant as an error, not merely a printed warning.
  # Checking permissions by explicit role keeps the audit independent of
  # the superuser owner session used to provision these accounts.
  local status
  status="$(admin_psql -A -t -c "
SELECT CASE WHEN
  (SELECT count(*) = 2 AND bool_and(
      NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole
      AND NOT rolreplication AND NOT rolbypassrls)
     FROM pg_roles
     WHERE rolname IN ('panadan_ingest_writer', 'panadan_report_reader'))
  AND has_database_privilege('panadan_ingest_writer',current_database(),'CONNECT')
  AND has_database_privilege('panadan_report_reader',current_database(),'CONNECT')
  AND NOT has_database_privilege('panadan_ingest_writer',current_database(),'CREATE,TEMP')
  AND NOT has_database_privilege('panadan_report_reader',current_database(),'CREATE,TEMP')
  AND has_schema_privilege('panadan_ingest_writer','panadan_ingest','USAGE')
  AND has_schema_privilege('panadan_report_reader','panadan_ingest','USAGE')
  AND NOT has_schema_privilege('panadan_ingest_writer','panadan_ingest','CREATE')
  AND NOT has_schema_privilege('panadan_report_reader','panadan_ingest','CREATE')
  AND NOT has_schema_privilege('panadan_report_reader','public','CREATE')
  AND has_table_privilege('panadan_ingest_writer','panadan_ingest.sources','SELECT')
  AND has_function_privilege('panadan_ingest_writer','panadan_ingest.lock_source_for_ingest(text)','EXECUTE')
  AND NOT has_function_privilege('panadan_report_reader','panadan_ingest.lock_source_for_ingest(text)','EXECUTE')
  AND NOT has_table_privilege('panadan_ingest_writer','panadan_ingest.sources','INSERT,UPDATE,DELETE,TRUNCATE')
  AND NOT has_table_privilege('panadan_ingest_writer','panadan_ingest.safe_call_facts_v1','SELECT')
  AND has_table_privilege('panadan_report_reader','panadan_ingest.safe_call_facts_v1','SELECT')
  AND NOT has_table_privilege('panadan_report_reader','panadan_ingest.sources','SELECT,INSERT,UPDATE,DELETE')
  AND NOT has_table_privilege('panadan_report_reader','panadan_ingest.source_records','SELECT,INSERT,UPDATE,DELETE')
  AND NOT has_table_privilege('panadan_report_reader','panadan_ingest.raw_revisions','SELECT,INSERT,UPDATE,DELETE')
  AND NOT has_table_privilege('panadan_report_reader','panadan_ingest.processing_jobs','SELECT,INSERT,UPDATE,DELETE')
  AND NOT has_table_privilege('panadan_report_reader','panadan_ingest.derived_facts','SELECT,INSERT,UPDATE,DELETE')
  AND NOT has_table_privilege('panadan_report_reader','panadan_ingest.sync_checkpoints','SELECT,INSERT,UPDATE,DELETE')
  AND NOT has_table_privilege('panadan_report_reader','panadan_ingest.sync_runs','SELECT,INSERT,UPDATE,DELETE')
THEN 'PASS' ELSE 'FAIL' END;")" || die "Could not audit PostgreSQL roles."
  [[ "$status" == "PASS" ]] ||
    die "Role privilege verification FAILED: unexpected grants or missing restrictions."
  echo "Role privilege verification: PASS (writer restricted, reader safe-view-only)."
}
case "${1:-help}" in
  setup)
    [[ ! -e "$ROLES_FILE" && ! -L "$ROLES_FILE" ]] ||
      die "$ROLES_FILE exists; never overwrite stored role passwords."
    command -v openssl >/dev/null || die "openssl required."
    tmp="$(mktemp ".env.platform.roles.tmp.XXXXXXXX")"
    trap 'rm -f -- "$tmp"' EXIT
    printf 'PANADAN_WRITER_PASSWORD=%s\nPANADAN_READER_PASSWORD=%s\n' \
      "$(openssl rand -hex 32)" "$(openssl rand -hex 32)" > "$tmp"
    chmod 600 "$tmp"
    ln -- "$tmp" "$ROLES_FILE" || die "Could not create role credentials without overwrite."
    rm -f -- "$tmp"
    echo "Generated two private, distinct login secrets in $ROLES_FILE (mode 600)."
    echo "No PostgreSQL permissions or connections changed."
    ;;
  apply)
    set +x
    need_runtime
    check_permissions "$PLATFORM_FILE"
    check_roles_file
    confirm_target
    [[ -s "$SQL_FILE" && -s "$FOUNDATION_SQL" ]] || die "Missing reviewed schema or permission migration."
    # Schema must already exist: provisioning should never silently bootstrap a DB.
    schema_count="$(admin_psql -A -t -c "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'panadan_ingest' AND table_type = 'BASE TABLE' AND table_name IN ('sources','source_records','raw_revisions','processing_jobs','derived_facts','sync_checkpoints','sync_runs')")"
    [[ "$schema_count" == "7" ]] || die "Initialize the 7-table platform schema before provisioning roles."
    command -v python3 >/dev/null 2>&1 || die "python3 is required for local SCRAM derivation."
    [[ -s tools/scram_secret.py ]] || die "Missing local SCRAM derivation helper."
    logging="$(admin_psql -A -t -c 'SHOW log_statement;' 2>/dev/null)" ||
      die "Cannot verify PostgreSQL SQL statement logging policy."
    [[ "$logging" == "none" ]] ||
      die "Refusing role provisioning while PostgreSQL statement logging is enabled."
    writer_verifier="$(printf '%s' "$writer" | python3 tools/scram_secret.py)" ||
      die "Failed to derive writer SCRAM verifier."
    reader_verifier="$(printf '%s' "$reader" | python3 tools/scram_secret.py)" ||
      die "Failed to derive reader SCRAM verifier."
    [[ "$writer_verifier" == SCRAM-SHA-256\$* && "$reader_verifier" == SCRAM-SHA-256\$* ]] ||
      die "Invalid derived SCRAM verifier."
    # Feed only locally derived SCRAM verifiers on stdin to local psql.
    # Never send plaintext credentials in SQL, shell arguments or logs.
    {
      cat <<'ROLE_SQL'
DO $create$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'panadan_ingest_writer') THEN
    CREATE ROLE panadan_ingest_writer LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'panadan_report_reader') THEN
    CREATE ROLE panadan_report_reader LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  END IF;
END
$create$;
ROLE_SQL
      printf "ALTER ROLE panadan_ingest_writer LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD '%s';\n" "$writer_verifier"
      printf "ALTER ROLE panadan_report_reader LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD '%s';\n" "$reader_verifier"
      # Additive foundation migration installs the lock helper on existing DBs.
      cat "$FOUNDATION_SQL"
      cat "$SQL_FILE"
    } | admin_psql --single-transaction >/dev/null 2>&1
    unset writer reader writer_verifier reader_verifier
    audit_roles
    echo "Restricted ingest-writer and safe-facts reader roles provisioned."
    echo "No Odoo connection, source activation, or dashboard cutover occurred."
    ;;
  check)
    need_runtime
    check_permissions "$PLATFORM_FILE"
    confirm_target
    audit_roles
    ;;
  help|-h|--help)
    echo "Usage: ./panadan.sh platform-db roles-{setup|apply|check}"
    echo "setup stores ignored private role credentials; apply explicitly grants minimum access."
    ;;
  *)
    die "Unknown role operation."
    ;;
esac
