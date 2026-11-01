"""Auth migration: isolated SQLite snapshots and disposable PostgreSQL 18 only.

No real credentials, customer records, VPN or production database are accessed.
The PostgreSQL test is opt-in and only permitted against panadan_ci loopback.
"""
import os
from pathlib import Path
import sqlite3

import psycopg
from psycopg.conninfo import conninfo_to_dict
import pytest

from server.auth_pg_migration import (
    inspect_snapshot, import_into_disposable, validate_disposable_target,
)
from server.security import Store


@pytest.fixture
def snapshot(tmp_path):
    live=tmp_path/"synthetic-live.sqlite"
    store=Store(str(live))
    store.bootstrap("synthetic_admin","synthetic-test-admin-password-very-long")
    admin=store.verify_login("synthetic_admin","synthetic-test-admin-password-very-long")
    analyst=store.create_user(
        "synthetic_analyst","synthetic-test-analyst-password-very-long",
        "analyst",["calls:read","metrics:read","mcp:use"]
    )
    session,csrf=store.create_session(analyst)
    _,token=store.create_token("synthetic_mcp","mcp:read",7,analyst)
    store.bind_oauth_identity("https://identity.example.test","subject-synthetic-1",analyst)
    store.record_activity(user_id=analyst,surface="mcp",action="MCP synthetic",
                          http_status=200,duration_ms=2)
    store.record_login_failure("synthetic_analyst")
    store.set_operator_assignment("Synthetic operator","Synthetic destination","Synthetic team")
    out=tmp_path/"auth-backup.sqlite"
    with store.db() as source, sqlite3.connect(out) as destination:
        source.backup(destination)
    yield out,store,admin,analyst,session,csrf,token


def test_offline_snapshot_preflight_and_no_token_output(snapshot,capsys):
    path,_,_,_,_,_,token=snapshot
    connection,counts=inspect_snapshot(path)
    try:
        assert counts["users"]==2
        assert counts["access_tokens"]==1
        assert counts["oauth_identities"]==1
        assert counts["sessions"]==1
        assert counts["activity_events"]==1
    finally:
        connection.close()
    assert token not in capsys.readouterr().out


def test_refuses_missing_source_or_non_snapshot_wal(tmp_path,snapshot):
    with pytest.raises(ValueError):
        inspect_snapshot(tmp_path/"missing.sqlite")
    path,*_=snapshot
    (tmp_path/"auth-backup.sqlite-wal").write_bytes(b"untrusted")
    with pytest.raises(ValueError,match="WAL-associated"):
        inspect_snapshot(path)


def test_refuses_non_disposable_targets(monkeypatch):
    monkeypatch.setenv("PANADAN_AUTH_MIGRATION_TEST_ALLOW_APPLY","YES")
    for dsn in (
        "postgresql://a@127.0.0.1/panadan",
        "postgresql://a@192.168.3.9/panadan_ci",
        "postgresql://a@host.example/panadan_ci",
    ):
        with pytest.raises(ValueError,match="disposable"):
            validate_disposable_target(dsn)
    monkeypatch.delenv("PANADAN_AUTH_MIGRATION_TEST_ALLOW_APPLY")
    with pytest.raises(ValueError):
        validate_disposable_target("postgresql://a@127.0.0.1/panadan_ci")


@pytest.fixture
def disposable_db():
    dsn=os.environ.get("PANADAN_PLATFORM_TEST_DSN")
    if not dsn:
        pytest.skip("No disposable panadan_ci PostgreSQL instance")
    cfg=conninfo_to_dict(dsn)
    if cfg.get("dbname")!="panadan_ci" or cfg.get("host") not in ("127.0.0.1","localhost") or os.environ.get("PANADAN_PLATFORM_TEST_ALLOW_RESET")!="YES":
        pytest.fail("Refusing any non-disposable PostgreSQL")
    with psycopg.connect(dsn,autocommit=True) as owner:
        # The schema is additive and must remain idempotent.
        sql=Path("database/migrations/003_auth_foundation.sql").read_text()
        owner.execute(sql)
        owner.execute(sql)
        for table in (
            "activity_events","transcript_access_audit","oauth_identities","access_tokens",
            "sessions","login_throttle","operator_directory","users",
        ):
            # Disposable CI database only. Never on real Panadan.
            owner.execute(f"TRUNCATE panadan_auth.{table} RESTART IDENTITY CASCADE")
    return dsn


def test_transactional_pg_import_preserves_accounts_tokens_bindings(snapshot,disposable_db,monkeypatch):
    monkeypatch.setenv("PANADAN_AUTH_MIGRATION_TEST_ALLOW_APPLY","YES")
    path,store,_,analyst,_,csrf,token=snapshot
    source,counts=inspect_snapshot(path)
    try:
        assert import_into_disposable(source,disposable_db,counts)==counts
    finally:
        source.close()
    with psycopg.connect(disposable_db) as pg:
        role,hash_password,profile=pg.execute(
            "SELECT role,password_hash,profile_id FROM panadan_auth.users WHERE id=%s",(analyst,)
        ).fetchone()
        assert role=="analyst"
        assert profile.startswith("prf_")
        assert ":" in hash_password
        assert pg.execute("SELECT COUNT(*) FROM panadan_auth.oauth_identities").fetchone()[0]==1
        assert pg.execute("SELECT csrf FROM panadan_auth.sessions WHERE user_id=%s",(analyst,)).fetchone()[0]==csrf
        assert pg.execute("SELECT count(*) FROM panadan_auth.access_tokens").fetchone()[0]==1
        # Explicitly verify the stored digest rather than copying raw bearer.
        from server.security import digest
        assert pg.execute("SELECT token_hash FROM panadan_auth.access_tokens").fetchone()[0]==digest(token)
        assert pg.execute("SELECT count(*) FROM panadan_auth.login_throttle").fetchone()[0]==1
        assert pg.execute("SELECT count(*) FROM panadan_auth.operator_directory").fetchone()[0]==1
    source,_=inspect_snapshot(path)
    try:
        with pytest.raises(ValueError,match="nonempty"):
            import_into_disposable(source,disposable_db,counts)
    finally:
        source.close()


def test_import_rollback_on_invalid_late_row(snapshot,disposable_db,monkeypatch):
    monkeypatch.setenv("PANADAN_AUTH_MIGRATION_TEST_ALLOW_APPLY","YES")
    path,*_=snapshot
    with sqlite3.connect(path) as s:
        # Test fixture is an offline disposable snapshot; make the deliberate
        # corruption in rollback-journal mode, without leaving WAL sidecars.
        s.execute("PRAGMA journal_mode=DELETE")
        s.execute("UPDATE activity_events SET duration_ms=999999 WHERE id=(SELECT MIN(id) FROM activity_events)")
    source,counts=inspect_snapshot(path)
    try:
        with pytest.raises(psycopg.errors.CheckViolation):
            import_into_disposable(source,disposable_db,counts)
    finally:
        source.close()
    with psycopg.connect(disposable_db) as pg:
        for table in ("users","sessions","activity_events","access_tokens"):
            assert pg.execute(f"SELECT COUNT(*) FROM panadan_auth.{table}").fetchone()[0]==0
