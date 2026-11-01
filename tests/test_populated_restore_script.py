"""Offline safety checks for restoring a populated auth PG18 archive.

A real on-disk data restore must be separately exercised with a trusted,
age-encrypted archive and approved identity; these tests never access live data.
"""
import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/verify-populated-platform-restore.sh"


def test_script_has_valid_bash_syntax():
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)], capture_output=True, text=True, timeout=8,
    )
    assert result.returncode == 0, result.stderr


def test_requires_three_local_explicit_files(tmp_path):
    result = subprocess.run(
        ["bash", str(SCRIPT)], capture_output=True, text=True, timeout=8,
    )
    assert result.returncode == 2
    assert "Usage" in result.stderr
    archive, identity, grants = (tmp_path / p for p in ("dump.age", "id.txt", "grants.sql"))
    for p in (archive, identity, grants):
        p.write_text("synthetic placeholder")
    archive.unlink()
    archive.symlink_to(grants)
    result = subprocess.run(
        ["bash", str(SCRIPT), str(archive), str(identity), str(grants)],
        capture_output=True, text=True, timeout=8,
    )
    assert result.returncode == 2
    assert "symlinked" in result.stderr


def test_restoration_is_offline_ephemeral_and_scope_is_panadan_only():
    source = SCRIPT.read_text()
    assert "--network none" in source
    assert "--tmpfs" in source
    assert "--pull never" in source
    assert "--no-owner --no-acl" in source
    assert "--single-transaction --exit-on-error" in source
    assert "docker rm -f" in source
    assert "age --decrypt" in source
    assert "panadan_auth.users" in source
    assert "panadan_ingest.sources" in source
    assert '"18|7|8|0"' in source
    assert '"t|t|t|t|t|t|t|t|t"' in source
    assert "CREATE ROLE panadan_auth_runtime NOLOGIN" in source
    assert '"t|f|t|t|t|t|f|f|f|f|f|f"' in source
    assert "SET ROLE panadan_auth_runtime" in source
    for forbidden in (
        "compose up", "compose down", "docker restart", "docker volume rm",
        "--publish", "-p 5432:", "--privileged", "--mount", "--volume",
        "192.168.3.9", "vpn/client.ovpn", ".env.app", ".env.db",
        "DROP TABLE", "TRUNCATE", "pg_restore --clean",
    ):
        # The script may mention TRUNCATE in SQL privilege names; forbid
        # only actual production/data mutations, not read-only ACL tests.
        if forbidden == "TRUNCATE":
            assert "TRUNCATE panadan_auth" not in source
        else:
            assert forbidden not in source


def test_invalid_tmpfs_limit_exits_before_docker(tmp_path):
    (tmp_path / "bin").mkdir()
    for exe in ("docker", "age", "openssl"):
        path = tmp_path / "bin" / exe
        path.write_text("#!/bin/sh\necho 'UNEXPECTED COMMAND' >&2\nexit 55\n")
        path.chmod(0o700)
    files = [tmp_path / x for x in ("dump.age", "identity", "grants.sql")]
    for f in files:
        f.write_bytes(b"synthetic bytes")
    env = os.environ.copy()
    env["PATH"] = str(tmp_path / "bin") + os.pathsep + env["PATH"]
    for invalid in ("1", "8193", "0", "-5", "noninteger", "01024"):
        env["PANADAN_RESTORE_TMPFS_MIB"] = invalid
        result = subprocess.run(
            ["bash", str(SCRIPT), *(str(x) for x in files)],
            capture_output=True, text=True, timeout=8, env=env,
        )
        assert result.returncode == 2, (invalid, result.stderr)
        assert "128-8192" in result.stderr
        assert "UNEXPECTED COMMAND" not in result.stderr
