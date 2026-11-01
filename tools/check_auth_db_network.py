#!/usr/bin/env python3
"""Read-only audit of the private Panadan-to-owned-PostgreSQL network.

Never creates, connects, disconnects, restarts, or reconfigures containers.
Use --stage before before planned attachment, --stage after after attachment.
Does not inspect or print environment variables, credentials or database data.
"""
from __future__ import annotations

import argparse
import json
import subprocess

NET = "panadan-auth-db"
PG = "panadan-platform-db-1"
VPN = "panadan-vpn-1"
WEB = "panadan-web-1"
PROXY = "plane-app-proxy-1"
GATEWAY = "panadan-edge-gateway-gateway-1"


def docker(*args: str) -> str:
    return subprocess.run(
        ["docker", *args],
        check=True, text=True, capture_output=True, timeout=15
    ).stdout.strip()


def audit(containers: dict, network: dict | None, stage: str) -> list[str]:
    if stage not in {"before", "after"}:
        raise ValueError("Unexpected audit stage")

    for name in (PG, VPN, WEB, PROXY, GATEWAY):
        if name not in containers:
            raise ValueError(f"Required running container missing: {name}")
        if containers[name]["State"].get("Running") is not True:
            raise ValueError(f"Container not running: {name}")
    for name in (PG, VPN):
        if containers[name]["State"].get("Health", {}).get("Status") != "healthy":
            raise ValueError(f"Health check is not healthy: {name}")

    pg = containers[PG]
    vpn = containers[VPN]
    pg_nets = pg["NetworkSettings"]["Networks"]
    vpn_nets = vpn["NetworkSettings"]["Networks"]
    if "panadan-platform_default" not in pg_nets:
        raise ValueError("PostgreSQL has lost its original platform network")
    for required in ("panadan_default", "panadan-ingress"):
        if required not in vpn_nets:
            raise ValueError(f"VPN lost original network: {required}")

    bindings = (pg["NetworkSettings"].get("Ports") or {}).get("5432/tcp")
    if not bindings or any(b.get("HostIp") not in ("127.0.0.1", "::1") for b in bindings):
        raise ValueError("PostgreSQL 5432 must stay bound to loopback only")
    # Protect against an unexpected additional publicly published port.
    for mappings in (pg["NetworkSettings"].get("Ports") or {}).values():
        if mappings and any(b.get("HostIp") not in ("127.0.0.1", "::1") for b in mappings):
            raise ValueError("Unexpected non-loopback PostgreSQL port exposure")

    result = ["PASS: PostgreSQL/VPN healthy; original networks and loopback port retained"]

    if network is None:
        if stage == "after":
            raise ValueError(f"Required private network {NET} is missing")
        result.append("PASS: Proposed private network does not exist yet")
        return result

    if network.get("Name") != NET or network.get("Driver") != "bridge" or network.get("Internal") is not True:
        raise ValueError("Private network must be an internal Docker bridge")
    members = {c.get("Name") for c in (network.get("Containers") or {}).values()}
    allowed = {PG, VPN}
    if members - allowed:
        raise ValueError("Unexpected service attached to auth network: " + ", ".join(sorted(members-allowed)))
    result.append("PASS: Auth network is internal and has no gateway/Plane members")

    if stage == "before":
        if members:
            raise ValueError("Auth network already has members; use --stage after or inspect partial changes")
        result.append("PASS: Auth network exists but no containers have been attached")
    else:
        if members != allowed or NET not in pg_nets or NET not in vpn_nets:
            raise ValueError("Both PostgreSQL and VPN must be attached to the auth network")
        aliases = pg_nets[NET].get("Aliases") or []
        if "panadan-auth-postgres" not in aliases:
            raise ValueError("Required DNS alias panadan-auth-postgres missing")
        result.append("PASS: Only VPN + owned PostgreSQL attached, DB DNS alias present")
    return result


def run(stage: str) -> None:
    raw = json.loads(docker(
        "inspect", PG, VPN, WEB, PROXY, GATEWAY
    ))
    containers = {c["Name"].lstrip("/"): c for c in raw}
    networks = docker("network", "ls", "--format", "{{.Name}}").splitlines()
    network = None
    if NET in networks:
        network = json.loads(docker("network", "inspect", NET))[0]
    messages = audit(containers, network, stage)

    # This route must remain over tun0 for the external read-only Odoo DB.
    route = docker("exec", VPN, "ip", "-4", "route", "get", "192.168.3.9")
    if " dev tun0 " not in f" {route} ":
        raise ValueError("Odoo PostgreSQL routing no longer uses tun0")
    messages.append("PASS: Existing source Odoo route remains on tun0")
    print("\n".join(messages))
    print("NOTE: This is read-only topology verification, NOT a PostgreSQL TCP or role authentication test.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("before", "after"), required=True)
    args = parser.parse_args()
    try:
        run(args.stage)
    except (ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired, KeyError) as exc:
        # Never print secrets: Docker output/stderr may contain sensitive data.
        if isinstance(exc, (subprocess.CalledProcessError, subprocess.TimeoutExpired)):
            print("FAIL: Docker inspection command failed or timed out")
        else:
            print(f"FAIL: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
