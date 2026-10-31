"""Regression guard for Docker Desktop/WSL bind mounts and safe relay refresh."""
from pathlib import Path


def test_relay_mount_uses_stable_directory_not_single_git_file():
    compose = Path("compose.dev.yaml").read_text()
    assert "- ./tools:/relay:ro" in compose
    assert "./tools/pgrelay.py:/relay/pgrelay.py" not in compose
    assert "network_mode: service:vpn" in compose
    assert "command: [python, -u, /relay/pgrelay.py]" in compose
    assert "- '127.0.0.1:${PANADAN_PG_PROXY_PORT:-15432}:15432'" in compose


def test_relay_recreation_is_nondependent_and_does_not_reset_vpn():
    shell = Path("panadan.sh").read_text()
    section = shell.split("  relay-recreate)", 1)[1].split("  ;;", 1)[0]
    assert "check_config" in section
    assert "compose_dev up -d --no-deps --force-recreate pgrelay" in section
    assert "compose_dev down" not in section
    assert "vpn-down" not in section
    assert "relay-recreate" in shell.split("Usage:", 1)[1]


def test_readme_no_longer_recommends_brittle_restart():
    readme = Path("README.md").read_text()
    assert "./panadan.sh relay-recreate" in readme
    assert "restart pgrelay" not in readme
