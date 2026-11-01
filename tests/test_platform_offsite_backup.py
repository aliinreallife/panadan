"""Offline integration-style safety tests for the optional owned PG backup.

All docker, age and rclone calls use test-only fake executables. No actual
source Odoo/VPN, production database, cloud remote or credentials are touched.
"""
from pathlib import Path
import os
import shutil
import stat
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/backup-platform-offsite.sh"


def _executable(path: Path, source: str) -> None:
    path.write_text(source)
    path.chmod(0o700)


def _sandbox(tmp_path):
    (tmp_path / "tools").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "tmp").mkdir()
    (tmp_path / "remote").mkdir()
    shutil.copyfile(SCRIPT, tmp_path / "tools/backup-platform-offsite.sh")
    shutil.copyfile(ROOT / "compose.platform.yaml", tmp_path / "compose.platform.yaml")
    platform_env = tmp_path / ".env.platform"
    platform_env.write_text("PANADAN_PLATFORM_DB_PORT=15433\nPANADAN_PLATFORM_DB_PASSWORD=" + "a" * 64 + "\n")
    platform_env.chmod(0o600)

    binaries = tmp_path / "bin"
    binaries.mkdir()
    _executable(binaries / "docker", r'''#!/usr/bin/env python3
import os,sys
args=sys.argv[1:]
with open(os.environ["MOCK_LOG"],"a") as f:
    f.write("docker " + " ".join(args[:4]) + "\n")
if args == ["compose","version"]:
    print("Docker Compose version v2")
elif "ps" in args and "-q" in args and "db" in args:
    print("synthetic-owned-postgres")
elif args and args[0]=="inspect":
    print("true")
elif args and args[0]=="exec":
    if "psql" in args:
        print("17|wrong|wrong|0" if os.environ.get("MOCK_BAD_DB") else "18|panadan|panadan_owner|7")
    elif "pg_dump" in args:
        sys.stdout.buffer.write(b"PGDMP synthetic and private test bytes")
    elif "pg_restore" in args:
        sys.exit(0 if sys.stdin.buffer.read().startswith(b"PGDMP") else 1)
    else:
        sys.exit(4)
else:
    sys.exit(3)
''')
    _executable(binaries / "age", r'''#!/usr/bin/env python3
import pathlib,sys,os
args=sys.argv[1:]
with open(os.environ["MOCK_LOG"],"a") as f:f.write("age\n")
if "-r" not in args or "-o" not in args:sys.exit(2)
pathlib.Path(args[args.index("-o")+1]).write_bytes(b"synthetic-age:" + pathlib.Path(args[-1]).read_bytes())
''')
    _executable(binaries / "rclone", r'''#!/usr/bin/env python3
import os,pathlib,sys
args=sys.argv[1:]
with open(os.environ["MOCK_LOG"],"a") as f:f.write("rclone " + args[0] + "\n")
folder=pathlib.Path(os.environ["MOCK_REMOTE_DIR"])
if args[0]=="lsf":
    sys.exit(2 if os.environ.get("MOCK_REMOTE_DOWN") else 0)
name=args[2].rsplit("/",1)[-1] if args[0]=="copyto" else args[1].rsplit("/",1)[-1]
if args[0]=="copyto":
    (folder/name).write_bytes(pathlib.Path(args[1]).read_bytes())
elif args[0]=="cat":
    content=(folder/name).read_bytes()
    sys.stdout.buffer.write(content + (b"corrupted" if os.environ.get("MOCK_CORRUPT") else b""))
else:
    sys.exit(3)
''')
    env = os.environ.copy()
    env.update(
        PATH=str(binaries) + os.pathsep + env["PATH"],
        TMPDIR=str(tmp_path / "tmp"),
        MOCK_REMOTE_DIR=str(tmp_path / "remote"),
        MOCK_LOG=str(tmp_path / "commands.log"),
        PANADAN_PLATFORM_BACKUP_LOCK_FILE=str(tmp_path / "backup.lock"),
        PANADAN_BACKUP_AGE_RECIPIENT="age1syntheticpublicrecipient",
        PANADAN_PLATFORM_BACKUP_RCLONE_DEST="offsite:panadan/owned-postgres",
    )
    return env, platform_env


def _run(tmp_path, env, *args):
    return subprocess.run(
        ["bash", str(tmp_path / "tools/backup-platform-offsite.sh"), *args],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=15,
    )


