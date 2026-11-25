"""Native WorkOS AuthKit checks; no live identity or source data."""
import base64
import hashlib
import json
import time
from urllib.parse import urlsplit, parse_qs
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from server.authkit_login import AuthKitConfig, AuthKitError
from server.oauth_mcp import OAuthConfig, OAuthVerifier
from server.security import Store

ISSUER = "https://synthetic.authkit.app"
RESOURCE = "https://panadan.invalid/mcp/"
SUBJECT = "user_synthetic123"
EMAIL = "admin@example.invalid"


def config(**overrides):
    env = {
        "PANADAN_WEB_AUTH_MODE": "authkit",
        "WORKOS_CLIENT_ID": "client_synthetic123",
        "WORKOS_API_KEY": "sk_test_synthetic_not_real",
        "PANADAN_AUTHKIT_ADMIN_EMAIL": EMAIL,
        "PANADAN_AUTHKIT_ADMIN_SUBJECT": SUBJECT,
        "PANADAN_AUTHKIT_ADMIN_UID": "1",
        **overrides,
    }
    return AuthKitConfig.from_env(
        env, origin="https://panadan.invalid", secure=True,
        oauth_mode="oauth", standalone=False,
    )


def test_state_pkce_and_callback_origin():
    c = config()
    url, cookie = c.begin()
    p = urlsplit(url)
    q = parse_qs(p.query)
    assert (p.scheme, p.netloc, p.path) == (
        "https", "api.workos.com", "/user_management/authorize")
    assert q["redirect_uri"] == [c.callback]
    assert q["provider"] == ["authkit"]
    verifier = c.verifier_for(cookie, q["state"][0])
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
    assert q["code_challenge"] == [challenge.decode().rstrip("=")]
    assert q["code_challenge_method"] == ["S256"]
    assert c.begin()[1] != cookie
    with pytest.raises(AuthKitError):
        c.verifier_for(cookie, "wrong")
    with pytest.raises(AuthKitError):
        c.verifier_for(None, q["state"][0])


@pytest.mark.parametrize("changes", [
    {"id": "user_other123"}, {"email": "other@example.invalid"},
    {"email_verified": False}, {"email_verified": "true"},
])
def test_only_pinned_verified_identity_can_sign_in(changes):
    c = config()
    user = {"id": SUBJECT, "email": EMAIL, "email_verified": True}
    c.verify_user(user)
    with pytest.raises(AuthKitError):
        c.verify_user({**user, **changes})


def test_invalid_native_mode_fails_closed():
    with pytest.raises(ValueError):
        config(PANADAN_AUTHKIT_ADMIN_SUBJECT="panadan-user-1")
    with pytest.raises(ValueError):
        config(WORKOS_API_KEY="")
    with pytest.raises(ValueError):
        config(PANADAN_AUTHKIT_ADMIN_UID="0")
    assert not config(PANADAN_WEB_AUTH_MODE="local").enabled


def test_exchange_checks_authenticated_user_and_never_exposes_tokens(monkeypatch):
    c = config()
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self, limit):
            return json.dumps({"user": {"id": SUBJECT, "email": EMAIL,
                "email_verified": True}, "access_token": "sensitive-token"}).encode()
    def open_request(req, timeout):
        assert req.full_url == "https://api.workos.com/user_management/authenticate"
        payload = json.loads(req.data)
        assert payload["grant_type"] == "authorization_code"
        assert payload["code_verifier"] == "synthetic-verifier"
        return Response()
    monkeypatch.setattr("server.authkit_login.build_opener",
                        lambda *args: SimpleNamespace(open=open_request))
    assert c.exchange("synthetic-code", "synthetic-verifier") is None


def test_additive_sessions_and_native_admin_migration(tmp_path):
    store = Store(str(tmp_path / "auth.sqlite"))
    store.bootstrap("admin", "synthetic-long-password")
    other = store.create_user("old_user", "synthetic-long-password", "reader")
    store.bind_oauth_identity(ISSUER, "panadan-user-1", 1)
    local, _ = store.create_session(1)
    other_session, _ = store.create_session(other)
    store.prepare_authkit_admin(1, ISSUER, SUBJECT)
    assert store.actor_for_oauth(ISSUER, SUBJECT) == 1
    assert store.actor_for_oauth(ISSUER, "panadan-user-1") is None
    assert store.user_access(other) is None
    assert store.session(other_session) is None
    assert store.session(local, auth_source="authkit") is None
    native, _ = store.create_session(1, auth_source="authkit")
    assert store.session(native) is None
    assert store.session(native, auth_source="authkit")["user_id"] == 1
    store.prepare_authkit_admin(1, ISSUER, SUBJECT)
    assert store.session(native, auth_source="authkit")
    store.logout(native)
    assert store.session(native, auth_source="authkit") is None
    assert len(store.list_users()) == 2


def test_mcp_native_subject_requires_valid_signature_audience_scope_and_client():
    cfg = OAuthConfig(mode="oauth", issuer=ISSUER, jwks_url=ISSUER + "/oauth2/jwks",
                      resource=RESOURCE, scope="openid", authkit_admin_subject=SUBJECT)
    verifier = OAuthVerifier(cfg)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier.jwks = SimpleNamespace(get_signing_key_from_jwt=lambda raw:
                                   SimpleNamespace(key=key.public_key()))
    now = int(time.time())
    base = {"iss": ISSUER, "aud": RESOURCE, "sub": SUBJECT, "iat": now,
            "exp": now + 300, "scope": "openid", "sid": "consent-id",
            "jti": "token-id", "client_id": "https://chatgpt.com/oauth/client.json"}
    def token(claims):
        return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test"})
    assert verifier.verify_details(token(base)) == {
        "subject": SUBJECT, "client_id": base["client_id"]}
    for changes in ({"sub": "user_other"}, {"sub": "panadan-user-1"},
                    {"aud": "https://other.invalid/mcp/"},
                    {"scope": "email"}, {"client_id": None}, {"sid": None}):
        assert verifier.verify_details(token({**base, **changes})) is None


