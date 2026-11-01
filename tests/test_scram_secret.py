"""Test local SCRAM derivation independently from PostgreSQL or Docker."""
import base64
import hashlib
import hmac
import importlib.util
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRAM_FILE = ROOT / "tools/scram_secret.py"


def _module():
    spec = importlib.util.spec_from_file_location("panadan_scram_secret", SCRAM_FILE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_scram_verifier_has_postgresql_format_and_valid_keys():
    raw = b"a" * 64
    salt = bytes(range(16))
    result = _module().verifier(raw, salt)
    assert result.startswith("SCRAM-SHA-256$4096:")
    assert raw.decode() not in result
    prefix, keys = result.removeprefix("SCRAM-SHA-256$").split("$")
    iterations, encoded_salt = prefix.split(":")
    stored_key, server_key = keys.split(":")
    assert int(iterations) == 4096
    assert base64.b64decode(encoded_salt) == salt
    salted = hashlib.pbkdf2_hmac("sha256", raw, salt, 4096)
    assert base64.b64decode(stored_key) == hashlib.sha256(
        hmac.digest(salted, b"Client Key", "sha256")
    ).digest()
    assert base64.b64decode(server_key) == hmac.digest(
        salted, b"Server Key", "sha256"
    )


def test_cli_uses_fresh_salts_and_never_prints_plaintext():
    raw = b"b" * 64
    results = [subprocess.run(
        [sys.executable, str(SCRAM_FILE)], input=raw,
        capture_output=True, timeout=10,
    ) for _ in range(2)]
    assert all(r.returncode == 0 and not r.stderr for r in results)
    assert results[0].stdout != results[1].stdout
    assert all(r.stdout.startswith(b"SCRAM-SHA-256$4096:") for r in results)
    assert all(raw not in r.stdout + r.stderr for r in results)


def test_cli_rejects_invalid_plaintext_without_echoing_it():
    invalid = [b"short", b"z" * 64, b"a" * 65, b"a" * 64 + b"\\n"]
    for raw in invalid:
        result = subprocess.run([sys.executable, str(SCRAM_FILE)],
                                input=raw, capture_output=True, timeout=10)
        assert result.returncode != 0
        assert b"SCRAM-SHA-256" not in result.stdout
        assert raw not in result.stdout + result.stderr
