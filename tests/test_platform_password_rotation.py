"""Safe offline checks for owner password rotation on the *local* platform DB.

All Docker calls go to a temporary fake executable: never touches Odoo,
the real Panadan database, or a production volume.
"""
import os
from pathlib import Path
import shutil
import stat
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/platform-db.sh"


def _sandbox(tmp_path, *, mode=0o600):
    (tmp_path / "tools").mkdir()
    shutil.copyfile(SCRIPT, tmp_path / "tools/platform-db.sh")
    shutil.copyfile(ROOT / "tools/scram_secret.py", tmp_path / "tools/scram_secret.py")
    original = (
        "PANADAN_PLATFORM_DB_PORT=15433\n"
        "PANADAN_PLATFORM_DB_PASSWORD=" + "a" * 64 + "\n"
        "KEEP_UNRELATED_OPTION=yes\n"
    )
    private = tmp_path / ".env.platform"
    private.write_text(original)
    private.chmod(mode)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(r"""#!/usr/bin/env bash
set -euo pipefail
args="$*"
if [[ "$args" == "compose version" ]]; then exit 0; fi
if [[ "$args" == *"inspect --format"* ]]; then echo true; exit 0; fi
if [[ "$args" == *" ps -q db"* ]]; then echo fake-platform-container; exit 0; fi
if [[ "$args" == *"SHOW server_version_num"* ]]; then echo 180006; exit 0; fi
if [[ "$args" == *"current_database()"* ]]; then echo panadan:panadan_owner; exit 0; fi
if [[ "$args" == *"SHOW log_statement"* ]]; then echo "${MOCK_LOG_STATEMENT:-none}"; exit 0; fi
if [[ "$args" == *"--single-transaction"* ]]; then
    IFS= read -r statement
    [[ "$statement" =~ ^ALTER[[:space:]]ROLE[[:space:]]panadan_owner[[:space:]]PASSWORD[[:space:]]\'SCRAM-SHA-256\$[0-9]+:[A-Za-z0-9+/=]+\\$[A-Za-z0-9+/=]+:[A-Za-z0-9+/=]+\'\;$ ]] || exit 2
    [[ "${MOCK_ALTER_FAIL:-}" != YES ]] || exit 4
    printf 'alter\n' >> "$MOCK_LOG"
    exit 0
fi
if [[ "$args" == *" --force-recreate db"* ]]; then
    printf 'recreate\n' >> "$MOCK_LOG"
    [[ "${MOCK_RECREATE_FAIL:-}" != YES ]]
    exit
fi
if [[ "$args" == *" sh -c "* ]]; then
    printf 'auth\n' >> "$MOCK_LOG"
    echo 1
    exit 0
fi
echo 'Unexpected Docker call' >&2
exit 3
""")
    docker.chmod(0o700)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["MOCK_LOG"] = str(tmp_path / "mock.log")
    return private, original, env


def _run(tmp_path, env):
    return subprocess.run(
        ["bash", str(tmp_path / "tools/platform-db.sh"), "rotate-password"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=15,
    )


def test_rotate_password_updates_private_env_and_probes_tcp(tmp_path):
    private, original, env = _sandbox(tmp_path)
    run = _run(tmp_path, env)
    assert run.returncode == 0, run.stderr
    updated = private.read_text()
    assert updated != original
    assert "PANADAN_PLATFORM_DB_PORT=15433\n" in updated
    assert "KEEP_UNRELATED_OPTION=yes\n" in updated
    new_secret = updated.split("PANADAN_PLATFORM_DB_PASSWORD=", 1)[1].splitlines()[0]
    assert len(new_secret) == 64 and new_secret != "a" * 64
    assert stat.S_IMODE(private.stat().st_mode) == 0o600
    assert new_secret not in run.stdout + run.stderr
    assert ("a" * 64) not in run.stdout + run.stderr
    assert (tmp_path / "mock.log").read_text().splitlines() == ["alter", "recreate", "auth"]
    assert not list(tmp_path.glob(".env.platform.rotate.*"))
    assert "SCRAM-SHA-256$" not in updated  # only the plaintext password belongs in env
    assert "python3 tools/scram_secret.py" in SCRIPT.read_text()
    assert "--force-recreate db" in SCRIPT.read_text()
    assert 'PGPASSWORD="$POSTGRES_PASSWORD"' in SCRIPT.read_text()
    assert "docker volume rm" not in SCRIPT.read_text()


def test_failed_server_alter_preserves_original_credentials(tmp_path):
    private, original, env = _sandbox(tmp_path)
    env["MOCK_ALTER_FAIL"] = "YES"
    run = _run(tmp_path, env)
    assert run.returncode != 0
    assert private.read_text() == original
    assert not list(tmp_path.glob(".env.platform.rotate.*"))
    assert "recreate" not in (tmp_path / "mock.log").read_text() if (tmp_path / "mock.log").exists() else True


def test_rotation_refuses_public_or_symlinked_credentials(tmp_path):
    private, original, env = _sandbox(tmp_path, mode=0o644)
    run = _run(tmp_path, env)
    assert run.returncode != 0
    assert private.read_text() == original
    private.unlink()
    target = tmp_path / "elsewhere.env"
    target.write_text(original)
    target.chmod(0o600)
    private.symlink_to(target)
    rejected = _run(tmp_path, env)
    assert rejected.returncode != 0
    assert target.read_text() == original


def test_failed_container_recreation_keeps_new_credentials_for_recovery(tmp_path):
    private, original, env = _sandbox(tmp_path)
    env["MOCK_RECREATE_FAIL"] = "YES"
    run = _run(tmp_path, env)
    assert run.returncode != 0
    assert private.read_text() != original
    assert "Retry platform-db up" in run.stderr
    assert not list(tmp_path.glob(".env.platform.rotate.*"))


def test_rotation_refuses_sql_logging_before_generating_a_password(tmp_path):
    private, original, env = _sandbox(tmp_path)
    env["MOCK_LOG_STATEMENT"] = "ddl"
    result = _run(tmp_path, env)
    assert result.returncode != 0
    assert "statement logging" in result.stderr
    assert private.read_text() == original
    assert not list(tmp_path.glob(".env.platform.rotate.*"))
