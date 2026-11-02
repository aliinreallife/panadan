"""Legacy production entrypoint must refuse hardened live Docker networks.

All Docker commands are test-only mocks. No VPN, VPS, or production secrets.
"""
from pathlib import Path
import os
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "panadan.sh"


def _sandbox(tmp_path, *, networks="", docker_exit=0):
    shutil.copyfile(WRAPPER, tmp_path / "panadan.sh")
    (tmp_path / "bin").mkdir()
    fake = tmp_path / "bin/docker"
    fake.write_text(r'''#!/usr/bin/env python3
import os,sys
with open(os.environ["MOCK_DOCKER_LOG"],"a") as f:
    f.write(" ".join(sys.argv[1:]) + "\n")
if sys.argv[1:]==["network","ls","--format","{{.Name}}"]:
    if os.environ.get("MOCK_FAIL_NETWORK")=="1":
        sys.exit(9)
    print(os.environ.get("MOCK_NETWORK_NAMES",""))
elif "compose" in sys.argv[1:]:
    print("UNEXPECTED compose invocation",file=sys.stderr)
    sys.exit(11)
else:
    sys.exit(12)
''')
    fake.chmod(0o700)
    env=os.environ.copy()
    env["PATH"]=str(tmp_path/"bin")+os.pathsep+env["PATH"]
    env["MOCK_DOCKER_LOG"]=str(tmp_path/"calls.log")
    env["MOCK_NETWORK_NAMES"]=networks
    if docker_exit:
        env["MOCK_FAIL_NETWORK"]="1"
    return env


@pytest.mark.parametrize("command", ["up", "down"])
@pytest.mark.parametrize("network", ["panadan-edge", "panadan-ingress", "panadan-auth-db"])
def test_live_private_network_refuses_bare_production_even_without_overlay(tmp_path, command, network):
    env=_sandbox(tmp_path, networks="unrelated\n"+network+"\nlocal-only")
    assert not (tmp_path / "data/ingress").exists()
    result=subprocess.run(["bash", str(tmp_path/"panadan.sh"), command],
                          capture_output=True,text=True,env=env,timeout=8)
    assert result.returncode==64
    assert "REFUSED" in result.stderr
    assert "hardened" in result.stderr.lower()
    calls=(tmp_path/"calls.log").read_text()
    assert calls.strip()=="network ls --format {{.Name}}"
    assert "UNEXPECTED" not in result.stderr


@pytest.mark.parametrize("command", ["up", "down"])
def test_failed_docker_network_inspection_refuses_closed(tmp_path, command):
    env=_sandbox(tmp_path, docker_exit=1)
    result=subprocess.run(["bash", str(tmp_path/"panadan.sh"),command],
                          capture_output=True,text=True,env=env,timeout=8)
    assert result.returncode==64
    assert "REFUSED" in result.stderr
    assert (tmp_path/"calls.log").read_text().count("network ls")==1


def test_no_private_network_does_not_trigger_hardened_early_guard(tmp_path):
    env=_sandbox(tmp_path, networks="bridge\nhost\nnone\n")
    result=subprocess.run(["bash", str(tmp_path/"panadan.sh"),"up"],
                          capture_output=True,text=True,env=env,timeout=8)
    # It now reaches the existing separate .env/Odoo config check. The fake
    # environment has no credentials, so starting Compose is still impossible.
    assert result.returncode!=64
    assert "Missing .env.db" in result.stderr
    assert "compose" not in (tmp_path/"calls.log").read_text()


@pytest.mark.parametrize("cmd", ["verify", "help"])
def test_non_production_commands_do_not_probe_docker_networks(tmp_path, cmd):
    env=_sandbox(tmp_path, networks="panadan-edge")
    # verify dispatches a missing tools/verify-local.sh in this sandbox, so
    # only ensure it never ran Docker during early routing.
    result=subprocess.run(["bash", str(tmp_path/"panadan.sh"),cmd],
                          capture_output=True,text=True,env=env,timeout=8)
    assert not (tmp_path/"calls.log").exists()
