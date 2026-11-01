"""No-VPS regression tests for guarded owned PostgreSQL setup orchestration."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tools/setup_owned_auth_pg.py"
spec = importlib.util.spec_from_file_location("owned_pg_setup", PATH)
assert spec and spec.loader
setup = importlib.util.module_from_spec(spec)
sys.path.insert(0, str(ROOT / "tools"))
spec.loader.exec_module(setup)


def test_shell_wrapper_and_setup_python_are_well_formed():
    proc = subprocess.run(
        ["bash", "-n", str(ROOT / "tools/setup-owned-auth-pg.sh")],
        capture_output=True, text=True, timeout=10,
    )
    assert proc.returncode == 0, proc.stderr
    compile(PATH.read_text(), str(PATH), "exec")


def test_command_defaults_refuse_live_mutations(monkeypatch, capsys):
    monkeypatch.setattr(setup, "preflight", lambda: None)
    monkeypatch.setattr(setup, "network_stage", lambda: "before")
    calls = []
    monkeypatch.setattr(setup, "audit_network", lambda stage: calls.append(("audit",stage)))
    monkeypatch.setattr(setup, "source_routes", lambda: calls.append(("routes",)))
    monkeypatch.setattr(setup, "endpoints", lambda: calls.append(("endpoints",)))
    monkeypatch.setattr(setup, "apply", lambda: calls.append(("DANGEROUS",)))
    monkeypatch.setattr(sys, "argv", ["setup", "plan"])
    assert setup.main() == 0
    assert calls == [("audit","before"),("routes",),("endpoints",)]
    monkeypatch.setattr(sys, "argv", ["setup", "apply"])
    assert setup.main() == 1
    assert ("DANGEROUS",) not in calls
    assert "REFUSED" in capsys.readouterr().err


def test_setup_rolls_back_only_newly_created_members_when_tcp_fails(monkeypatch):
    members = set()
    network = None
    calls = []

    def fake_network():
        if network is None:
            return None
        return {
            "Name": setup.NET, "Driver": "bridge", "Internal": True,
            "IPAM": {"Config": [{"Subnet": "172.31.12.0/24"}]},
            "Containers": {m: {"Name": m} for m in members},
        }

    def fake_run(*args, **kwargs):
        nonlocal network
        calls.append(args)
        if args[:3] == ("docker","network","create"):
            network = True
        elif args[:3] == ("docker","network","connect"):
            members.add(args[-1])
        elif args[:3] == ("docker","network","disconnect"):
            members.remove(args[-1])
        elif args[:3] == ("docker","network","rm"):
            assert not members
            network = None
        return ""

    monkeypatch.setattr(setup, "preflight", lambda: None)
    monkeypatch.setattr(setup, "network_stage", lambda: "before")
    monkeypatch.setattr(setup, "audit_network", lambda stage: None)
    monkeypatch.setattr(setup, "source_routes", lambda: None)
    monkeypatch.setattr(setup, "endpoints", lambda: None)
    monkeypatch.setattr(setup, "current_db_backup", lambda: None)
    monkeypatch.setattr(setup, "new_subnet_safe", lambda net: None)
    monkeypatch.setattr(setup, "inspect_network", fake_network)
    monkeypatch.setattr(setup, "run", fake_run)

    def tcp_failure():
        raise setup.Refusal("simulated private DNS timeout")
    monkeypatch.setattr(setup, "tcp_smoke", tcp_failure)
    with pytest.raises(setup.Refusal, match="DNS"):
        setup.apply()
    assert network is None
    assert members == set()
    assert ("docker","network","disconnect",setup.NET,setup.VPN) in calls
    assert ("docker","network","disconnect",setup.NET,setup.PG) in calls
    assert not any(cmd[:3] == ("docker","compose","up") for cmd in calls)


def test_repeated_setup_never_reattaches_existing_network(monkeypatch):
    calls = []
    monkeypatch.setattr(setup, "preflight", lambda: None)
    monkeypatch.setattr(setup, "network_stage", lambda: "after")
    monkeypatch.setattr(setup, "audit_network", lambda stage: calls.append(("audit",stage)))
    monkeypatch.setattr(setup, "source_routes", lambda: None)
    monkeypatch.setattr(setup, "endpoints", lambda: None)
    monkeypatch.setattr(setup, "current_db_backup", lambda: None)
    monkeypatch.setattr(setup, "new_subnet_safe", lambda n: None)
    monkeypatch.setattr(setup, "inspect_network", lambda: {
        "Name": setup.NET, "Driver": "bridge", "Internal": True,
        "Containers": {setup.PG: {"Name": setup.PG},
                       setup.VPN: {"Name": setup.VPN}}
    })
    monkeypatch.setattr(setup, "tcp_smoke", lambda: None)
    monkeypatch.setattr(setup, "schema_apply", lambda: calls.append(("schema",)))
    monkeypatch.setattr(setup, "check_role", lambda: calls.append(("role",)))
    monkeypatch.setattr(setup, "run", lambda *args, **kw: calls.append(args))
    setup.apply()
    assert calls == [
        ("audit","after"), ("audit","after"), ("schema",), ("role",),
    ]


def test_offline_auth_password_is_unique_and_secret_is_not_logged(monkeypatch,tmp_path,capsys):
    path=tmp_path / ".env.platform.auth"
    monkeypatch.setattr(setup, "AUTH_FILE", path)
    secret=setup.auth_password()
    assert len(secret)==64
    assert path.stat().st_mode & 0o777 == 0o600
    assert "PANADAN_AUTH_RUNTIME_PASSWORD" in path.read_text()
    assert setup.auth_password()==secret
    assert secret not in capsys.readouterr().out
    path.chmod(0o644)
    with pytest.raises(setup.Refusal,match="0600"):
        setup.auth_password()


def test_subnet_guard_rejects_odoo_and_existing_routes(monkeypatch):
    monkeypatch.setattr(setup, "run", lambda *a,**kw:
        "172.21.0.0/16 dev eth0\n192.168.3.9 via 172.21.0.1 dev tun0\n")
    with pytest.raises(setup.Refusal,match="Odoo"):
        setup.new_subnet_safe({"IPAM":{"Config":[{"Subnet":"192.168.3.0/24"}]}})
    with pytest.raises(setup.Refusal,match="overlaps"):
        setup.new_subnet_safe({"IPAM":{"Config":[{"Subnet":"172.21.10.0/24"}]}})
    setup.new_subnet_safe({"IPAM":{"Config":[{"Subnet":"172.29.10.0/24"}]}})


def test_no_automatic_compose_recreate_or_live_auth_cutover():
    source=PATH.read_text()
    assert "compose\", \"up\"" not in source
    assert "compose\", \"down\"" not in source
    assert "PANADAN_AUTH_DB" not in source
    assert "docker\", \"network\", \"connect\"" in source
    assert "ack-restored-backup" in source
    assert "approve-live-network" in source
