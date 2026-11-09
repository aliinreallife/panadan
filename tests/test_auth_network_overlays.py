"""Offline Compose network topology checks; never start/stop containers."""
from pathlib import Path
import json
import os
import shutil
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[1]


def _compose(tmp_path, files, env=None):
    if shutil.which("docker") is None:
        pytest.skip("Docker CLI not installed")
    p=subprocess.run(
        ["docker","compose", *sum((["-f",str(f)] for f in files),[]),
         "config","--format","json"],
        cwd=tmp_path,env={**os.environ,**(env or {})},
        text=True,capture_output=True,timeout=20,
    )
    if p.returncode!=0:
        # Do not dump stdout: rendered Compose output can contain
        # interpolated passwords, even when the test expects synthetic env.
        # Docker Desktop/WSL failures sometimes exit without any stderr.
        try:
            version = subprocess.run(
                ["docker", "compose", "version"], cwd=tmp_path,
                text=True, capture_output=True, timeout=10,
            )
            diagnostic = (
                f"; compose_version_exit={version.returncode}"
                f"; compose_version={version.stdout.strip()[:120] if version.returncode == 0 else 'unavailable'}"
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            diagnostic = f"; compose_version_check={type(exc).__name__}"
        pytest.fail(
            f"Docker Compose offline config failed: exit={p.returncode}"
            f"; stdout_bytes={len(p.stdout)}"
            f"; stderr={p.stderr[:400]!r}{diagnostic}"
        )
    return json.loads(p.stdout)


def test_platform_postgres_remains_localhost_only_and_preserves_default(tmp_path):
    config=_compose(tmp_path,[
        ROOT/"compose.platform.yaml",
        ROOT/"deploy/compose.auth-network.platform.yaml",
    ],{"PANADAN_PLATFORM_DB_PASSWORD":"a"*64})
    pg=config["services"]["db"]
    assert set(pg["networks"])=={"default","auth_db"}
    assert pg["networks"]["auth_db"]["aliases"]==["panadan-auth-postgres"]
    assert config["networks"]["auth_db"]["external"] is True
    assert config["networks"]["auth_db"]["name"]=="panadan-auth-db"
    assert all(port["host_ip"]=="127.0.0.1" for port in pg["ports"])
    assert len(pg["volumes"])==1
    assert pg["volumes"][0]["target"]=="/var/lib/postgresql"
    assert pg["healthcheck"]["test"][0]=="CMD-SHELL"


def test_panadan_vpn_keeps_default_private_ingress_and_web_namespace(tmp_path):
    # Entirely synthetic contents. No actual environment files or VPN used.
    (tmp_path/".env.app").write_text("PANADAN_AUTH_DB=/data/auth.sqlite\n")
    (tmp_path/".env.db").write_text("PGSSLMODE=require\n")
    ingress=tmp_path/"synthetic-ingress.yaml"
    ingress.write_text(
        "services:\n  vpn:\n    networks:\n      default: {}\n"
        "      ingress: {}\nnetworks:\n  ingress:\n"
        "    external: true\n    name: panadan-ingress\n"
    )
    # Compose resolves env_file relative to its *first* compose file,
    # not cwd. Copy the baseline config into the synthetic temp directory
    # so no real private .env files are read in CI.
    baseline=tmp_path/"compose.prod.yaml"
    shutil.copyfile(ROOT/"compose.prod.yaml",baseline)
    config=_compose(tmp_path,[
        baseline,
        ingress,
        ROOT/"deploy/compose.auth-network.panadan.yaml",
    ])
    vpn=config["services"]["vpn"]
    assert set(vpn["networks"])=={"default","ingress","auth_db"}
    assert config["networks"]["auth_db"]["name"]=="panadan-auth-db"
    assert config["networks"]["auth_db"]["external"] is True
    assert "auth_db" not in config["services"]["web"].get("networks",{})
    assert config["services"]["web"]["network_mode"]=="service:vpn"
    assert len(vpn["ports"])==1
    assert vpn["ports"][0]["host_ip"]=="127.0.0.1"
    assert vpn["devices"]
    assert "NET_ADMIN" in vpn["cap_add"]


def test_overlays_do_not_change_secrets_permissions_or_direct_source_access():
    pg=(ROOT/"deploy/compose.auth-network.platform.yaml").read_text()
    app=(ROOT/"deploy/compose.auth-network.panadan.yaml").read_text()
    for data in (pg,app):
        assert "panadan-auth-db" in data
        assert "panadan_ingest" not in data
        assert "192.168.3.9" not in data
        assert "network_mode: host" not in data
        assert "ports:" not in data
        assert "privileged:" not in data
        assert "password" not in data.lower()
