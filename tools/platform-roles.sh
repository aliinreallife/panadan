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
  local values
  values="$(admin_psql -A -t -c 'SELECT current_database(); SHOW server_version_num;')"
  [[ "$values" == "$(printf 'panadan\n' )"18????" ]] && return 0
  # Explicit validation without interpolating arbitrary database identifiers.
  [[ "$(printf '%s\n' "$values" | head -1)" == "panadan" ]] ||
    die "Wrong target database: expected panadan."
  [[ "$(printf '%s\n' "$values" | tail -1)" =~ ^18[0-9]{4}$ ]] ||
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
  [[ "$writer" =~ ^[[:xdigit:]]{64}$ && "$reader" =~ ^[[:xdigit:]]{64}$ && "$writer" != "$reader" ]] ||
    die "Each role password must be distinct, exactly 64 hexadecimal characters."
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
    need_runtime
    check_permissions "$PLATFORM_FILE"
    check_roles_file
    confirm_target
    [[ -s "$SQL_FILE" ]] || die "Missing reviewed database permission migration."
    # Feed role passwords only on stdin to local psql. Never use -v for
    # secrets, echo the SQL, enable shell tracing, or embed them in Docker argv.
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
      printf "ALTER ROLE panadan_ingest_writer LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD '%s';\n" "$writer"
      printf "ALTER ROLE panadan_report_reader LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD '%s';\n" "$reader"
      cat "$SQL_FILE"
    } | admin_psql --single-transaction >/dev/null
    echo "Restricted ingest-writer and safe-facts reader roles provisioned."
    echo "No Odoo connection, source activation, or dashboard cutover occurred."
    ;;
  check)
    need_runtime
    check_permissions "$PLATFORM_FILE"
    confirm_target
    admin_psql -A -t -c "
SELECT 'writer_can_read_source_registry=' || has_table_privilege('panadan_ingest_writer','panadan_ingest.sources','SELECT');
SELECT 'writer_can_enable_sources=' || has_table_privilege('panadan_ingest_writer','panadan_ingest.sources','UPDATE');
SELECT 'reader_can_read_safe_view=' || has_table_privilege('panadan_report_reader','panadan_ingest.safe_call_facts_v1','SELECT');
SELECT 'reader_can_read_raw=' || has_table_privilege('panadan_report_reader','panadan_ingest.raw_revisions','SELECT');
SELECT 'reader_can_write_raw=' || has_table_privilege('panadan_report_reader','panadan_ingest.raw_revisions','INSERT');
SELECT 'reader_can_create_schema=' || has_database_privilege('panadan_report_reader','panadan','CREATE');"
    ;;
  help|-h|--help)
    echo "Usage: ./panadan.sh platform-db roles-{setup|apply|check}"
    echo "setup stores ignored private role credentials; apply explicitly grants minimum access."
    ;;
  *)
    die "Unknown role operation."
    ;;
esac