def test_cookie_signature_and_server_side_expiry(monkeypatch):
    c = config()
    monkeypatch.setattr("server.authkit_login.time.time", lambda: 1000)
    url, cookie = c.begin()
    state = parse_qs(urlsplit(url).query)["state"][0]
    assert c.verifier_for(cookie, state)
    parts = cookie.split(".")
    parts[1] = ("a" if parts[1][0] != "a" else "b") + parts[1][1:]
    with pytest.raises(AuthKitError):
        c.verifier_for(".".join(parts), state)
    with pytest.raises(AuthKitError):
        config(WORKOS_API_KEY="sk_test_different_key").verifier_for(cookie, state)
    monkeypatch.setattr("server.authkit_login.time.time", lambda: 1601)
    with pytest.raises(AuthKitError):
        c.verifier_for(cookie, state)


def test_native_http_login_and_logout_without_real_provider(tmp_path, monkeypatch):
    import importlib
    from contextlib import asynccontextmanager
    from fastapi.testclient import TestClient
    import server.main as main

    with monkeypatch.context() as mp:
        settings = {
            "PANADAN_AUTH_DB": str(tmp_path / "native.sqlite"),
            "PANADAN_AUTH_BACKEND": "sqlite",
            "PANADAN_PUBLIC_ORIGIN": "https://panadan.invalid",
            "PANADAN_COOKIE_SECURE": "true",
            "PANADAN_MCP_AUTH_MODE": "oauth",
            "PANADAN_OAUTH_ISSUER": ISSUER,
            "PANADAN_OAUTH_JWKS_URL": ISSUER + "/oauth2/jwks",
            "PANADAN_OAUTH_RESOURCE": RESOURCE,
            "PANADAN_OAUTH_SCOPE": "openid",
            "PANADAN_WORKOS_STANDALONE_ENABLED": "false",
            "PANADAN_WEB_AUTH_MODE": "authkit",
            "WORKOS_CLIENT_ID": "client_synthetic123",
            "WORKOS_API_KEY": "sk_test_synthetic_not_real",
            "PANADAN_AUTHKIT_ADMIN_EMAIL": EMAIL,
            "PANADAN_AUTHKIT_ADMIN_SUBJECT": SUBJECT,
            "PANADAN_AUTHKIT_ADMIN_UID": "1",
        }
        for k, v in settings.items():
            mp.setenv(k, v)
        main = importlib.reload(main)
        main.store.bootstrap("admin", "synthetic-long-password")
        old, _ = main.store.create_session(1)
        main.store.prepare_authkit_admin(1, ISSUER, SUBJECT)
        exchanged = []

        def exchange(self, code, verifier):
            exchanged.append(code)
            if code != "valid-test-code":
                raise AuthKitError("Provider rejected")

        mp.setattr(AuthKitConfig, "exchange", exchange)

        @asynccontextmanager
        async def isolated(_app):
            yield

        main.app.router.lifespan_context = isolated
        with TestClient(main.app, base_url="https://panadan.invalid") as client:
            client.cookies.set("panadan_session", old)
            assert client.get("/dashboard/oauth").status_code == 401
            login = client.get("/login")
            assert login.status_code == 200
            assert "/auth/workos/start" in login.text
            assert 'name="password"' not in login.text
            assert client.post("/login", data={"username": "admin",
                "password": "synthetic-long-password", "nonce": "bad"}).status_code == 403
            assert client.get("/oauth/workos/login?external_auth_id=synthetic_test_123456789").status_code == 404

            def start():
                response = client.get("/auth/workos/start", follow_redirects=False)
                assert response.status_code == 303
                assert "secure" in response.headers["set-cookie"].lower()
                assert "httponly" in response.headers["set-cookie"].lower()
                return parse_qs(urlsplit(response.headers["location"]).query)["state"][0]

            state = start()
            failed = client.get("/auth/workos/callback", params={"code": "valid-test-code",
                               "state": "wrong"}, follow_redirects=False)
            assert failed.headers["location"] == "/login?error=1"
            assert not exchanged
            state = start()
            failed = client.get("/auth/workos/callback", params={"code": "denied",
                               "state": state}, follow_redirects=False)
            assert failed.headers["location"] == "/login?error=1"
            assert client.get("/dashboard/oauth").status_code == 401
            state = start()
            ok = client.get("/auth/workos/callback", params={"code": "valid-test-code",
                            "state": state}, follow_redirects=False)
            assert ok.headers["location"] == "/dashboard"
            raw = client.cookies.get(main.COOKIE_NAME)
            assert raw and main.store.session(raw) is None
            session = main.store.session(raw, auth_source="authkit")
            assert session["user_id"] == 1
            assert client.get("/dashboard/oauth").status_code == 200
            assert client.get("/api/v1/calls").status_code == 401
            assert client.get("/mcp/").status_code == 401
            assert client.post("/logout", data={"csrf": "bad"}).status_code == 403
            out = client.post("/logout", data={"csrf": session["csrf"]},
                              follow_redirects=False)
            assert out.status_code == 303
            assert main.store.session(raw, auth_source="authkit") is None
            assert client.get("/dashboard/oauth").status_code == 401
    importlib.reload(main)
