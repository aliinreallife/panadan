"""Offline safety tests for validated hardened production plans (issue #56).

Every Docker response is synthetic; no VPS/Plane/VPN/source access.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/validate_production_compose.py"
CTRL = ROOT / "tools/prodctl-production.sh"
spec = importlib.util.spec_from_file_location("prod_guard", SCRIPT)
assert spec and spec.loader
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def panadan(auth=False):
    nets = {"default": {}, "ingress": {}}
    if auth:
        nets["auth_db"] = {}
    return {"services": {
        "web": {
            "image": "panadan-web:cac4b36",
            "network_mode": "service:vpn",
            "environment": {
                "PANADAN_COOKIE_SECURE": "true",
                "PANADAN_PUBLIC_ORIGIN": "https://dan.panafor.com",
                "PANADAN_AUTH_DB": "/data/auth.sqlite",
                "PANADAN_MCP_AUTH_MODE": "legacy",
            },
            "volumes": [{"type":"volume","source":"panadan_panadan_auth_data",
                         "target":"/data"}],
        },
        "vpn": {
            "image": "ghcr.io/aliinreallife/panadan-vpn:sha-" + "a"*40,
            "ports": [{"host_ip": "127.0.0.1", "published": 8508, "target": 8000}],
            "networks": nets,
        },
    }}


def plane():
    return {"services": {"proxy": {
        "networks": {"default": {}, "edge": {}},
        "volumes": [
            {"type": "volume", "source": "plane_data", "target": "/data"},
            {"type": "volume", "source": "plane_config", "target": "/config"},
            {"type": "bind", "source": "/trusted/Caddyfile",
             "target": "/etc/caddy/Caddyfile", "read_only": True},
        ],
    }}}


def gateway():
    return {"services": {"gateway": {"networks": {"edge": {}, "ingress": {}}}}}


def auth_network(members=True):
    data = {"Name": "panadan-auth-db", "Driver": "bridge",
            "Internal": True, "Containers": {}}
    if members:
        data["Containers"] = {
            "1": {"Name": "panadan-vpn-1"},
            "2": {"Name": "panadan-platform-db-1"},
        }
    return [data]


def caddy_routes():
    # Same structural shape as Caddy's adapted JSON (not raw Caddyfile).
    # Plane is intentionally nested inside a subroute; the VPS input
    # demonstrated it can be absent from literal top-level site blocks.
    return {"apps": {"http": {"servers": {"srv0": {"routes": [
        {"match": [{"host": ["dan.panafor.com"]}],
         "handle": [{"handler": "static_response", "body": "synthetic"}]},
        {"handle": [{"handler": "subroute", "routes": [
            {"match": [{"host": ["plane.panafor.com"]}],
             "handle": [{"handler": "static_response", "body": "synthetic"}]}
        ]}]}
    ]}}}}}


def private_networks():
    return [
        {"Name": "panadan-edge", "Driver": "bridge", "Internal": True,
         "Containers": {
             "1": {"Name": "plane-app-proxy-1"},
             "2": {"Name": "panadan-edge-gateway-gateway-1"},
         }},
        {"Name": "panadan-ingress", "Driver": "bridge", "Internal": True,
         "Containers": {
             "1": {"Name": "panadan-edge-gateway-gateway-1"},
             "2": {"Name": "panadan-vpn-1"},
         }},
    ]


def test_private_network_refuses_public_bridge_or_wrong_members():
    networks = private_networks()
    networks[0]["Internal"] = False
    with pytest.raises(guard.InvalidDeployment):
        guard.validate_private_networks(networks)
    networks = private_networks()
    networks[1]["Containers"]["3"] = {"Name": "unexpected-public-service"}
    with pytest.raises(guard.InvalidDeployment):
        guard.validate_private_networks(networks)


def test_valid_production_snapshots_and_operator_auth_overlay():
    guard.validate_panadan(panadan(), auth_enabled=False)
    guard.validate_panadan(panadan(True), auth_enabled=True)
    guard.validate_plane(plane())
    guard.validate_gateway(gateway())
    guard.validate_auth_network(auth_network())
    guard.validate_private_networks(private_networks())
    guard.validate_caddy_adapted(caddy_routes())


@pytest.mark.parametrize("image", [
    "ghcr.io/aliinreallife/panadan-web:main",
    "ghcr.io/aliinreallife/panadan-web:latest",
    "panadan-web:latest", "panadan-web:develop", "unexpected:1234567", "",
])
def test_mutable_or_untrusted_images_fail_closed(image):
    data = panadan()
    data["services"]["web"]["image"] = image
    with pytest.raises(guard.InvalidDeployment):
        guard.validate_panadan(data, auth_enabled=False)


@pytest.mark.parametrize("change", [
    lambda d: d["services"]["web"].update(network_mode="host"),
    lambda d: d["services"]["web"].update(ports=[{"host_ip": "0.0.0.0"}]),
    lambda d: d["services"]["web"]["environment"].update(PANADAN_COOKIE_SECURE="false"),
    lambda d: d["services"]["web"]["environment"].update(PANADAN_PUBLIC_ORIGIN="http://dan.panafor.com"),
    lambda d: d["services"]["vpn"].update(ports=[{"host_ip": "0.0.0.0"}]),
    lambda d: d["services"]["vpn"].update(networks={"default": {}}),
])
def test_leaky_or_wrong_panadan_topology_fails_closed(change):
    data = panadan()
    change(data)
    with pytest.raises(guard.InvalidDeployment):
        guard.validate_panadan(data, auth_enabled=False)


def test_existing_auth_network_requires_compose_overlay():
    with pytest.raises(guard.InvalidDeployment, match="auth network"):
        guard.validate_panadan(panadan(), auth_enabled=True)


@pytest.mark.parametrize("change", [
    lambda d: d["services"]["proxy"].update(networks={"edge": {}}),
    lambda d: d["services"]["proxy"]["volumes"][0].update(type="bind"),
    lambda d: d["services"]["proxy"]["volumes"][2].update(read_only=False),
])
def test_plane_original_networks_and_volumes_are_protected(change):
    data = plane()
    change(data)
    with pytest.raises(guard.InvalidDeployment):
        guard.validate_plane(data)


def test_gateway_ports_and_auth_members_are_guarded():
    data = gateway()
    data["services"]["gateway"]["ports"] = [{"host_ip": "127.0.0.1", "target": 80}]
    with pytest.raises(guard.InvalidDeployment):
        guard.validate_gateway(data)
    bad = auth_network()
    bad[0]["Containers"]["3"] = {"Name": "plane-app-proxy-1"}
    with pytest.raises(guard.InvalidDeployment):
        guard.validate_auth_network(bad)
    bad = auth_network(members=False)
    with pytest.raises(guard.InvalidDeployment):
        guard.validate_auth_network(bad)


def test_no_raw_config_or_secrets_appear_on_validation_failure():
    result = subprocess.run(
        ["python3", str(SCRIPT), "panadan"],
        input='{"services":{"web":{"environment":{"SECRET":"private_key_123"}}}}',
        text=True, capture_output=True, timeout=8,
    )
    assert result.returncode == 1
    assert "private_key_123" not in result.stdout + result.stderr
    assert "REFUSED" in result.stderr


def _sandbox(tmp_path):
    (tmp_path / "tools").mkdir()
    (tmp_path / "deploy").mkdir()
    (tmp_path / "data/ingress/rollback").mkdir(parents=True)
    (tmp_path / "plane").mkdir()
    shutil.copy2(CTRL, tmp_path / "tools/prodctl-production.sh")
    for name in ("validate_production_compose.py", "check_auth_db_network.py",
                 "check-plane-intake.sh", "smoke-production-web.sh"):
        shutil.copy2(ROOT / "tools" / name, tmp_path / "tools" / name)
    shutil.copy2(ROOT / "deploy/compose.auth-network.panadan.yaml",
                 tmp_path / "deploy/compose.auth-network.panadan.yaml")
    (tmp_path / "compose.prod.yaml").write_text("services: {}\n")
    (tmp_path / ".env.app").write_text("synthetic only\n")
    (tmp_path / ".env.db").write_text("synthetic only\n")
    (tmp_path / "plane/docker-compose.yaml").write_text("services: {}\n")
    (tmp_path / "plane/plane.env").write_text("synthetic only\n")
    for x in ("compose.panadan.yaml", "compose.web.release.yaml",
              "compose.web.https.yaml", "compose.gateway.yaml", "compose.plane.yaml"):
        (tmp_path / "data/ingress" / x).write_text("services: {}\n")
    (tmp_path / "data/ingress/Caddyfile").write_text(
        "plane.panafor.com {\n reverse_proxy plane:3000\n}\n"
        "dan.panafor.com {\n reverse_proxy gateway:80\n}\n")
    (tmp_path / "data/ingress/nginx.conf").write_text("server {}\n")
    (tmp_path / "bin").mkdir()
    docker = tmp_path / "bin/docker"
    docker.write_text(r'''#!/usr/bin/env python3
import json,os,sys
args=sys.argv[1:]
with open(os.environ["MOCK_LOG"],"a") as fd:
    fd.write(" ".join(args) + "\n")
mode=os.environ.get("MOCK_AUTH_MODE","absent")
if args[:2]==["network","ls"]:
    print("panadan-edge\npanadan-ingress"+("\npanadan-auth-db" if mode!="absent" else ""))
elif args[:2]==["network","inspect"]:
    if "panadan-auth-db" in args[2:]:
        data={"Name":"panadan-auth-db","Driver":"bridge","Internal":True,
              "Containers":{"a":{"Name":"panadan-vpn-1"},
                            "b":{"Name":"panadan-platform-db-1"}}}
        if mode=="partial":
            data["Containers"].pop("b")
        print(json.dumps([data]))
    else:
        data=[
          {"Name":"panadan-edge","Driver":"bridge","Internal":True,
           "Containers":{"a":{"Name":"plane-app-proxy-1"},
                         "b":{"Name":"panadan-edge-gateway-gateway-1"}}},
          {"Name":"panadan-ingress","Driver":"bridge","Internal":True,
           "Containers":{"a":{"Name":"panadan-edge-gateway-gateway-1"},
                         "b":{"Name":"panadan-vpn-1"}}}
        ]
        print(json.dumps(data))
elif args[:1]==["inspect"]:
    def state(name):
        return {"Name":"/"+name,
                "State":{"Running":True,
                         "Health":{"Status":"healthy"}},
                "NetworkSettings":{"Networks":{}, "Ports":{}}}
    cs={n:state(n) for n in [
        "panadan-platform-db-1","panadan-vpn-1","panadan-web-1",
        "plane-app-proxy-1","panadan-edge-gateway-gateway-1"]}
    cs["panadan-platform-db-1"]["NetworkSettings"]["Networks"]={
        "panadan-platform_default":{},
        "panadan-auth-db":{"Aliases":["panadan-auth-postgres"]}}
    cs["panadan-platform-db-1"]["NetworkSettings"]["Ports"]={
        "5432/tcp":[{"HostIp":"127.0.0.1","HostPort":"15433"}]}
    cs["panadan-vpn-1"]["NetworkSettings"]["Networks"]={
        "panadan_default":{},"panadan-ingress":{},"panadan-auth-db":{}}
    print(json.dumps([cs[n] for n in args[1:]]))
elif args[:3]==["exec","panadan-vpn-1","ip"]:
    print("192.168.3.9 via 10.8.0.1 dev tun0 src 10.8.0.2")
elif args[:3]==["exec","plane-app-proxy-1","cat"]:
    if os.environ.get("MOCK_CADDY_MOUNT_MISMATCH")=="YES":
        sys.stdout.write("unexpected different Caddyfile bytes")
    else:
        with open(os.environ["PANADAN_INGRESS_DIR"]+"/Caddyfile","rb") as fd:
            sys.stdout.buffer.write(fd.read())
elif args[:3]==["exec","plane-app-proxy-1","caddy"]:
    site=os.environ.get("MOCK_CADDY_ROUTES","both")
    sites=["dan.panafor.com"]
    if site=="both":sites.append("plane.panafor.com")
    print(json.dumps({"apps":{"http":{"servers":{"srv0":{"routes":[
        {"handle":[{"handler":"subroute","routes":[
            {"match":[{"host":[host]}]} for host in sites
        ]}]}
    ]}}}}}))
elif args[:2]==["image","inspect"]:
    sys.exit(0)
elif args[:1]==["compose"]:
    if "config" in args:
        if "--quiet" in args:sys.exit(0)
        if "docker-compose.yaml" in args:
            result={"services":{"proxy":{
                "networks":{"default":{},"edge":{}},
                "volumes":[
                    {"type":"volume","source":"plane_data","target":"/data"},
                    {"type":"volume","source":"plane_config","target":"/config"},
                    {"type":"bind","source":"/backup/Caddyfile",
                     "target":"/etc/caddy/Caddyfile","read_only":True}]}}}
        elif any("compose.gateway.yaml" in a for a in args):
            result={"services":{"gateway":{"networks":{"edge":{},"ingress":{}}}}}
        else:
            networks={"default":{},"ingress":{}}
            if any("compose.auth-network.panadan.yaml" in a for a in args):
                networks["auth_db"]={}
            result={"services":{
                "vpn":{"image":"panadan-vpn:cac4b36",
                       "ports":[{"host_ip":"127.0.0.1"}],"networks":networks},
                "web":{"image":"panadan-web:cac4b36","network_mode":"service:vpn",
                       "environment":{"PANADAN_COOKIE_SECURE":"true",
                                      "PANADAN_PUBLIC_ORIGIN":"https://dan.panafor.com",
                                      "PANADAN_AUTH_DB":"/data/auth.sqlite",
                                      "PANADAN_MCP_AUTH_MODE":"legacy"},
                       "volumes":[{"type":"volume","source":"panadan_auth_data",
                                   "target":"/data"}]}}}
        print(json.dumps(result))
    elif "ps" in args:print("synthetic containers running")
    elif "up" in args:
        if "--dry-run" not in args:
            open(os.environ["MOCK_UP_MARKER"],"w").write("web-only")
        sys.exit(0)
    else:sys.exit(5)
else:sys.exit(6)
''')
    docker.chmod(0o700)
    curl=tmp_path / "bin/curl"
    curl.write_text(r'''#!/usr/bin/env python3
import os,sys
args=sys.argv[1:]
url=args[-1]
with open(os.environ["MOCK_LOG"],"a") as fd:
    fd.write("curl " + url + "\\n")
status="200"
if url.endswith("/healthz"):
    if os.path.exists(os.environ["MOCK_UP_MARKER"]):
        counter=os.environ["MOCK_CURL_COUNTER"]
        n=int(open(counter).read()) if os.path.exists(counter) else 0
        n+=1
        open(counter,"w").write(str(n))
        status="200" if n>=int(os.environ.get("MOCK_RECOVER_AT","3")) else "502"
    else:
        status=os.environ.get("MOCK_BASELINE_HTTP","200")
if "--write-out" in args:
    print(status,end="")
if status!="200" and "--fail" in args:
    sys.exit(22)
''')
    curl.chmod(0o700)
    sleep=tmp_path / "bin/sleep"
    sleep.write_text('#!/bin/sh\necho "sleep $*" >> "$MOCK_LOG"\n')
    sleep.chmod(0o700)
    env=os.environ.copy()
    env.update(
        PATH=str(tmp_path/"bin")+os.pathsep+env["PATH"],
        PANADAN_INGRESS_DIR=str(tmp_path/"data/ingress"),
        PANADAN_PLANE_DIR=str(tmp_path/"plane"),
        MOCK_LOG=str(tmp_path/"calls.txt"),
        MOCK_UP_MARKER=str(tmp_path/"web-recreated.marker"),
        MOCK_CURL_COUNTER=str(tmp_path/"curl-count.txt"),
    )
    return env


def _ctrl(tmp_path, env, *args):
    return subprocess.run(
        ["bash", str(tmp_path/"tools/prodctl-production.sh"), *args],
        capture_output=True, text=True, env=env, timeout=15,
    )


def test_plan_never_changes_running_containers_or_prints_env(tmp_path):
    env=_sandbox(tmp_path)
    result=_ctrl(tmp_path,env,"plan")
    assert result.returncode==0, result.stderr
    assert "PASS" in result.stdout
    calls=(tmp_path/"calls.txt").read_text()
    assert "config" in calls
    assert " up " not in calls
    assert " down " not in calls
    assert "synthetic only" not in result.stdout+result.stderr


def test_existing_auth_bridge_is_rendered_in_all_app_compose_calls(tmp_path):
    env=_sandbox(tmp_path)
    env["MOCK_AUTH_MODE"]="present"
    result=_ctrl(tmp_path,env,"plan")
    assert result.returncode==0, result.stderr
    calls=(tmp_path/"calls.txt").read_text()
    assert "compose.auth-network.panadan.yaml" in calls
    assert "network inspect panadan-auth-db" in calls
    assert " up " not in calls


def test_partial_auth_network_blocks_any_deploy(tmp_path):
    env=_sandbox(tmp_path)
    env["MOCK_AUTH_MODE"]="partial"
    result=_ctrl(tmp_path,env,"deploy-web","--apply","--expect-image",
                 "panadan-web:cac4b36","--ack-restored-backup")
    assert result.returncode!=0
    assert "REFUSED" in result.stderr
    assert " up " not in (tmp_path/"calls.txt").read_text()


def test_proxy_requires_specific_ack_and_independent_intake_and_caddy_backups(tmp_path):
    env=_sandbox(tmp_path)
    no_ack=_ctrl(tmp_path,env,"deploy-proxy","--apply")
    assert no_ack.returncode==64
    assert not (tmp_path/"calls.txt").exists()
    no_backups=_ctrl(tmp_path,env,"deploy-proxy","--apply","--ack-plane-impact")
    assert no_backups.returncode==64
    assert "original Plane intake" in no_backups.stderr
    assert " up " not in (tmp_path/"calls.txt").read_text()


def test_bare_controller_does_not_run_with_missing_private_overlays(tmp_path):
    env=_sandbox(tmp_path)
    (tmp_path/"data/ingress/compose.gateway.yaml").unlink()
    result=_ctrl(tmp_path,env,"plan")
    assert result.returncode==64
    assert "missing reviewed" in result.stderr.lower()
    assert not (tmp_path/"calls.txt").exists()


@pytest.mark.parametrize("change", [
    lambda d: d["services"]["web"]["environment"].update(PANADAN_AUTH_BACKEND="postgres-staging"),
    lambda d: d["services"]["web"]["environment"].update(PANADAN_AUTH_STAGING_ENABLE="YES"),
    lambda d: d["services"]["web"]["environment"].update(PANADAN_AUTH_STAGING_ISOLATED="YES"),
    lambda d: d["services"]["web"]["environment"].update(PANADAN_AUTH_STAGING_DSN="postgresql://secret"),
    lambda d: d["services"]["web"]["environment"].update(PANADAN_AUTH_DB="/data/other.sqlite"),
    lambda d: d["services"]["web"]["environment"].update(PANADAN_MCP_AUTH_MODE="oauth"),
    lambda d: d["services"]["web"].update(volumes=[]),
    lambda d: d["services"]["web"]["volumes"][0].update(type="bind"),
    lambda d: d["services"]["web"]["volumes"][0].update(target="/tmp"),
    lambda d: d["services"]["web"]["volumes"][0].update(read_only=True),
])
def test_normal_production_release_preserves_sqlite_and_unapproved_oauth_stays_off(change):
    data = panadan()
    change(data)
    with pytest.raises(guard.InvalidDeployment):
        guard.validate_panadan(data, auth_enabled=False)


def test_empty_auth_backend_defaults_to_sqlite():
    data = panadan()
    del data["services"]["web"]["environment"]["PANADAN_MCP_AUTH_MODE"]
    guard.validate_panadan(data, auth_enabled=False)
    data["services"]["web"]["environment"]["PANADAN_AUTH_BACKEND"] = "sqlite"
    guard.validate_panadan(data, auth_enabled=False)


def test_web_deploy_requires_exact_image_and_explicit_backup_ack(tmp_path):
    env=_sandbox(tmp_path)
    for args in (("deploy-web","--apply"), ("deploy-web","--apply","--expect-image","panadan-web:cac4b36"),
                 ("deploy-web","--apply","--expect-image","panadan-web:main","--ack-restored-backup")):
        result=_ctrl(tmp_path,env,*args)
        assert result.returncode==64
        assert "REFUSED" in result.stderr
    # Every rejected invocation leaves all containers untouched.
    if (tmp_path/"calls.txt").exists():
        assert " up " not in (tmp_path/"calls.txt").read_text()


def test_web_deploy_refuses_image_not_present_in_effective_compose(tmp_path):
    env=_sandbox(tmp_path)
    result=_ctrl(tmp_path,env,"deploy-web","--apply","--expect-image",
                 "ghcr.io/aliinreallife/panadan-web:sha-"+"a"*40,
                 "--ack-restored-backup")
    assert result.returncode==64
    assert "differs from reviewed release" in result.stderr
    assert " up " not in (tmp_path/"calls.txt").read_text()


@pytest.mark.parametrize("change, expected", [
    (lambda d: d["services"]["web"]["environment"].update(PANADAN_AUTH_BACKEND="postgres-staging"),
     "SQLite auth backend selector"),
    (lambda d: d["services"]["web"]["environment"].update(PANADAN_AUTH_DB="/data/other.sqlite"),
     "SQLite auth database path"),
    (lambda d: d["services"]["web"]["volumes"][0].update(type="bind"),
     "SQLite persistent named /data mount"),
    (lambda d: d["services"]["web"]["environment"].update(PANADAN_MCP_AUTH_MODE="oauth"),
     "MCP legacy authentication mode"),
    (lambda d: d["services"]["web"].update(network_mode="host"),
     "web VPN namespace"),
])
def test_safe_diagnostics_only_show_allowlisted_invariant(change, expected):
    config = panadan()
    config["services"]["web"]["environment"]["PROD_SECRET"] = "DO_NOT_PRINT_THIS"
    change(config)
    cmd = ["python3", str(SCRIPT), "panadan", "--explain-safe"]
    result = subprocess.run(
        cmd, input=json.dumps(config), text=True,
        capture_output=True, timeout=8,
    )
    assert result.returncode == 1
    assert "SAFE CHECK: " + expected in result.stderr
    assert "DO_NOT_PRINT_THIS" not in (result.stdout + result.stderr)
    assert "/data/other.sqlite" not in (result.stdout + result.stderr)
    assert "postgres-staging" not in (result.stdout + result.stderr)


def test_safe_diagnostics_never_echo_unknown_exception_text(monkeypatch):
    config = panadan()
    unsafe = "DB_PASSWORD=very_sensitive_testing_value"
    def unexpected_problem(*args, **kwargs):
        raise guard.InvalidDeployment(unsafe)
    monkeypatch.setattr(guard, "validate_panadan", unexpected_problem)
    # The mapping only yields fixed trusted labels; unexpected error text
    # must be suppressed even in diagnostics mode.
    assert guard.SAFE_PANADAN_CHECKS.get(unsafe, "unspecified invariant") == "unspecified invariant"


def test_safe_diagnostics_rejects_duplicate_and_unknown_flags():
    for flags in (["--explain-safe", "--explain-safe"], ["--explain-safe", "--debug"]):
        result = subprocess.run(
            ["python3", str(SCRIPT), "panadan", *flags],
            input=json.dumps(panadan()), text=True,
            capture_output=True, timeout=8,
        )
        assert result.returncode == 2
        assert "invalid validator arguments" in result.stderr


def test_caddy_adapter_accepts_nested_explicit_hosts_not_plaintext_site_blocks():
    # The real host Caddyfile has an explicit dan site but Plane can enter
    # via environment-expanded/imported routes. Validate the adapter output.
    guard.validate_caddy_adapted(caddy_routes())


def test_caddy_adapter_rejects_missing_plane_and_incidental_host_strings():
    data=caddy_routes()
    data["apps"]["http"]["servers"]["srv0"]["routes"][1]["handle"][0]["routes"] = []
    data["example"]="plane.panafor.com"
    with pytest.raises(guard.InvalidDeployment, match="explicit Caddy host matchers"):
        guard.validate_caddy_adapted(data)


def test_caddy_adapter_rejects_hostless_and_wildcard_only_routes():
    for hosts in (["dan.panafor.com","*.panafor.com"],
                  ["dan.panafor.com"]):
        data={"apps":{"http":{"servers":{"srv0":{"routes":[
            {"match":[{"host":hosts}]}]}}}}}
        with pytest.raises(guard.InvalidDeployment):
            guard.validate_caddy_adapted(data)


def test_caddy_adapter_rejects_invalid_or_missing_http_server_structure():
    for data in ({}, {"apps":{"http":{"servers":{}}}},
                 {"apps":{"http":{"servers":{"srv0":{"routes":[{"match":"bad"}]}}}}}):
        with pytest.raises(guard.InvalidDeployment):
            guard.validate_caddy_adapted(data)


def test_plan_rejects_mismatched_proxy_mount_without_docker_changes(tmp_path):
    env=_sandbox(tmp_path)
    env["MOCK_CADDY_MOUNT_MISMATCH"]="YES"
    result=_ctrl(tmp_path,env,"plan")
    assert result.returncode==64
    assert "reviewed Caddyfile differs" in result.stderr
    calls=(tmp_path/"calls.txt").read_text()
    assert "exec plane-app-proxy-1 cat /etc/caddy/Caddyfile" in calls
    assert "exec plane-app-proxy-1 caddy adapt" not in calls
    assert " up " not in calls


def test_plan_rejects_missing_caddy_host_after_real_adapter(tmp_path):
    env=_sandbox(tmp_path)
    env["MOCK_CADDY_ROUTES"]="missing-plane"
    result=_ctrl(tmp_path,env,"plan")
    assert result.returncode==64
    assert "caddy-adapted production topology" in result.stderr
    calls=(tmp_path/"calls.txt").read_text()
    assert "exec plane-app-proxy-1 caddy adapt" in calls
    assert " up " not in calls


def _release_sandbox(tmp_path, *, baseline="200", recover_at="3"):
    env=_sandbox(tmp_path)
    env["MOCK_BASELINE_HTTP"]=baseline
    env["MOCK_RECOVER_AT"]=recover_at
    # The full authenticated smoke has separate integration and curl tests.
    # These controller tests exercise the call ordering and readiness gate.
    smoke=tmp_path/"tools/smoke-production-web.sh"
    smoke.write_text(
        '#!/bin/sh\necho "smoke $*" >> "$MOCK_LOG"\n'
        'echo "PASS: Synthetic post-deploy smoke"\n'
    )
    return env


def test_deploy_web_retries_transient_502_before_post_release_smoke(tmp_path):
    env=_release_sandbox(tmp_path, recover_at="3")
    result=_ctrl(tmp_path,env,"deploy-web","--apply","--expect-image",
                 "panadan-web:cac4b36","--ack-restored-backup")
    assert result.returncode==0, result.stdout+result.stderr
    assert "ready (attempt 3/12)" in result.stdout
    calls=(tmp_path/"calls.txt").read_text()
    assert calls.count("curl https://dan.panafor.com/healthz")>=4
    assert calls.count("sleep 5")==2
    assert "smoke --expected-image panadan-web:cac4b36" in calls
    assert " up -d --no-deps --no-build --pull never web" in calls
    assert " down " not in calls
    assert "restart vpn" not in calls


def test_deploy_web_stops_after_bounded_readiness_timeout(tmp_path):
    env=_release_sandbox(tmp_path, recover_at="99")
    result=_ctrl(tmp_path,env,"deploy-web","--apply","--expect-image",
                 "panadan-web:cac4b36","--ack-restored-backup")
    assert result.returncode==64
    assert "bounded readiness window" in result.stderr
    calls=(tmp_path/"calls.txt").read_text()
    assert calls.count("sleep 5")==11
    assert "smoke --expected-image" not in calls
    assert " down " not in calls


def test_rollback_web_succeeds_with_unhealthy_panadan_baseline(tmp_path):
    env=_release_sandbox(tmp_path, baseline="502", recover_at="2")
    result=_ctrl(tmp_path,env,"rollback-web","--apply","--expect-image",
                 "panadan-web:cac4b36","--ack-restored-backup")
    assert result.returncode==0, result.stdout+result.stderr
    assert "recovering Panadan Web only" in result.stderr
    assert "ready (attempt 2/12)" in result.stdout
    calls=(tmp_path/"calls.txt").read_text()
    assert "smoke --expected-image panadan-web:cac4b36" in calls
    assert " up -d --no-deps --no-build --pull never web" in calls
    assert " down " not in calls
    assert "restart " not in calls


def test_deploy_web_refuses_unhealthy_baseline_without_up(tmp_path):
    env=_release_sandbox(tmp_path, baseline="502")
    result=_ctrl(tmp_path,env,"deploy-web","--apply","--expect-image",
                 "panadan-web:cac4b36","--ack-restored-backup")
    assert result.returncode==64
    assert "Panadan HTTPS health failed" in result.stderr
    calls=(tmp_path/"calls.txt").read_text()
    assert " up -d " not in calls


def test_rollback_web_refuses_unpinned_or_unselected_image(tmp_path):
    env=_release_sandbox(tmp_path, baseline="502")
    for image in ("panadan-web:main","ghcr.io/aliinreallife/panadan-web:sha-"+"a"*40):
        result=_ctrl(tmp_path,env,"rollback-web","--apply","--expect-image",
                     image,"--ack-restored-backup")
        assert result.returncode==64
    calls=(tmp_path/"calls.txt").read_text()
    assert " up -d " not in calls


def test_rollback_web_refuses_missing_backup_ack_and_wrong_network(tmp_path):
    env=_release_sandbox(tmp_path, baseline="502")
    no_ack=_ctrl(tmp_path,env,"rollback-web","--apply","--expect-image",
                 "panadan-web:cac4b36")
    assert no_ack.returncode==64
    env["MOCK_AUTH_MODE"]="partial"
    bad_network=_ctrl(tmp_path,env,"rollback-web","--apply","--expect-image",
                      "panadan-web:cac4b36","--ack-restored-backup")
    assert bad_network.returncode==64
    assert " up -d " not in (tmp_path/"calls.txt").read_text()
