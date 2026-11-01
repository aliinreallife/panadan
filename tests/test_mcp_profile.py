"""Stable MCP profile IDs and credential-bound identity, using synthetic SQLite."""
import re
import sqlite3

from server.security import Store


def setup_reader(store: Store, username: str):
    user = store.create_user(
        username, "synthetic-very-long-password-for-tests", "analyst",
        ["calls:read", "metrics:read", "mcp:use"],
    )
    _, token=store.create_token(f"{username}-mcp", "mcp:read", 7, user)
    return user, token


def test_profiles_are_opaque_stable_distinct_and_revocable(tmp_path):
    path=tmp_path/"auth.sqlite"
    store=Store(str(path))
    a,token_a=setup_reader(store,"user_a")
    b,token_b=setup_reader(store,"user_b")
    pa=store.mcp_profile(legacy_token=token_a)
    pb=store.mcp_profile(legacy_token=token_b)
    assert pa["name"]=="user_a"
    assert pb["name"]=="user_b"
    assert re.fullmatch(r"prf_[A-Za-z0-9_-]{30,}", pa["id"])
    assert pa["id"] != pb["id"]
    assert str(a) not in pa["id"]
    assert store.mcp_profile(legacy_token=token_a)==pa
    assert Store(str(path)).mcp_profile(legacy_token=token_a)==pa
    assert store.mcp_profile(legacy_token="not_a_real_token") is None
    assert store.mcp_profile(legacy_token=token_a,oauth_subject="spoof") is None
    assert store.mcp_profile() is None
    # A different valid token owned by the same local account retains identity.
    _,another=store.create_token("alternate", "mcp:read", 7, a)
    assert store.mcp_profile(legacy_token=another)==pa
    admin=store.create_user("administrator","synthetic-super-long-admin-password","admin")
    store.update_user(b,"reader",["calls:read"],True,admin)
    assert store.mcp_profile(legacy_token=token_b) is None
    assert store.mcp_profile(legacy_token=token_a)==pa


def test_oauth_rebinding_keeps_stable_local_profile_id(tmp_path):
    store=Store(str(tmp_path/"auth.sqlite"))
    user,legacy=setup_reader(store,"oauth_person")
    original=store.mcp_profile(legacy_token=legacy)
    issuer="https://identity.example.test"
    subject="oidc-immutable-sub-987"
    store.bind_oauth_identity(issuer,subject,user)
    assert store.mcp_profile(oauth_issuer=issuer,oauth_subject=subject)==original
    assert store.mcp_profile(oauth_issuer="https://other.example",oauth_subject=subject) is None
    binding=store.list_oauth_identities(issuer)[0]
    store.revoke_oauth_identity(issuer,binding["id"])
    assert store.mcp_profile(oauth_issuer=issuer,oauth_subject=subject) is None
    store.bind_oauth_identity(issuer,subject,user)
    assert store.mcp_profile(oauth_issuer=issuer,oauth_subject=subject)==original


def test_migrating_legacy_users_assigns_profile_once(tmp_path):
    path=tmp_path/"legacy.sqlite"
    with sqlite3.connect(path) as c:
        c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL)")
        c.execute("INSERT INTO users (username,password_hash) VALUES('legacy','not-a-real-hash')")
    first=Store(str(path))
    with first.db() as c:
        a=c.execute("SELECT profile_id FROM users WHERE username='legacy'").fetchone()[0]
    assert a.startswith("prf_")
    second=Store(str(path))
    with second.db() as c:
        b=c.execute("SELECT profile_id FROM users WHERE username='legacy'").fetchone()[0]
    assert a==b
