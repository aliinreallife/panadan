"""No-VPN tests for Panadan's opt-in platform database management CLI.

Only setup runs in a disposable temporary folder. Tests never start Docker or
connect to the existing Odoo/VPN or a persistent database.
"""
from pathlib import Path
import re
import shutil
import stat
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/platform-db.sh"


def test_platform_db_setup_creates_private_secret_and_refuses_overwrite(tmp_path):
    tools = tmp_path / "tools"
    tools.mkdir()
    shutil.copyfile(SCRIPT, tools / "platform-db.sh")

    first = subprocess.run(
        ["bash", str(tools / "platform-db.sh"), "setup"],
        capture_output=True, text=True, check=True,
        cwd=tmp_path, timeout=10,
    )
    env_file = tmp_path / ".env.platform"
    assert env_file.is_file()
    content = env_file.read_text()
    assert re.search(r"(?m)^PANADAN_PLATFORM_DB_PASSWORD=[a-f0-9]{64}$", content)
    assert "PANADAN_PLATFORM_DB_PORT=15433" in content
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600
    assert content.split("PANADAN_PLATFORM_DB_PASSWORD=")[1].strip() not in first.stdout

    second = subprocess.run(
        ["bash", str(tools / "platform-db.sh"), "setup"],
        capture_output=True, text=True, cwd=tmp_path, timeout=10,
    )
    assert second.returncode != 0
    assert "refusing to overwrite" in second.stderr
    assert env_file.read_text() == content


def test_cli_never_references_odoo_credentials_or_deletes_volumes():
    script = SCRIPT.read_text()
    assert "compose.platform.yaml" in script
    assert ".env.platform" in script
    assert ".env.db" not in script
    assert ".env.app" not in script
    assert "vpn/client.ovpn" not in script
    assert "192.168.3.9" not in script
    assert "docker volume rm" not in script
    assert "down -v" not in script and "down --volumes" not in script
    assert "pg_dump" in script and "pg_restore --list" in script
    assert "database/migrations/001_multisource_foundation.sql" in script
    assert "--single-transaction" in script
    assert "assert_pg18" in script
    assert "chmod 600" in script
    assert "chmod 700" in script


def test_bash_wrapper_routes_platform_commands_separately_from_source():
    wrapper = (ROOT / "panadan.sh").read_text()
    early = wrapper.split("if [[ -f .env.app ]]; then", 1)[0]
    assert 'if [[ "$cmd" == "platform-db" ]]; then' in early
    assert 'exec bash tools/platform-db.sh "$@"' in early
    assert "check_config" not in early
    assert ".env.db" not in early


def test_help_does_not_need_secret_or_docker():
    r = subprocess.run(
        ["bash", str(SCRIPT), "help"],
        cwd=ROOT, capture_output=True, text=True, check=True, timeout=10,
    )
    assert "{setup|up|init|check|backup|rotate-password|down|roles-setup|roles-apply|roles-check}" in r.stdout


def test_disposable_docker_container_name_expands_bash_pid():
    """A literal $ is an illegal Docker container name (regression)."""
    runner = (ROOT / "tools/test-platform-integration.sh").read_text()
    assert 'container="panadan-ci-pg-${BASHPID}"' in runner
    assert 'container="panadan-ci-pg-$"' not in runner
    assert 'docker run -d \\' in runner
    assert 'docker run --rm -d' not in runner
    assert 'docker restart "$container"' in runner
    assert 'docker rm -fv "$container"' in runner
