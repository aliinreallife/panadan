"""Generated frontend files must remain local, not in Git/Docker contexts."""
from pathlib import Path


def test_built_vendor_assets_are_ignored_completely():
    gitignore = Path(".gitignore").read_text()
    dockerignore = Path(".dockerignore").read_text()
    build = Path("web/build.mjs").read_text()
    assert "static/vendor/" in gitignore.splitlines()
    assert "static/vendor/" in dockerignore.splitlines()
    assert "static/vendor/panadan-bundle.js" in build
    assert "static/vendor/doran.css" in build


def test_local_dev_loads_generated_vendor_only_after_build():
    launcher = Path("panadan.sh").read_text()
    assert "static/vendor/panadan-bundle.js" in launcher
    assert "static/vendor/panadan-bundle.css" in launcher
