"""Offline exact-byte guard for Plane's custom intake page (#62).

No actual web requests or Plane Docker operations: curl is a test-only fake.
"""
from pathlib import Path
import os
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/check-plane-intake.sh"


def _sandbox(tmp_path):
    (tmp_path / "tools").mkdir()
    (tmp_path / "bin").mkdir()
    (tmp_path / "private-tmp").mkdir()
    shutil.copyfile(SCRIPT, tmp_path / "tools/check-plane-intake.sh")
    fake = tmp_path / "bin/curl"
    fake.write_text(r'''#!/usr/bin/env python3
import os,pathlib,sys
a=sys.argv[1:]
with open(os.environ["MOCK_CURL_LOG"],"a") as f:f.write(" ".join(a) + "\n")
if os.environ.get("MOCK_OFFLINE"):
    sys.exit(7)
if "--output" not in a or "--write-out" not in a:
    sys.exit(2)
body=os.environ.get("MOCK_HTML","<html>original custom intake</html>").encode()
pathlib.Path(a[a.index("--output")+1]).write_bytes(body)
sys.stdout.write(os.environ.get("MOCK_HTTP_STATUS","200"))
''')
    fake.chmod(0o700)
    env = os.environ.copy()
    env.update(
        PATH=str(tmp_path / "bin") + os.pathsep + env["PATH"],
        TMPDIR=str(tmp_path / "private-tmp"),
        MOCK_CURL_LOG=str(tmp_path / "requests.log"),
    )
    original = tmp_path / "original-intake.html"
    original.write_text("<html>original custom intake</html>")
    return env, original


def _run(tmp_path, env, *args):
    return subprocess.run(
        ["bash", str(tmp_path / "tools/check-plane-intake.sh"), *args],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=10,
    )


def test_bash_syntax_and_fixed_public_https_no_docker():
    checked = subprocess.run(["bash","-n",str(SCRIPT)],capture_output=True,text=True,timeout=8)
    assert checked.returncode == 0, checked.stderr
    source = SCRIPT.read_text()
    assert 'https://plane.panafor.com/intake.html' in source
    assert "curl --fail" in source and "--proto '=https'" in source
    assert "HTTP_CODE" in source and '== "200"' in source
    assert "sha256sum" in source
    assert "docker " not in source
    assert "scp " not in source
    assert "--location" not in source


def test_fingerprint_is_read_only_and_not_mistaken_for_backup(tmp_path):
    env, _ = _sandbox(tmp_path)
    result = _run(tmp_path,env,"fingerprint")
    assert result.returncode == 0, result.stderr
    assert "SHA-256:" in result.stdout
    assert "NOT a backup" in result.stdout
    assert not list((tmp_path / "private-tmp").iterdir())
    assert "https://plane.panafor.com/intake.html" in (tmp_path / "requests.log").read_text()


def test_exact_trusted_copy_and_negative_content_mismatch(tmp_path):
    env, original = _sandbox(tmp_path)
    pass_result = _run(tmp_path,env,"verify",str(original))
    assert pass_result.returncode == 0, pass_result.stderr
    assert "PASS:" in pass_result.stdout
    env["MOCK_HTML"] = "<html>some different page</html>"
    fail_result = _run(tmp_path,env,"verify",str(original))
    assert fail_result.returncode != 0
    assert "mismatch" in fail_result.stderr
    assert "some different page" not in fail_result.stderr
    assert not list((tmp_path / "private-tmp").iterdir())


def test_missing_or_symlink_reference_fails_before_web_request(tmp_path):
    env, original = _sandbox(tmp_path)
    missing = _run(tmp_path,env,"verify",str(tmp_path/"missing.html"))
    assert missing.returncode != 0
    assert not (tmp_path / "requests.log").exists()
    target = tmp_path / "link.html"
    target.symlink_to(original)
    symlinked = _run(tmp_path,env,"verify",str(target))
    assert symlinked.returncode != 0
    assert not (tmp_path / "requests.log").exists()


def test_redirect_status_and_unreachable_endpoint_fail_closed(tmp_path):
    env, original = _sandbox(tmp_path)
    env["MOCK_HTTP_STATUS"] = "302"
    redirect = _run(tmp_path,env,"verify",str(original))
    assert redirect.returncode != 0
    assert "HTTP 200" in redirect.stderr
    env.pop("MOCK_HTTP_STATUS")
    env["MOCK_OFFLINE"] = "1"
    offline = _run(tmp_path,env,"verify",str(original))
    assert offline.returncode != 0
    assert "Cannot fetch" in offline.stderr
    assert not list((tmp_path / "private-tmp").iterdir())
