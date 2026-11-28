"""Synthetic tests for the explicitly installed SQLite identity foundation."""
import sqlite3
from contextlib import closing
from uuid import uuid4

import pytest

from server.security import Store
from server.knowledge_identity import SQLiteIdentityBridge, install_profile_identity


@pytest.fixture
def auth(tmp_path):
    store = Store(str(tmp_path / "auth.sqlite"))
    store.bootstrap("admin", "synthetic-password-only")
    uid = store.create_user("reader", "synthetic-password-only", "reader")
    token, _ = store.create_session(uid)
    return store, uid, token, uuid4()


def test_missing_installation_never_grants_and_legacy_login_works(auth):
    store, uid, token, ns = auth
    assert store.session(token)["user_id"] == uid
    assert SQLiteIdentityBridge(store, ns).resolve_session(token) is None
    with pytest.raises(ValueError):
        install_profile_identity(store, ns)
    assert SQLiteIdentityBridge(store, ns).resolve_session(token) is None


def test_profile_identity_stable_explicit_and_namespace_bound(auth):
    store, uid, token, ns = auth
    install_profile_identity(store, ns, confirmed=True)
    bridge = SQLiteIdentityBridge(store, ns)
    token, _ = store.create_session(uid)
    assert bridge.resolve_session(token) is None
    assert store.session(token) is None
    token, _ = store.create_session(uid)
    first = bridge.resolve_session(token)
    assert first is not None and first.subject.startswith("prf_")
    install_profile_identity(store, ns, confirmed=True)
    assert bridge.resolve_session(token) == first
    assert SQLiteIdentityBridge(store, uuid4()).resolve_session(token) is None
    with pytest.raises(ValueError):
        install_profile_identity(store, uuid4(), confirmed=True)
    with closing(store.db()) as db, db:
        db.execute("UPDATE users SET username='renamed' WHERE id=?", (uid,))
    assert bridge.resolve_session(token) == first
    other = store.create_user("other", "synthetic-password-only", "reader")
    second, _ = store.create_session(other)
    assert bridge.resolve_session(second).subject != first.subject
    # No changes to login or post-installation session semantics.
    assert store.verify_login("renamed", "synthetic-password-only") == uid


def test_deletion_replacement_and_profile_rewrite_blocked(auth):
    store, uid, token, ns = auth
    install_profile_identity(store, ns, confirmed=True)
    bridge = SQLiteIdentityBridge(store, ns)
    token, _ = store.create_session(uid)
    before = bridge.resolve_session(token)
    for query, params in [
        ("DELETE FROM users WHERE id=?", (uid,)),
        ("UPDATE users SET id=99 WHERE id=?", (uid,)),
        ("UPDATE users SET rowid=99 WHERE id=?", (uid,)),
        ("INSERT OR REPLACE INTO knowledge_identity_installation VALUES(1,'different')", ()),
        ("UPDATE users SET profile_id=NULL WHERE id=?", (uid,)),
        ("INSERT OR REPLACE INTO users(id,username,password_hash,role) VALUES (?,?,?,'reader')",
         (uid, "replacement", "not-a-password-hash")),
        ("UPDATE OR REPLACE users SET username='reader' WHERE username='admin'", ()),
    ]:
        with closing(store.db()) as db, pytest.raises(sqlite3.IntegrityError), db:
            db.execute(query, params)
    assert bridge.resolve_session(token) == before


def test_logout_disable_and_expiry_rechecked(auth):
    store, uid, token, ns = auth
    install_profile_identity(store, ns, confirmed=True)
    bridge = SQLiteIdentityBridge(store, ns)
    assert bridge.resolve_session(token)
    store.logout(token)
    assert bridge.resolve_session(token) is None
    token, _ = store.create_session(uid)
    with closing(store.db()) as db, db:
        db.execute("UPDATE sessions SET expires_at=0 WHERE user_id=?", (uid,))
    assert bridge.resolve_session(token) is None
    token, _ = store.create_session(uid)
    admin = next(u["id"] for u in store.list_users() if u["role"] == "admin")
    store.update_user(uid, "reader", None, False, admin)
    assert bridge.resolve_session(token) is None


def test_separate_installations_do_not_share_identity(auth, tmp_path):
    store, uid, token, ns = auth
    install_profile_identity(store, ns, confirmed=True)
    other = Store(str(tmp_path / "other.sqlite"))
    other.bootstrap("admin", "synthetic-password-only")
    uid2 = other.create_user("reader", "synthetic-password-only", "reader")
    token2, _ = other.create_session(uid2)
    ns2 = uuid4()
    install_profile_identity(other, ns2, confirmed=True)
    token, _ = store.create_session(uid)
    token2, _ = other.create_session(uid2)
    assert uid == uid2
    assert SQLiteIdentityBridge(other, ns2).resolve_session(token2) != SQLiteIdentityBridge(store, ns).resolve_session(token)
    assert SQLiteIdentityBridge(other, ns).resolve_session(token2) is None
