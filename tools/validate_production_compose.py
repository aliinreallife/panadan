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

# These labels are ONLY static, developer-reviewed invariant identifiers.
# Never print an exception message or anything derived from Compose values.
# The explicit map prevents a future dynamic ValueError from leaking a secret.
SAFE_PANADAN_CHECKS = {
    "missing services": "service inventory",
    "missing web service": "web service declaration",
    "missing vpn service": "VPN service declaration",
    "web must retain VPN network namespace": "web VPN namespace",
    "web must not publish host ports": "web public ports",
    "web cannot attach separate networks": "web network isolation",
    "secure session cookie required": "web secure-cookie flag",
    "HTTPS origin mismatch": "web canonical HTTPS origin",
    "web environment missing": "web environment structure",
    "live SQLite authority must retain its persistent /data path": "SQLite auth database path",
    "production web release must retain SQLite authentication": "SQLite auth backend selector",
    "disposable staging credentials in live environment": "forbidden staging-auth settings",
    "unapproved MCP OAuth mode on routine web release": "MCP legacy authentication mode",
    "web authentication volume declaration missing": "web auth volume structure",
    "web SQLite /data must be backed by a persistent writable named volume": "SQLite persistent named /data mount",
    "web must use a reviewed digest or commit-specific image tag": "pinned web image",
    "vpn must use a reviewed digest or commit-specific image tag": "pinned VPN image",
    "invalid vpn port declaration": "VPN port schema",
    "vpn ports must use explicit host-IP mappings": "VPN port binding type",
    "vpn cannot publish ports beyond host loopback": "VPN loopback-only port publishing",
    "invalid service network declaration": "VPN network structure",
    "VPN original default network missing": "VPN default network",
    "VPN private ingress network missing": "VPN private ingress",
    "owned auth network omitted from effective VPN Compose configuration": "owned-auth bridge attachment",
}



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

    # Normal web releases MUST NOT activate the disposable PG18 auth backend,
    # change the authoritative SQLite path, or silently enable unapproved
    # live OAuth discovery. The PG18 auth cutover needs its own reviewed gate.
    env = object_value(web.get("environment"), "web environment missing")
    require(env.get("PANADAN_AUTH_DB") == "/data/auth.sqlite",
            "live SQLite authority must retain its persistent /data path")
    require(env.get("PANADAN_AUTH_BACKEND", "sqlite") in ("", "sqlite"),
            "production web release must retain SQLite authentication")
    for key in ("PANADAN_AUTH_STAGING_ENABLE", "PANADAN_AUTH_STAGING_ISOLATED",
                "PANADAN_AUTH_STAGING_DSN"):
        require(not env.get(key), "disposable staging credentials in live environment")
    require(env.get("PANADAN_MCP_AUTH_MODE", "legacy") in ("", "legacy"),
            "unapproved MCP OAuth mode on routine web release")
    volumes = web.get("volumes") or []
    require(isinstance(volumes, list), "web authentication volume declaration missing")
    auth_mounts = [v for v in volumes if isinstance(v, dict) and v.get("target") == "/data"]
    require(len(auth_mounts) == 1
            and auth_mounts[0].get("type") == "volume"
            and bool(auth_mounts[0].get("source"))
            and not auth_mounts[0].get("read_only", False),
            "web SQLite /data must be backed by a persistent writable named volume")

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


def validate_private_networks(data: object) -> None:
    require(isinstance(data, list) and len(data) == 2,
            "expected edge and ingress private networks")
    networks = {
        n.get("Name"): n for n in data
        if isinstance(n, dict) and isinstance(n.get("Name"), str)
    }
    require(set(networks) == {"panadan-edge", "panadan-ingress"},
            "wrong private production network names")
    expected = {
        "panadan-edge": {"plane-app-proxy-1", "panadan-edge-gateway-gateway-1"},
        "panadan-ingress": {"panadan-edge-gateway-gateway-1", "panadan-vpn-1"},
    }
    for name, members in expected.items():
        net = networks[name]
        require(net.get("Driver") == "bridge" and net.get("Internal") is True,
                "production bridge must remain internal")
        containers = object_value(net.get("Containers"), "network membership absent")
        observed = {v.get("Name") for v in containers.values() if isinstance(v, dict)}
        require(observed == members, "private production network membership differs")


