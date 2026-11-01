"""Persistent account login throttling tests (synthetic usernames, no Odoo)."""
from server.security import Store, LOGIN_THROTTLE_WINDOW, LOGIN_THROTTLE_THRESHOLD


def test_per_account_throttle_is_persistent_and_independent(tmp_path):
    path = str(tmp_path / "login-throttle.sqlite")
    store = Store(path)
    alice = "alice"
    bob = "bob"
    for _ in range(LOGIN_THROTTLE_THRESHOLD):
        store.record_login_failure(alice, now=1000)
    assert store.login_is_throttled(alice, now=1000)
    assert not store.login_is_throttled(bob, now=1000)
    assert Store(path).login_is_throttled(alice, now=1000)
    assert not store.login_is_throttled(alice, now=1001)  # first cooldown is short
    for i in range(1, 8):
        store.record_login_failure(alice, now=1001+i)
    assert store.login_is_throttled(alice, now=1008)
    assert not store.login_is_throttled(alice, now=1068)  # capped 60 seconds


def test_throttle_expiration_cleanup_and_success_reset(tmp_path):
    store = Store(str(tmp_path / "login-throttle.sqlite"))
    for _ in range(LOGIN_THROTTLE_THRESHOLD):
        store.record_login_failure("alice", now=1000)
    assert store.login_is_throttled("alice", now=1000)
    store.clear_login_failures("alice")
    assert not store.login_is_throttled("alice", now=1000)
    for _ in range(LOGIN_THROTTLE_THRESHOLD):
        store.record_login_failure("alice", now=1000)
    assert not store.login_is_throttled("alice", now=1000+LOGIN_THROTTLE_WINDOW)
    store.record_login_failure("alice", now=1000+LOGIN_THROTTLE_WINDOW)
    with store.db() as db:
        assert db.execute("SELECT failure_count FROM login_throttle").fetchone()[0] == 1
        values = [r[0] for r in db.execute("SELECT username_hash FROM login_throttle")]
    assert "alice" not in values


def test_invalid_username_length_uses_bounded_key(tmp_path):
    store = Store(str(tmp_path / "login-throttle.sqlite"))
    store.record_login_failure("x" * 10000, now=1000)
    store.record_login_failure("y" * 10000, now=1000)
    with store.db() as db:
        assert db.execute("SELECT COUNT(*) FROM login_throttle").fetchone()[0] == 1


def test_http_login_throttle_scoped_per_account(tmp_path, monkeypatch):
    from contextlib import asynccontextmanager
    import importlib
    import re
    from fastapi.testclient import TestClient
    monkeypatch.setenv("PANADAN_AUTH_DB", str(tmp_path / "auth.sqlite"))
    monkeypatch.setenv("PANADAN_ADMIN_USER", "admin")
    monkeypatch.setenv("PANADAN_ADMIN_PASSWORD", "synthetic-safe-admin-password")
    monkeypatch.setenv("PANADAN_COOKIE_SECURE", "true")
    monkeypatch.setenv("PANADAN_PUBLIC_ORIGIN", "https://dan.panafor.com")
    import server.main as main
    main = importlib.reload(main)

    @asynccontextmanager
    async def isolated(_app):
        main.store.bootstrap("admin", "synthetic-safe-admin-password")
        yield
    main.app.router.lifespan_context = isolated
    # All clients share one apparent proxy IP. Account throttling must not
    # block a separate legitimate user on that IP.
    with TestClient(main.app, base_url="https://dan.panafor.com") as client:
        for i in range(LOGIN_THROTTLE_THRESHOLD):
            page = client.get("/login")
            nonce = re.search(r'name="nonce" value="([^"]+)"', page.text).group(1)
            bad = client.post("/login", data={
                "username": "unknown-user", "password": "wrong-password",
                "nonce": nonce,
            }, headers={"Origin": "https://dan.panafor.com"}, follow_redirects=False)
            assert bad.status_code == 303, i
        page = client.get("/login")
        nonce = re.search(r'name="nonce" value="([^"]+)"', page.text).group(1)
        blocked = client.post("/login", data={
            "username": "unknown-user", "password": "wrong-password",
            "nonce": nonce,
        }, headers={"Origin": "https://dan.panafor.com", "X-Forwarded-For": "1.2.3.4"},
           follow_redirects=False)
        assert blocked.status_code == 429
        page = client.get("/login")
        nonce = re.search(r'name="nonce" value="([^"]+)"', page.text).group(1)
        good = client.post("/login", data={
            "username": "admin", "password": "synthetic-safe-admin-password",
            "nonce": nonce,
        }, headers={"Origin": "https://dan.panafor.com"}, follow_redirects=False)
        assert good.status_code == 303
        assert client.get("/dashboard").status_code == 200
