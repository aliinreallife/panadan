"""Staging writer selector security tests: no customer data or real DB."""
from contextlib import contextmanager
from pathlib import Path
import os

import pytest

from server import odoo_mirror_target as target


def _staging(tmp_path: Path) -> dict[str, str]:
    dsn_file = tmp_path / "writer.dsn"
    dsn_file.write_text(
        "host=127.0.0.1 port=55432 dbname=panadan_ci "
        "user=panadan_ingest_writer password=synthetic-only "
        "sslmode=prefer",
        encoding="utf-8",
    )
    dsn_file.chmod(0o600)
    return {
        target.MODE_ENV: target.STAGING_MODE,
        target.STAGING_ACK: "YES",
        target.STAGING_DSN_FILE: str(dsn_file),
    }


def test_staging_writer_requires_private_file_and_exact_target(tmp_path):
    env = _staging(tmp_path)
    assert "panadan_ci" in target.validate_staging_writer_config(env)
    with pytest.raises(ValueError, match="requires explicit approval"):
        target.validate_staging_writer_config({**env, target.STAGING_ACK: "NO"})
    with pytest.raises(ValueError, match="requires explicit approval"):
        target.validate_staging_writer_config({
            **env, target.MODE_ENV: "production"})
    for modifier in [
        "host=192.168.3.9 port=5432 dbname=odoo user=report_user",
        "host=panadan-auth-postgres port=5432 dbname=panadan "
        "user=panadan_ingest_writer",
        "host=127.0.0.1 port=55432 dbname=panadan_ci user=postgres",
        "host=127.0.0.1 port=55432 dbname=panadan user=panadan_ingest_writer",
    ]:
        file = tmp_path / "writer.dsn"
        file.write_text(modifier + " password=synthetic-only sslmode=prefer",
                        encoding="utf-8")
        with pytest.raises(ValueError, match="loopback"):
            target.validate_staging_writer_config(env)
    _staging(tmp_path)
    dsn_file = tmp_path / "writer.dsn"
    dsn_file.chmod(0o644)
    with pytest.raises(ValueError, match="Private"):
        target.validate_staging_writer_config(env)
    dsn_file.chmod(0o600)
    link = tmp_path / "writer-symlink.dsn"
    link.symlink_to(dsn_file)
    with pytest.raises(ValueError, match="Private"):
        target.validate_staging_writer_config({
            **env, target.STAGING_DSN_FILE: str(link),
        })
    with pytest.raises(ValueError, match="environment redirect"):
        target.validate_staging_writer_config({
            **env, "PGHOSTADDR": "192.168.3.9",
        })


def test_staging_connection_enforces_pg_identity_and_never_falls_back(
        tmp_path, monkeypatch):
    env = _staging(tmp_path)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    for key in target._DSN_REDIRECT_ENV:
        monkeypatch.delenv(key, raising=False)

    calls = []
    @contextmanager
    def legacy():
        calls.append("legacy")
        yield object()

    class FakeResult:
        def __init__(self, record):
            self.record = record
        def fetchone(self):
            return self.record

    class FakeConnection:
        def __init__(self, identity):
            self.identity = identity
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def execute(self, statement):
            assert "current_database()" in statement
            return FakeResult(self.identity)

    identity = {
        "db": "panadan_ci", "role": "panadan_ingest_writer", "version": "180006",
    }

    def stage_connect(dsn, **kwargs):
        assert "dbname=panadan_ci" in dsn
        assert kwargs["autocommit"] is True
        assert "statement_timeout" in kwargs["options"]
        calls.append("staging")
        return FakeConnection(identity)

    monkeypatch.setattr(target.guarded, "owned_connection", legacy)
    monkeypatch.setattr(target.psycopg, "connect", stage_connect)

    with target.owned_connection() as conn:
        assert conn.identity is identity
    assert calls == ["staging"]
    identity["db"] = "panadan"
    with pytest.raises(PermissionError, match="identity"):
        with target.owned_connection():
            pass
    assert calls == ["staging", "staging"]

    monkeypatch.setenv(target.MODE_ENV, "incorrect")
    with pytest.raises(ValueError, match="Unsupported"):
        with target.owned_connection():
            pass
    assert calls == ["staging", "staging"]

    monkeypatch.delenv(target.MODE_ENV)
    with target.owned_connection():
        pass
    assert calls == ["staging", "staging", "legacy"]
