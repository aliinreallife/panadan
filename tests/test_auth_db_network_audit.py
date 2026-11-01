"""Pure offline invariants for the VPS private database networking audit."""
import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tools/check_auth_db_network.py"
spec = importlib.util.spec_from_file_location("check_auth_db_network", PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixtures():
    def c(nets, *, ports=None, healthy=False):
        return {
            "State": {"Running": True, "Health": {"Status": "healthy" if healthy else None}},
            "NetworkSettings": {"Networks": nets, "Ports": ports or {}}
        }
    network = {
        "Name": "panadan-auth-db", "Driver": "bridge", "Internal": True,
        "Containers": {}
    }
    containers = {
        module.PG: c(
            {"panadan-platform_default": {}},
            ports={"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "15433"}]},
            healthy=True
        ),
        module.VPN: c({"panadan_default": {}, "panadan-ingress": {}}, healthy=True),
        module.WEB: c({}),
        module.PROXY: c({}),
        module.GATEWAY: c({})
    }
    return containers, network


def attached():
    cs, net = fixtures()
    cs[module.PG]["NetworkSettings"]["Networks"][module.NET] = {
        "Aliases": ["panadan-auth-postgres"]
    }
    cs[module.VPN]["NetworkSettings"]["Networks"][module.NET] = {}
    net["Containers"] = {
        "abc": {"Name": module.PG}, "def": {"Name": module.VPN}
    }
    return cs, net


def test_safe_before_without_created_network():
    cs, _ = fixtures()
    messages = module.audit(cs, None, "before")
    assert len(messages) == 2


def test_safe_before_empty_internal_network():
    cs, net = fixtures()
    assert len(module.audit(cs, net, "before")) == 3


def test_safe_after_exact_private_members_and_alias():
    cs, net = attached()
    assert module.audit(cs, net, "after")[-1].startswith("PASS:")


def test_reject_missing_members_and_wrong_hostname():
    cs, net = attached()
    net["Containers"].pop("def")
    with pytest.raises(ValueError, match="Both PostgreSQL and VPN"):
        module.audit(cs, net, "after")
    cs, net = attached()
    cs[module.PG]["NetworkSettings"]["Networks"][module.NET]["Aliases"] = []
    with pytest.raises(ValueError, match="alias"):
        module.audit(cs, net, "after")


def test_never_trust_public_or_wrong_network():
    cs, net = attached()
    for broken in (
        {"Internal": False},
        {"Driver": "host"},
    ):
        changed = {**net, **broken}
        with pytest.raises(ValueError, match="internal Docker bridge"):
            module.audit(cs, changed, "after")
    cs, net = attached()
    net["Containers"]["evil"] = {"Name": module.PROXY}
    with pytest.raises(ValueError, match="Unexpected service"):
        module.audit(cs, net, "after")


def test_original_vpn_route_network_and_localhost_binding_required():
    cs, net = attached()
    cases = [
        (module.PG, "NetworkSettings", "Networks", "panadan-platform_default"),
        (module.VPN, "NetworkSettings", "Networks", "panadan-ingress"),
    ]
    for name, prop, netkey, key in cases:
        changed = copy.deepcopy(cs)
        changed[name][prop][netkey].pop(key)
        with pytest.raises(ValueError):
            module.audit(changed, net, "after")
    cs, net = attached()
    cs[module.PG]["NetworkSettings"]["Ports"]["5432/tcp"][0]["HostIp"] = "0.0.0.0"
    with pytest.raises(ValueError, match="loopback"):
        module.audit(cs, net, "after")


def test_public_postgres_extra_binding_and_unhealthy_services_blocked():
    cs, net = attached()
    cs[module.PG]["NetworkSettings"]["Ports"]["5433/tcp"] = [
        {"HostIp": "::", "HostPort": "15434"}
    ]
    with pytest.raises(ValueError, match="non-loopback"):
        module.audit(cs, net, "after")
    cs, net = attached()
    cs[module.VPN]["State"]["Health"]["Status"] = "unhealthy"
    with pytest.raises(ValueError, match="Health"):
        module.audit(cs, net, "after")
