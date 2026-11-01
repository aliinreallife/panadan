"""Non-mutating safety checks for the offsite PG restore drill wrapper."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_isolated_pg_restore_script_has_valid_bash_syntax():
    result = subprocess.run(
        ["bash", "-n", str(ROOT / "tools/verify-offsite-platform-restore.sh")],
        capture_output=True, text=True, timeout=8,
    )
    assert result.returncode == 0, result.stderr


def test_restore_script_requires_explicit_archive_and_identity():
    script = ROOT / "tools/verify-offsite-platform-restore.sh"
    result = subprocess.run(
        ["bash", str(script)], capture_output=True, text=True, timeout=8,
    )
    assert result.returncode == 2
    assert "Usage:" in result.stderr


def test_restore_script_never_touches_host_services_or_external_network():
    script = (ROOT / "tools/verify-offsite-platform-restore.sh").read_text()
    assert "--network none" in script
    assert "--tmpfs /var/lib/postgresql" in script
    assert "--single-transaction --exit-on-error" in script
    assert "--no-owner --no-acl" in script
    assert "docker rm -f" in script
    assert "ssh " not in script
    assert "docker compose down" not in script
    # Ignore prose comments when asserting Docker flags: our runbook
    # explicitly says that publishing or privileged mode is forbidden.
    commands = "\n".join(
        line for line in script.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    assert "--publish" not in commands
    assert "--privileged" not in commands


def test_offline_auth_schema_rehearsal_is_optional_and_isolated():
    script = (ROOT / "tools/verify-offsite-platform-restore.sh").read_text()
    assert '"--auth-schema"' in script
    assert 'SCHEMA_SQL="$4"' in script
    assert 'psql -X -v ON_ERROR_STOP=1 -1' in script
    assert 'auth_tables" == "8"' in script
    assert 'ingest_tables" == "7"' in script
    assert 'if [[ -n "$SCHEMA_SQL" ]]' in script
    assert '--network none' in script


def test_offline_auth_schema_requires_existing_file(tmp_path):
    script = ROOT / "tools/verify-offsite-platform-restore.sh"
    archive = tmp_path / "test.dump.age"
    identity = tmp_path / "test.identity"
    archive.write_bytes(b"synthetic only")
    identity.write_bytes(b"synthetic only")
    result = subprocess.run(
        ["bash", str(script), str(archive), str(identity),
         "--auth-schema", str(tmp_path / "missing.sql")],
        capture_output=True, text=True, timeout=8,
    )
    assert result.returncode == 2


def test_auth_role_rehearsal_checks_individual_grants_and_denies_ingestion():
    script = (ROOT / "tools/verify-offsite-platform-restore.sh").read_text()
    assert 'GRANTS_SQL="$6"' in script
    assert '"--auth-grants"' in script
    assert "CREATE ROLE panadan_auth_runtime NOLOGIN" in script
    assert "has_table_privilege('panadan_auth_runtime','panadan_auth.users','SELECT')" in script
    assert "has_table_privilege('panadan_auth_runtime','panadan_auth.users','INSERT')" in script
    assert "has_table_privilege('panadan_auth_runtime','panadan_auth.users','UPDATE')" in script
    assert "has_table_privilege('panadan_auth_runtime','panadan_auth.users','DELETE')" in script
    assert "has_table_privilege('panadan_auth_runtime','panadan_auth.users','TRUNCATE')" in script
    assert "has_table_privilege('panadan_auth_runtime','panadan_ingest.sources','SELECT')" in script
    assert "SET ROLE panadan_auth_runtime" in script
    assert '--network none' in script


def test_invalid_auth_grants_path_refused_without_docker(tmp_path):
    script = ROOT / "tools/verify-offsite-platform-restore.sh"
    archive, identity, schema = (
        tmp_path / "backup.age", tmp_path / "identity", tmp_path / "schema.sql"
    )
    for p in (archive, identity, schema):
        p.write_bytes(b"synthetic placeholder")
    result = subprocess.run(
        ["bash", str(script), str(archive), str(identity),
         "--auth-schema", str(schema), "--auth-grants", str(tmp_path / "missing.sql")],
        capture_output=True, text=True, timeout=8,
    )
    assert result.returncode == 2
