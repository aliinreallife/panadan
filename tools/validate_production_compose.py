#!/usr/bin/env python3
"""No-secrets, fail-closed validation of Panadan's effective production Compose.

Read a single Docker Compose JSON document (or Docker network inspect array)
from stdin. Do not print the source JSON, environment values, credentials,
file paths or network details on failure.
"""
from __future__ import annotations

import json
import re
import sys
from collections.abc import Mapping

ALLOWED_LOCAL_TAG = re.compile(r"^panadan-(?:web|vpn):[a-f0-9]{7,40}$")
PINNED_GHCR_TAG = re.compile(
    r"^ghcr\.io/aliinreallife/panadan-(?:web|vpn):sha-[a-f0-9]{40}$"
)
DIGEST = re.compile(r"^[a-zA-Z0-9._/-]+@sha256:[a-f0-9]{64}$")


class InvalidDeployment(ValueError):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise InvalidDeployment(reason)


def object_value(value: object, reason: str) -> Mapping:
    require(isinstance(value, dict), reason)
    return value


def service(data: Mapping, name: str) -> Mapping:
    services = object_value(data.get("services"), "missing services")
    return object_value(services.get(name), f"missing {name} service")


def pinned_image(value: object, name: str) -> None:
    require(
        isinstance(value, str)
        and (bool(DIGEST.fullmatch(value))
             or bool(PINNED_GHCR_TAG.fullmatch(value))
             or bool(ALLOWED_LOCAL_TAG.fullmatch(value))),
        f"{name} must use a reviewed digest or commit-specific image tag",
    )


def network_keys(svc: Mapping) -> set[str]:
    networks = svc.get("networks", {})
    if isinstance(networks, dict):
        return set(networks)
    if isinstance(networks, list):
        return {n for n in networks if isinstance(n, str)}
    raise InvalidDeployment("invalid service network declaration")


def private_port_bindings(svc: Mapping, name: str) -> None:
    ports = svc.get("ports") or []
    require(isinstance(ports, list), f"invalid {name} port declaration")
    for port in ports:
        require(isinstance(port, dict), f"{name} ports must use explicit host-IP mappings")
        ip = port.get("host_ip")
        require(isinstance(ip, str) and ip in ("127.0.0.1", "::1"),
                f"{name} cannot publish ports beyond host loopback")


def validate_panadan(data: Mapping, *, auth_enabled: bool) -> None:
    web = service(data, "web")
    vpn = service(data, "vpn")
    require(web.get("network_mode") == "service:vpn",
            "web must retain VPN network namespace")
    require(not web.get("ports"), "web must not publish host ports")
    require(not web.get("networks"), "web cannot attach separate networks")
    require((web.get("environment") or {}).get("PANADAN_COOKIE_SECURE") in ("true", "True", True),
            "secure session cookie required")
    require((web.get("environment") or {}).get("PANADAN_PUBLIC_ORIGIN")
            == "https://dan.panafor.com", "HTTPS origin mismatch")
    pinned_image(web.get("image"), "web")
    pinned_image(vpn.get("image"), "vpn")
    private_port_bindings(vpn, "vpn")
    vpn_networks = network_keys(vpn)
    require("default" in vpn_networks, "VPN original default network missing")
    require(any("ingress" in n for n in vpn_networks),
            "VPN private ingress network missing")
    require((not auth_enabled) or "auth_db" in vpn_networks,
            "owned auth network omitted from effective VPN Compose configuration")


def validate_plane(data: Mapping) -> None:
    proxy = service(data, "proxy")
    networks = network_keys(proxy)
    require("edge" in networks and len(networks) >= 2,
            "Plane proxy must preserve original and private edge networks")
    volumes = proxy.get("volumes") or []
    require(isinstance(volumes, list), "Plane proxy volumes missing")
    mounts = {
        v.get("target"): v for v in volumes
        if isinstance(v, dict) and isinstance(v.get("target"), str)
    }
    for target in ("/data", "/config"):
        mount = object_value(mounts.get(target), f"Plane proxy {target} persistence missing")
        require(mount.get("type") == "volume" and bool(mount.get("source")),
                f"Plane proxy {target} must preserve named persistent volume")
    caddy = object_value(mounts.get("/etc/caddy/Caddyfile"), "read-only Caddyfile missing")
    require(caddy.get("type") == "bind" and caddy.get("read_only") is True,
            "Plane Caddyfile must be a read-only bind mount")


def validate_gateway(data: Mapping) -> None:
    gw = service(data, "gateway")
    require(not gw.get("ports"), "Gateway must not publish host ports")
    require(not gw.get("network_mode"), "Gateway cannot share a host/service network namespace")
    networks = network_keys(gw)
    require(any("edge" in n for n in networks) and any("ingress" in n for n in networks),
            "Gateway requires private edge and ingress networks")
    require(not gw.get("privileged"), "Privileged gateway forbidden")


def validate_auth_network(data: object) -> None:
    require(isinstance(data, list) and len(data) == 1, "expected one auth network")
    net = object_value(data[0], "malformed auth network")
    require(net.get("Name") == "panadan-auth-db"
            and net.get("Driver") == "bridge"
            and net.get("Internal") is True,
            "owned auth bridge must be internal")
    containers = object_value(net.get("Containers"), "missing auth network memberships")
    names = {v.get("Name") for v in containers.values() if isinstance(v, dict)}
    require(names == {"panadan-vpn-1", "panadan-platform-db-1"},
            "owned auth network requires exactly VPN and owned PostgreSQL")
    # Network inspect does not reliably expose DNS aliases. The separate
    # existing check_auth_db_network.py queries each container for aliases.


def validate_caddy(source: str) -> None:
    # This is only a public-site-name guard. Detailed private Caddy routing
    # and upstream must be reviewed against the actual operator backup.
    sites = re.findall(r"(?m)^[ \t]*(?:https://)?([a-z0-9.-]+)[ \t]*\{", source)
    require("plane.panafor.com" in sites and "dan.panafor.com" in sites,
            "both Plane and Panadan HTTPS site blocks must be preserved")


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print("Usage: validate_production_compose.py panadan|plane|gateway|auth-network|caddy [--auth]", file=sys.stderr)
        return 2
    part = sys.argv[1]
    try:
        if part == "caddy":
            require(len(sys.argv) == 2, "unexpected arguments")
            validate_caddy(sys.stdin.read())
        else:
            data = json.load(sys.stdin)
            if part == "panadan":
                require(len(sys.argv) == 2 or sys.argv[2] == "--auth", "unexpected arguments")
                validate_panadan(object_value(data, "invalid Compose file"),
                                 auth_enabled=len(sys.argv) == 3)
            else:
                require(len(sys.argv) == 2, "unexpected arguments")
                if part == "plane":
                    validate_plane(object_value(data, "invalid Compose file"))
                elif part == "gateway":
                    validate_gateway(object_value(data, "invalid Compose file"))
                elif part == "auth-network":
                    validate_auth_network(data)
                else:
                    raise InvalidDeployment("unknown component")
    except (ValueError, KeyError, TypeError, StopIteration):
        # Even the exception reason can inadvertently contain service labels
        # or operator-controlled input: do not print it to shared CI/VPS logs.
        print(f"REFUSED: {part} production topology did not pass safety checks", file=sys.stderr)
        return 1
    print(f"PASS: {part} production topology safety checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
