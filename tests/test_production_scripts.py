"""Safe CLI regression tests: no Docker, production data, OAuth or network."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("command", ["up", "down"])
@pytest.mark.parametrize("overlay", [
    "compose.panadan.yaml", "compose.web.release.yaml", "compose.web.https.yaml",
])
def test_legacy_prod_commands_refuse_hardened_deployments(tmp_path, command, overlay):
    (tmp_path / "data/ingress").mkdir(parents=True)
    (tmp_path / "data/ingress" / overlay).write_text("services: {}\n")
    shutil.copy2(ROOT / "panadan.sh", tmp_path / "panadan.sh")
    result = subprocess.run(
        ["bash", str(tmp_path / "panadan.sh"), command],
        text=True, capture_output=True, timeout=8,
    )
    assert result.returncode == 64
    assert "REFUSED" in result.stderr
    assert "prodctl-production.sh" in result.stderr


@pytest.mark.parametrize("script", [
    "panadan.sh", "tools/prodctl-production.sh", "tools/backup-auth-offsite.sh",
])
def test_production_shell_syntax(script):
    result = subprocess.run(
        ["bash", "-n", str(ROOT / script)], capture_output=True, text=True,
        timeout=8,
    )
    assert result.returncode == 0, result.stderr


def test_controller_missing_files_fails_closed(tmp_path):
    source = ROOT / "tools/prodctl-production.sh"
    (tmp_path / "tools").mkdir()
    shutil.copy2(source, tmp_path / "tools/prodctl-production.sh")
    result = subprocess.run(
        ["bash", str(tmp_path / "tools/prodctl-production.sh"), "check"],
        text=True, capture_output=True, timeout=8,
        env={"PATH": "/usr/bin:/bin"},
    )
    assert result.returncode != 0
    assert "MISSING" in result.stderr


def test_backup_requires_age_recipient_and_offsite_remote(tmp_path):
    (tmp_path / "tools").mkdir()
    shutil.copy2(ROOT / "tools/backup-auth-offsite.sh",
                 tmp_path / "tools/backup-auth-offsite.sh")
    result = subprocess.run(
        ["bash", str(tmp_path / "tools/backup-auth-offsite.sh"), "--check"],
        text=True, capture_output=True, timeout=8,
    )
    assert result.returncode != 0
    assert "BACKUP FAILED" in result.stderr


def _smoke_mocks(tmp_path):
    """Only synthetic processes. No real Docker or public network access."""
    tools = tmp_path / "bin"
    tools.mkdir()
    docker = tools / "docker"
    docker.write_text("""#!/usr/bin/env python3
import os,sys
args=sys.argv[1:]
with open(os.environ["SMOKE_CALL_LOG"],"a") as fd:
    fd.write("docker " + " ".join(args) + "\\n")
if args[:1] == ["inspect"] and "panadan-web-1" in args:
    if "{{.Config.Image}}" in args: print(os.environ["SMOKE_IMAGE"])
    else: print("true")
elif args[:1] == ["inspect"] and "panadan-vpn-1" in args:
    print("healthy")
elif args[:3] == ["exec","panadan-vpn-1","ip"]:
    print("192.168.3.9 via 10.8.0.1 dev "
          + os.environ.get("SMOKE_ROUTE","tun0"))
else:
    sys.exit(70)
""")
    docker.chmod(0o755)
    curl = tools / "curl"
    curl.write_text("""#!/usr/bin/env python3
import os,sys
args=sys.argv[1:]
with open(os.environ["SMOKE_CALL_LOG"],"a") as fd:
    fd.write("curl " + args[-1] + "\\n")
site=args[-1]
if site.endswith("/api/v1/calls") or site.endswith("/mcp/"):
    code=os.environ.get("SMOKE_AUTH_STATUS","401")
else:
    code="200"
if "--dump-header" in args:
    path=args[args.index("--dump-header")+1]
    cookie="Secure; HttpOnly" if os.environ.get("SMOKE_BAD_COOKIE")!="YES" else "HttpOnly"
    with open(path,"w") as fd:
        fd.write("HTTP/2 200\\r\\nSet-Cookie: panadan_login_nonce=synthetic; "
                 + cookie + "; SameSite=Lax\\r\\n")
print(code,end="")
""")
    curl.chmod(0o755)
    return tools


def _run_smoke(tmp_path, monkeypatch, **overrides):
    tools = _smoke_mocks(tmp_path)
    logfile = tmp_path / "calls.log"
    env = os.environ.copy()
    env.update({
        "PATH": str(tools) + os.pathsep + env["PATH"],
        "SMOKE_CALL_LOG": str(logfile),
        "SMOKE_IMAGE": "ghcr.io/aliinreallife/panadan-web:sha-" + "a"*40,
    })
    env.update(overrides)
    script = ROOT / "tools/smoke-production-web.sh"
    result = subprocess.run(
        ["bash", str(script), "--expected-image", env["SMOKE_IMAGE"]],
        env=env, text=True, capture_output=True, timeout=10,
    )
    return result, logfile.read_text() if logfile.exists() else ""


def test_readonly_web_release_smoke_passes_without_mutating_command(tmp_path, monkeypatch):
    result, calls = _run_smoke(tmp_path, monkeypatch)
    assert result.returncode == 0, result.stderr
    assert "PASS: Production web" in result.stdout
    assert "running web container references the reviewed image" in result.stdout
    assert "docker exec panadan-vpn-1 ip -4 route get" in calls
    assert "curl https://plane.panafor.com/intake.html" in calls
    assert "curl https://dan.panafor.com/mcp/" in calls
    assert "docker compose" not in calls and "docker rm" not in calls
    assert "docker restart" not in calls and "docker up" not in calls


@pytest.mark.parametrize("env_key,value", [
    ("SMOKE_AUTH_STATUS","200"),
    ("SMOKE_ROUTE","eth0"),
    ("SMOKE_BAD_COOKIE","YES"),
])
def test_readonly_web_release_smoke_rejects_missing_security_property(
    tmp_path, monkeypatch, env_key, value
):
    result, calls = _run_smoke(tmp_path, monkeypatch, **{env_key:value})
    assert result.returncode != 0
    assert "FAIL:" in result.stderr
    assert "docker restart" not in calls


def test_web_release_smoke_rejects_mutable_expected_tag_without_calls(tmp_path):
    result = subprocess.run(
        ["bash", str(ROOT / "tools/smoke-production-web.sh"),
         "--expected-image", "ghcr.io/aliinreallife/panadan-web:main"],
        text=True, capture_output=True, timeout=8,
    )
    assert result.returncode != 0
    assert "pinned" in result.stderr