def test_syntax_and_source_database_isolation():
    checked = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True, timeout=8)
    assert checked.returncode == 0, checked.stderr
    content = SCRIPT.read_text()
    assert "compose.platform.yaml" in content
    assert ".env.platform" in content
    assert "panadan_owner" in content
    assert "pg_dump" in content and "pg_restore --list" in content
    assert "age -r" in content and "--immutable" in content
    assert "rclone cat" in content and "sha256sum" in content
    for forbidden in [".env.db", ".env.app", "client.ovpn", "192.168.3.9",
                      "docker compose down", "docker volume rm", "docker restart",
                      "docker compose up", "psql -c 'DROP"]:
        assert forbidden not in content


def test_read_only_preflight_does_not_create_archives_or_upload(tmp_path):
    env, _ = _sandbox(tmp_path)
    result = _run(tmp_path, env, "--check")
    assert result.returncode == 0, result.stderr
    calls = (tmp_path / "commands.log").read_text()
    assert "rclone lsf" in calls
    assert "pg_dump" not in calls
    assert "rclone copyto" not in calls
    assert "age" not in calls
    assert not list((tmp_path / "remote").iterdir())
    assert not list((tmp_path / "tmp").iterdir())


def test_success_is_encrypted_byte_verified_and_plaintext_is_destroyed(tmp_path):
    env, _ = _sandbox(tmp_path)
    result = _run(tmp_path, env)
    assert result.returncode == 0, result.stderr
    assert "PASS:" in result.stdout
    stored = list((tmp_path / "data/platform-backups/encrypted").glob("*.age"))
    remote = list((tmp_path / "remote").glob("*.age"))
    assert len(stored) == len(remote) == 1
    assert stored[0].read_bytes() == remote[0].read_bytes()
    assert stored[0].read_bytes().startswith(b"synthetic-age:PGDMP")
    assert stat.S_IMODE(stored[0].stat().st_mode) == 0o600
    assert not list((tmp_path / "tmp").iterdir())
    assert not list(tmp_path.rglob("*.dump"))
    calls = (tmp_path / "commands.log").read_text()
    assert "pg_dump" in calls and "pg_restore" in calls
    assert "rclone copyto" in calls and "rclone cat" in calls


def test_remote_corruption_does_not_promote_unverified_copy(tmp_path):
    env, _ = _sandbox(tmp_path)
    env["MOCK_CORRUPT"] = "1"
    result = _run(tmp_path, env)
    assert result.returncode != 0
    assert "checksum mismatch" in result.stderr
    assert not list((tmp_path / "data").rglob("*.age"))
    assert not list((tmp_path / "tmp").iterdir())
    assert list((tmp_path / "remote").glob("*.age"))  # evidence kept for investigation


def test_malformed_or_public_platform_env_fails_before_db_access(tmp_path):
    env, private = _sandbox(tmp_path)
    private.chmod(0o644)
    result = _run(tmp_path, env, "--check")
    assert result.returncode != 0
    assert "group/world" in result.stderr
    assert not (tmp_path / "commands.log").exists()
    private.chmod(0o600)
    private.write_text("PANADAN_PLATFORM_DB_PASSWORD=missing\n")
    result = _run(tmp_path, env, "--check")
    assert result.returncode != 0
    assert "Malformed" in result.stderr
    assert not (tmp_path / "commands.log").exists()


def test_wrong_database_identity_and_remote_failure_fail_closed(tmp_path):
    env, _ = _sandbox(tmp_path)
    env["MOCK_BAD_DB"] = "1"
    result = _run(tmp_path, env)
    assert result.returncode != 0
    assert "Unexpected PostgreSQL" in result.stderr
    assert "pg_dump" not in (tmp_path / "commands.log").read_text()
    env.pop("MOCK_BAD_DB")
    env["MOCK_REMOTE_DOWN"] = "1"
    result = _run(tmp_path, env)
    assert result.returncode != 0
    assert "off-site destination" in result.stderr
    assert "pg_dump" not in (tmp_path / "commands.log").read_text()


def test_requires_both_independent_destination_and_public_recipient(tmp_path):
    env, _ = _sandbox(tmp_path)
    del env["PANADAN_BACKUP_AGE_RECIPIENT"]
    result = _run(tmp_path, env)
    assert result.returncode != 0
    assert "age PUBLIC recipient" in result.stderr
    assert not (tmp_path / "commands.log").exists()
    env["PANADAN_BACKUP_AGE_RECIPIENT"] = "age1fake"
    del env["PANADAN_PLATFORM_BACKUP_RCLONE_DEST"]
    result = _run(tmp_path, env)
    assert result.returncode != 0
    assert "PANADAN_PLATFORM_BACKUP_RCLONE_DEST" in result.stderr
