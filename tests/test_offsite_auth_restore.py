"""Offline age-encrypted SQLite auth restore tool: synthetic-only, no live network."""
from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/verify-offsite-auth-restore.sh"


def _fixture(tmp_path: Path, *, missing_table=False, empty_users=False):
    source = tmp_path / "synthetic-auth.sqlite"
    with sqlite3.connect(source) as db:
        db.executescript("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY, username TEXT NOT NULL,
                password_hash TEXT NOT NULL, role TEXT NOT NULL,
                is_active INTEGER NOT NULL);
            CREATE TABLE sessions (
                token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL,
                csrf TEXT NOT NULL, expires_at INTEGER NOT NULL);
            CREATE TABLE access_tokens (
                id INTEGER PRIMARY KEY, token_hash TEXT NOT NULL,
                scope TEXT NOT NULL, owner_id INTEGER);
            CREATE TABLE activity_events (
                id INTEGER PRIMARY KEY, action TEXT);
        """)
        if not empty_users:
            db.execute(
                "INSERT INTO users VALUES(1,?,?,?,1)",
                ("NEVER_LOG_PRIVATE_USERNAME", "abcd"*10 + ":" + "ef"*32, "admin"),
            )
        db.execute("INSERT INTO activity_events VALUES(1,'synthetic')")
        if missing_table:
            db.execute("DROP TABLE access_tokens")
    archive = tmp_path / "test.sqlite.age"
    archive.write_bytes(source.read_bytes())
    key = tmp_path / "synthetic-offhost-age-identity"
    key.write_text("ONLY SYNTHETIC TEST DATA")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    age = bindir / "age"
    age.write_text("""#!/usr/bin/env python3
import shutil,sys
args=sys.argv[1:]
if args[:1] != ["-d"] or "-i" not in args or "-o" not in args:
    sys.exit(3)
shutil.copyfile(args[-1],args[args.index("-o")+1])
""")
    age.chmod(0o755)
    return archive, key, bindir


def _run(tmp_path: Path, *, missing_table=False, empty_users=False):
    archive, key, bindir = _fixture(
        tmp_path, missing_table=missing_table, empty_users=empty_users
    )
    env = os.environ.copy()
    env["PATH"] = str(bindir) + os.pathsep + env["PATH"]
    return subprocess.run(
        ["bash", str(SCRIPT), str(archive), str(key)],
        env=env, text=True, capture_output=True, timeout=15,
    )


def test_offsite_auth_restore_has_valid_shell_syntax():
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)], capture_output=True, text=True, timeout=8
    )
    assert result.returncode == 0, result.stderr


def test_offsite_auth_restore_requires_archive_and_independent_key(tmp_path):
    result = subprocess.run(
        ["bash", str(SCRIPT)], capture_output=True, text=True, timeout=8
    )
    assert result.returncode == 2
    assert "Usage:" in result.stderr
    archive, key, _ = _fixture(tmp_path)
    key.unlink()
    result = subprocess.run(
        ["bash", str(SCRIPT), str(archive), str(key)],
        capture_output=True, text=True, timeout=8,
    )
    assert result.returncode != 0
    assert "FAIL" in result.stderr


def test_offsite_auth_restore_roundtrips_real_synthetic_sqlite(tmp_path):
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "PASS: Offline age decryption" in result.stdout
    assert "PASS: Disposable SQLite restore" in result.stdout
    assert "NEVER_LOG_PRIVATE_USERNAME" not in result.stdout + result.stderr
    assert "ONLY SYNTHETIC TEST DATA" not in result.stdout + result.stderr


def test_offsite_auth_restore_rejects_missing_auth_table(tmp_path):
    result = _run(tmp_path, missing_table=True)
    assert result.returncode != 0
    assert "FAIL: SQLite data/schema/account" in result.stderr
    assert "NEVER_LOG_PRIVATE_USERNAME" not in result.stdout + result.stderr


def test_offsite_auth_restore_rejects_backup_without_users(tmp_path):
    result = _run(tmp_path, empty_users=True)
    assert result.returncode != 0
    assert "FAIL: SQLite data/schema/account" in result.stderr


def test_offsite_auth_restore_refuses_symlinked_archive(tmp_path):
    archive, key, bindir = _fixture(tmp_path)
    link = tmp_path / "linked.age"
    link.symlink_to(archive)
    env = os.environ.copy()
    env["PATH"] = str(bindir) + os.pathsep + env["PATH"]
    result = subprocess.run(
        ["bash", str(SCRIPT), str(link), str(key)],
        env=env, capture_output=True, text=True, timeout=8,
    )
    assert result.returncode == 1
    assert "existing regular file" in result.stderr


def test_offsite_auth_restore_never_touches_production():
    script = SCRIPT.read_text()
    # Temporary decrypted/restore artifacts must be in RAM-backed tmpfs.
    assert "mktemp -d /dev/shm/" in script
    assert "trap cleanup EXIT" in script
    # The tool neither logs in nor connects to live systems.
    program = "\\n".join(
        line for line in script.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    assert "docker " not in program
    assert "ssh " not in program
    assert "rclone " not in program
    assert "curl " not in program
    assert "docker compose" not in program
    assert "PANADAN_AUTH_MIGRATION_TEST_ALLOW_APPLY" not in program
