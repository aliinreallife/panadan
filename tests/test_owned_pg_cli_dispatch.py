"""Synthetic production guard regressions. No Docker or live services."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def isolated_wrapper(tmp_path):
    shutil.copyfile(ROOT / "panadan.sh", tmp_path / "panadan.sh")
    (tmp_path / "tools").mkdir()
    (tmp_path / "data/ingress").mkdir(parents=True)
    return tmp_path


@pytest.mark.parametrize("command", ("up", "down"))
def test_bare_production_compose_refused_when_https_overlays_exist(isolated_wrapper, command):
    (isolated_wrapper / "data/ingress/compose.panadan.yaml").write_text(
        "services: {}\n"
    )
    p = subprocess.run(
        ["bash", str(isolated_wrapper / "panadan.sh"), command],
        capture_output=True, text=True, timeout=10,
    )
    assert p.returncode == 64
    assert "hardened production overlays" in p.stderr
    assert "reviewed production deployment controller" in p.stderr


def test_owned_pg_dispatch_does_not_load_source_db_or_run_compose(isolated_wrapper):
    entry = isolated_wrapper / "tools/setup-owned-auth-pg.sh"
    entry.write_text('#!/usr/bin/env bash\nprintf "OWNED-DB-DISPATCH %s\\n" "$1"\n')
    p = subprocess.run(
        ["bash", str(isolated_wrapper / "panadan.sh"), "owned-pg", "plan"],
        capture_output=True, text=True, timeout=10,
    )
    assert p.returncode == 0, p.stderr
    assert "OWNED-DB-DISPATCH plan" in p.stdout
