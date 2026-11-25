"""Route-level proof that WorkOS Standalone uses Panadan login and fails closed.

No WorkOS API, reporting DB, source Odoo, or real user is contacted.
"""
from contextlib import asynccontextmanager
from fastapi.testclient import TestClient
import pytest

from server.security import Store
from server.workos_standalone import WorkOSBridgeConfig


ISSUER = "https://workos-staging.example.com"
ORIGIN = "https://panadan.example.com"
USER_PASSWORD = "long-test-password-and-nothing-real"


def bridge():
    return WorkOSBridgeConfig.from_env({
        "PANADAN_WORKOS_STANDALONE_ENABLED": "true",
        "WORKOS_API_KEY": "sk_test_" + "t" * 40,
        "PANADAN_WORKOS_PENDING_SECRET": "not-real-signing-key-" * 4,
    }, oauth_mode="oauth", oauth_issuer=ISSUER, public_origin=ORIGIN)


@pytest.fixture
def offline_main(monkeypatch, tmp_path):
    from server import main
    db = Store(str(tmp_path / "route-only.sqlite"))
    db.bootstrap("admin", USER_PASSWORD)
    monkeypatch.setattr(main, "store", db)
    # SDK MCP session lifecycle is one-shot; this tests only FastAPI routes.
    @asynccontextmanager
    async def isolated(_app):
        yield
    monkeypatch.setattr(main.app.router, "lifespan_context", isolated)
    return main, db


def test_workos_endpoints_hidden_without_optin(offline_main, monkeypatch):
    main, _ = offline_main
    monkeypatch.setattr(main, "workos_bridge", WorkOSBridgeConfig())
    with TestClient(main.app, base_url="https://localhost:8508") as client:
        assert client.get("/oauth/workos/login?external_auth_id=ext_auth_01JX739KQ289Y3GRQP5CHTD5XB").status_code == 404
        assert client.get("/oauth/workos/continue").status_code == 404


def test_workos_redirects_to_existing_login_with_signed_cookie(offline_main, monkeypatch):
    main, _ = offline_main
    monkeypatch.setattr(main, "workos_bridge", bridge())
    with TestClient(main.app, base_url="https://localhost:8508") as client:
        bad = client.get("/oauth/workos/login?external_auth_id=invalid", follow_redirects=False)
        assert bad.status_code == 400
        res = client.get("/oauth/workos/login?external_auth_id=ext_auth_01JX739KQ289Y3GRQP5CHTD5XB",
                         follow_redirects=False)
        assert res.status_code == 303
        assert res.headers["location"] == "/login"
        cookie = client.cookies.get("panadan_workos_external_auth")
        assert bridge().read_pending(cookie) == "ext_auth_01JX739KQ289Y3GRQP5CHTD5XB"
        # We never set a new Panadan user session from the external request.
        assert client.cookies.get("panadan_session") is None


def test_workos_completion_requires_panadan_session_and_verified_email(offline_main, monkeypatch):
    main, db = offline_main
    cfg = bridge()
    monkeypatch.setattr(main, "workos_bridge", cfg)
    with TestClient(main.app, base_url="https://localhost:8508") as client:
        assert client.get("/oauth/workos/continue", follow_redirects=False).headers["location"] == "/login"
        uid = db.verify_login("admin", USER_PASSWORD)
        cookie, _ = db.create_session(uid)
        pending = cfg.issue_pending("ext_auth_01JX739KQ289Y3GRQP5CHTD5XB")
        headers = {"cookie": f"panadan_session={cookie}; panadan_workos_external_auth={pending}"}
        denied = client.get("/oauth/workos/continue", headers=headers, follow_redirects=False)
        assert denied.status_code == 403
        assert db.actor_for_oauth(ISSUER, cfg.external_subject(uid)) is None
        db.attest_workos_email(uid, "staging-owner@example.com", attested_by=uid,
                               evidence_ref="independent-check-123")
        called = []
        def fake_complete(auth_id, *, user_id, email):
            called.append((auth_id,user_id,email))
            return cfg.issuer + "/oauth/authorize/complete?state=ok"
        monkeypatch.setattr(cfg.__class__, "complete", lambda self, auth_id, *, user_id, email: fake_complete(auth_id,user_id=user_id,email=email))
        accepted = client.get("/oauth/workos/continue", headers=headers, follow_redirects=False)
        assert accepted.status_code == 303
        assert accepted.headers["location"] == cfg.issuer + "/oauth/authorize/complete?state=ok"
        assert called == [("ext_auth_01JX739KQ289Y3GRQP5CHTD5XB", uid,
                           "staging-owner@example.com")]
        assert db.actor_for_oauth(ISSUER,cfg.external_subject(uid)) == uid