def validate_caddy_adapted(data: Mapping) -> None:
    """Inspect Caddy's adapted HTTP host matchers, not raw Caddyfile syntax.

    Plain-text site-block regexes miss valid Caddy routes defined through
    imports, environment expansion, and alternative site address forms.
    Adaptation must happen on the reviewed mounted Caddyfile; this function
    never accepts arbitrary JSON fields as proof of a routed hostname.
    """
    apps = object_value(data.get("apps"), "Caddy apps missing")
    http = object_value(apps.get("http"), "Caddy HTTP app missing")
    servers = object_value(http.get("servers"), "Caddy HTTP servers missing")
    require(bool(servers), "no Caddy HTTP servers")
    hosts: set[str] = set()

    def visit_routes(routes: object, depth: int = 0) -> None:
        require(depth < 32, "Caddy nested route limit exceeded")
        require(isinstance(routes, list), "invalid Caddy routes")
        for route_raw in routes:
            route = object_value(route_raw, "invalid Caddy route")
            matchers = route.get("match", [])
            require(isinstance(matchers, list), "invalid Caddy route match")
            for matcher_raw in matchers:
                matcher = object_value(matcher_raw, "invalid Caddy matcher")
                match_hosts = matcher.get("host", [])
                require(isinstance(match_hosts, list), "invalid Caddy host matcher")
                for host in match_hosts:
                    if isinstance(host, str):
                        hosts.add(host)
            handlers = route.get("handle", [])
            require(isinstance(handlers, list), "invalid Caddy handlers")
            for handler_raw in handlers:
                handler = object_value(handler_raw, "invalid Caddy handler")
                if handler.get("handler") == "subroute":
                    visit_routes(handler.get("routes", []), depth + 1)

    for server_raw in servers.values():
        server = object_value(server_raw, "invalid Caddy HTTP server")
        visit_routes(server.get("routes", []))
    require({"plane.panafor.com", "dan.panafor.com"} <= hosts,
            "both Plane and Panadan explicit Caddy host matchers required")


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: validate_production_compose.py panadan|plane|gateway|auth-network|private-networks|caddy-adapted [--auth] [--explain-safe]", file=sys.stderr)
        return 2
    part = sys.argv[1]
    flags = sys.argv[2:]
    if part == "panadan":
        if len(flags) != len(set(flags)) or any(f not in ("--auth", "--explain-safe") for f in flags):
            print("REFUSED: invalid validator arguments", file=sys.stderr)
            return 2
    elif flags:
        print("REFUSED: invalid validator arguments", file=sys.stderr)
        return 2
    try:
        data = json.load(sys.stdin)
        if part == "caddy-adapted":
            validate_caddy_adapted(object_value(data, "invalid Caddy JSON"))
        else:
            if part == "panadan":
                validate_panadan(object_value(data, "invalid Compose file"),
                                 auth_enabled="--auth" in flags)
            else:
                if part == "plane":
                    validate_plane(object_value(data, "invalid Compose file"))
                elif part == "gateway":
                    validate_gateway(object_value(data, "invalid Compose file"))
                elif part == "auth-network":
                    validate_auth_network(data)
                elif part == "private-networks":
                    validate_private_networks(data)
                else:
                    raise InvalidDeployment("unknown component")
    except (ValueError, KeyError, TypeError, StopIteration) as exc:
        # Never print raw exception text, JSON, interpolated environment,
        # container metadata, sensitive mount paths or operator configuration.
        print(f"REFUSED: {part} production topology did not pass safety checks", file=sys.stderr)
        if part == "panadan" and "--explain-safe" in flags:
            reason = SAFE_PANADAN_CHECKS.get(str(exc), "unspecified invariant")
            print(f"SAFE CHECK: {reason}", file=sys.stderr)
        return 1
    print(f"PASS: {part} production topology safety checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
