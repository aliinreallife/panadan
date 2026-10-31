"""Offline regression guards for private role credential generation.

Runs only against a disposable temporary directory. No Docker or DB used.
"""
from pathlib import Path
import re
import os
import shutil
import stat
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ROLES = ROOT / "tools/platform-roles.sh"


def test_role_password_setup_is_private_unique_and_cannot_overwrite(tmp_path):
    tools = tmp_path / "tools"
    tools.mkdir()
    shutil.copyfile(ROLES, tools / "platform-roles.sh")
    script = tools / "platform-roles.sh"
    result = subprocess.run(
        ["bash", str(script), "setup"], cwd=tmp_path,
        check=True, capture_output=True, text=True, timeout=10,
    )
    env = tmp_path / ".env.platform.roles"
    assert env.is_file() and not env.is_symlink()
    assert stat.S_IMODE(env.stat().st_mode) == 0o600
    contents = env.read_text()
    pw = re.findall(r"^PANADAN_(?:WRITER|READER)_PASSWORD=([a-f0-9]{64})$", contents, re.M)
    assert len(pw) == 2 and pw[0] != pw[1]
    assert all(p not in (result.stdout + result.stderr) for p in pw)
    repeat = subprocess.run(
        ["bash", str(script), "setup"], cwd=tmp_path,
        capture_output=True, text=True, timeout=10,
    )
    assert repeat.returncode != 0
    assert "never overwrite" in repeat.stderr
    assert env.read_text() == contents


def test_permission_sql_prevents_raw_report_access_and_requires_disabled_sources():
    migration = (ROOT / "database/permissions/002_platform_runtime_roles.sql").read_text()
    assert "REVOKE ALL ON ALL TABLES IN SCHEMA panadan_ingest" in migration
    assert "GRANT SELECT ON panadan_ingest.sources TO panadan_ingest_writer" in migration
    assert "GRANT SELECT, INSERT, UPDATE ON panadan_ingest.source_records" in migration
    assert "GRANT SELECT ON panadan_ingest.safe_call_facts_v1 TO panadan_report_reader" in migration
    assert "GRANT SELECT ON panadan_ingest.raw_revisions TO panadan_report_reader" not in migration
    assert "REVOKE ALL ON SCHEMA public FROM PUBLIC" in migration
    foundation = (ROOT / "database/migrations/001_multisource_foundation.sql").read_text()
    ingest = (ROOT / "server/platform_ingest.py").read_text()
    assert "SECURITY DEFINER" in foundation
    assert "SET search_path = pg_catalog" in foundation
    assert "REVOKE ALL ON FUNCTION panadan_ingest.lock_source_for_ingest(TEXT) FROM PUBLIC" in foundation
    assert "GRANT EXECUTE ON FUNCTION panadan_ingest.lock_source_for_ingest(TEXT)" in migration
    assert "TO panadan_ingest_writer;" in migration
    assert "lock_source_for_ingest(%s)" in ingest
    assert "FROM panadan_ingest.sources WHERE source_key = %s FOR SHARE" not in ingest
    assert "s.is_deleted = false" in migration
    assert "d.processor_version = 'v1'" in migration


def test_role_provisioning_only_via_explicit_owner_db_stdin():
    sh = ROLES.read_text()
    assert "compose.platform.yaml" in sh
    assert "panadan_owner -d panadan" in sh
    assert "admin_psql --single-transaction" in sh
    assert "PANADAN_WRITER_PASSWORD" in sh and "PANADAN_READER_PASSWORD" in sh
    assert "No Odoo" in sh or "Never connects to remote Odoo" in sh
    assert ".env.db" not in sh and ".env.app" not in sh
    assert "192.168.3.9" not in sh
    assert "docker volume rm" not in sh
    assert "PASSWORD '%s'" in sh
    assert 'cat "$SQL_FILE"' in sh
    assert 'cat "$FOUNDATION_SQL"' in sh
    assert "has_function_privilege" in sh


def test_roles_check_fails_closed_on_privilege_drift(tmp_path):
    """Mock Docker/psql without contacting any real DB or source system."""
    tools = tmp_path / "tools"
    tools.mkdir()
    script = tools / "platform-roles.sh"
    shutil.copyfile(ROLES, script)
    secret = tmp_path / ".env.platform"
    secret.write_text("PANADAN_PLATFORM_DB_PASSWORD=synthetic_only\n")
    secret.chmod(0o600)

    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    docker = fakebin / "docker"
    docker.write_text("""#!/usr/bin/env bash
if [[ "$*" == "compose version" ]]; then exit 0; fi
if [[ "$*" == *"SELECT current_database()"* ]]; then echo panadan; exit 0; fi
if [[ "$*" == *"SHOW server_version_num"* ]]; then echo 180006; exit 0; fi
if [[ "$*" == *"SELECT CASE WHEN"* ]]; then echo "${FAKE_AUDIT_RESULT:-FAIL}"; exit 0; fi
echo 'Unexpected mock invocation' >&2
exit 2
""")
    docker.chmod(0o700)
    env = os.environ.copy()
    env["PATH"] = f"{fakebin}:{env['PATH']}"
    env["FAKE_AUDIT_RESULT"] = "PASS"
    passed = subprocess.run(
        ["bash", str(script), "check"], cwd=tmp_path,
        env=env, capture_output=True, text=True, timeout=10,
    )
    assert passed.returncode == 0, passed.stderr
    assert "verification: PASS" in passed.stdout

    env["FAKE_AUDIT_RESULT"] = "FAIL"
    denied = subprocess.run(
        ["bash", str(script), "check"], cwd=tmp_path,
        env=env, capture_output=True, text=True, timeout=10,
    )
    assert denied.returncode != 0
    assert "verification FAILED" in denied.stderr
