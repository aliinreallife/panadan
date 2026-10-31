"""Offline guardrails for the optional PostgreSQL 18 platform stack.

These tests only read checked-in config. They never start Docker, import
source call records, or access Odoo/VPN credentials.
"""
from pathlib import Path
import re


IMAGE = (
    "postgres:18.6-alpine3.24@sha256:"
    "10a5c69a83035ab5239f5620d708520e8b28f5aa1f2b20143e6024532edadfb5"
)


def test_pinned_postgres_image_matches_ci_and_local_platform_and_test_runner():
    ci = Path(".github/workflows/tests.yml").read_text()
    compose = Path("compose.platform.yaml").read_text()
    runner = Path("tools/test-platform-integration.sh").read_text()
    assert f"image: {IMAGE}" in ci
    assert f"image: {IMAGE}" in compose
    assert IMAGE in runner
    assert "postgres:17" not in (ci + compose + runner)
    assert "tools/test-platform-integration.sh" in ci


def test_pg18_persistent_volume_not_pg17_style_and_not_part_of_odoo_stack():
    compose = Path("compose.platform.yaml").read_text()
    assert "name: panadan-platform" in compose
    assert "PGDATA: /var/lib/postgresql/18/docker" in compose
    assert "panadan_platform_pg18_data:/var/lib/postgresql" in compose
    assert "/var/lib/postgresql/data" not in compose
    assert "'127.0.0.1:${PANADAN_PLATFORM_DB_PORT:-15433}:5432'" in compose
    assert "${PANADAN_PLATFORM_DB_PASSWORD:?" in compose
    assert ".env.db" not in compose and "vpn/client.ovpn" not in compose
    assert "compose.platform.yaml" not in Path("compose.dev.yaml").read_text()
    assert "compose.platform.yaml" not in Path("compose.prod.yaml").read_text()


def test_platform_secret_example_tracked_but_real_secret_ignored():
    ignore = Path(".gitignore").read_text()
    example = Path(".env.platform.example").read_text()
    assert ".env.*" in ignore
    assert "!.env.platform.example" in ignore
    assert re.search(r"(?m)^PANADAN_PLATFORM_DB_PASSWORD=\s*$", example)
    assert "PANADAN_PLATFORM_DB_PORT=15433" in example


def test_disposable_runner_uses_only_synthetic_database_and_cleanup():
    runner = Path("tools/test-platform-integration.sh").read_text()
    assert "trap cleanup EXIT INT TERM" in runner
    assert "docker rm -f" in runner
    assert "-p 127.0.0.1::5432" in runner
    assert "POSTGRES_DB=panadan_ci" in runner
    assert "PANADAN_PLATFORM_TEST_ALLOW_RESET=YES" in runner
    assert "test_platform_ingest.py" in runner
    assert ".env.db" not in runner and ".env.app" not in runner
    assert "192.168.3.9" not in runner
