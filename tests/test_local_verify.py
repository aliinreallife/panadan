"""Local verification tests use fake uv/npm/node and synthetic files only."""
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
VERIFY = ROOT / "tools/verify-local.sh"


def _project(tmp_path):
    tools = tmp_path / "tools"
    tools.mkdir()
    shutil.copyfile(VERIFY, tools / "verify-local.sh")
    (tmp_path / "static").mkdir()
    (tmp_path / "static/app.js").write_text("export const status = true;\n")
    (tmp_path / "uv.lock").write_text("offline-fixture\n")
    for filename in ("panadan.sh", "migrate-from-danf.sh", "start-vpn.sh"):
        (tmp_path / filename).write_text("#!/usr/bin/env bash\ntrue\n")
    (tools / "test-platform-integration.sh").write_text(
        '#!/usr/bin/env bash\nprintf "docker-synthetic\\n" >> "$MOCK_VERIFY_LOG"\n'
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("uv", "npm", "node"):
        stub = bin_dir / name
        stub.write_text(
            '#!/usr/bin/env bash\n'
            'set -euo pipefail\n'
            '# Every tool must run without inherited DB connection data.\n'
            '[[ -z "${PGHOST:-}" && -z "${PGPORT:-}" && -z "${PGUSER:-}" ]] || exit 67\n'
            '[[ -z "${PGPASSWORD:-}" && -z "${PGDATABASE:-}" ]] || exit 67\n'
            '[[ -z "${PANADAN_PLATFORM_TEST_DSN:-}" && -z "${PANADAN_PLATFORM_TEST_ALLOW_RESET:-}" ]] || exit 67\n'
            'printf "%s %s\\n" "' + name + '" "$*" >> "$MOCK_VERIFY_LOG"\n'
        )
        stub.chmod(0o700)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["MOCK_VERIFY_LOG"] = str(tmp_path / "verify.log")
    env["PGHOST"] = "not-a-real-source"
    env["PGPORT"] = "9999"
    env["PGUSER"] = "synthetic-do-not-connect"
    env["PGPASSWORD"] = "mock-do-not-connect"
    env["PGDATABASE"] = "mock-do-not-connect"
    env["PANADAN_PLATFORM_TEST_DSN"] = "not-a-real-platform"
    env["PANADAN_PLATFORM_TEST_ALLOW_RESET"] = "YES"
    return env


def test_verify_help_requires_no_services_or_dependencies(tmp_path):
    script = VERIFY
    result = subprocess.run(
        ["bash", str(script), "--help"], capture_output=True, text=True,
        cwd=tmp_path, timeout=10,
    )
    assert result.returncode == 0
    assert "--docker" in result.stdout and "--assets" in result.stdout


def test_default_verify_is_offline_and_checks_each_script(tmp_path):
    env = _project(tmp_path)
    result = subprocess.run(
        ["bash", "tools/verify-local.sh"], cwd=tmp_path,
        env=env, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert "PASSED" in result.stdout
    lines = (tmp_path / "verify.log").read_text().splitlines()
    assert "uv sync --locked --dev" in lines
    assert "uv run --locked python -m pytest -q" in lines
    assert "npm test" in lines
    assert "node --check static/app.js" in lines
    assert "docker-synthetic" not in lines
    assert not any("build" in item for item in lines)


def test_opt_in_docker_and_asset_build_stay_explicit(tmp_path):
    env = _project(tmp_path)
    result = subprocess.run(
        ["bash", "tools/verify-local.sh", "--docker", "--assets"], cwd=tmp_path,
        env=env, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    lines = (tmp_path / "verify.log").read_text().splitlines()
    assert "npm ci --no-audit --no-fund" in lines
    assert "npm run build" in lines
    assert "docker-synthetic" in lines


def test_unknown_argument_does_not_start_tests(tmp_path):
    env = _project(tmp_path)
    result = subprocess.run(
        ["bash", "tools/verify-local.sh", "--delete-data"], cwd=tmp_path,
        env=env, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode != 0
    assert not (tmp_path / "verify.log").exists()


def test_wrapper_dispatches_before_source_env_is_read():
    script = (ROOT / "panadan.sh").read_text()
    early = script.split("if [[ -f .env.app ]]; then", 1)[0]
    assert 'if [[ "$cmd" == "verify" ]]; then' in early
    assert 'exec bash tools/verify-local.sh "$@"' in early
    verify = VERIFY.read_text()
    assert "bash -n \"$script\"" in verify
    assert "node --check \"$script\"" in verify
    assert "tools/test-platform-integration.sh" in verify
    assert ".env.db" not in verify.split("usage()", 1)[0]
