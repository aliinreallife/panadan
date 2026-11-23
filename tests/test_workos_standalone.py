"""WorkOS existing-login bridge and signed-client consent gates: offline only."""
import json
import pytest

from server import workos_standalone as workos
from server.security import Store


ISSUER = "https://workos-staging.example.com"
ORIGIN = "https://panadan.example.com"


def config():
    return workos.WorkOSBridgeConfig.from_env({
        "PANADAN_WORKOS_STANDALONE_ENABLED": "true",
        "WORKOS_API_KEY": "sk_test_" + "a" * 40,
        "PANADAN_WORKOS_PENDING_SECRET": "test-signing-secret-do-not-use-in-prod-" * 3,
    }, oauth_mode="oauth", oauth_issuer=ISSUER, public_origin=ORIGIN)


def test_bridge_defaults_off_without_touching_production_login():
    assert not workos.WorkOSBridgeConfig.from_env(
        {}, oauth_mode="legacy", oauth_issuer="", public_origin="").enabled


@pytest.mark.parametrize("override", [
    {"PANADAN_WORKOS_STANDALONE_ENABLED": "garbage"},
    {"PANADAN_WORKOS_STANDALONE_ENABLED": "true"},
])
def test_incomplete_config_fails_closed(override):
    with pytest.raises(ValueError):
        workos.WorkOSBridgeConfig.from_env(
            override, oauth_mode="legacy", oauth_issuer=ISSUER, public_origin=ORIGIN)


def test_enabled_requires_oauth_mode_and_https_origin():
    env = {"PANADAN_WORKOS_STANDALONE_ENABLED": "true",
           "WORKOS_API_KEY": "sk_test_" + "a" * 40,
           "PANADAN_WORKOS_PENDING_SECRET": "z" * 40}
    for kwargs in (
        dict(oauth_mode="legacy", oauth_issuer=ISSUER, public_origin=ORIGIN),
        dict(oauth_mode="oauth", oauth_issuer=ISSUER, public_origin="http://panadan.example.com"),
        dict(oauth_mode="oauth", oauth_issuer="http://issuer.example.com", public_origin=ORIGIN),
    ):
        with pytest.raises(ValueError):
            workos.WorkOSBridgeConfig.from_env(env, **kwargs)


def test_signed_pending_cookie_expires_and_cannot_be_tampered():
    cfg = config()
    token = cfg.issue_pending("ext_auth_01JX739KQ289Y3GRQP5CHTD5XB", now=1000)
    assert cfg.read_pending(token, now=1001) == "ext_auth_01JX739KQ289Y3GRQP5CHTD5XB"
    assert cfg.read_pending(token, now=1601) is None
    assert cfg.read_pending(token, now=980) is None
    assert cfg.read_pending("not valid.token") is None
    assert cfg.read_pending(token + "changed", now=1010) is None
    tampered = token[:5] + ("A" if token[5] != "A" else "B") + token[6:]
    assert cfg.read_pending(tampered, now=1010) is None
    for invalid in ("", "/", "a" * 161, "a b", "a/b"):
        with pytest.raises(workos.WorkOSBridgeError):
            cfg.issue_pending(invalid)


@pytest.mark.parametrize("url", [
    "https://evil.example.com/oauth2/finish",
    "http://workos-staging.example.com/oauth2/finish",
    "https://workos-staging.example.com.evil.com/oauth2/finish",
    "https://user:pass@workos-staging.example.com/oauth2/finish",
    "https://workos-staging.example.com/evil/redirect",
    "https://workos-staging.example.com/oauth2/finish",
    "https://workos-staging.example.com/oauth/authorize/other",
    "https://workos-staging.example.com/oauth2/finish#fragment",
    "javascript:alert(1)",
])
def test_redirects_only_to_expected_workos_origin(url):
    with pytest.raises(workos.WorkOSBridgeError):
        config().validate_redirect(url)


def test_complete_uses_signed_in_user_id_and_attested_email_only(monkeypatch):
    cfg = config()
    called = {}

    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, n):
            assert n == 8193
            return json.dumps({
                "redirect_uri": ISSUER + "/oauth/authorize/complete?state=example"
            }).encode()

    def fake_urlopen(req, timeout):
        assert timeout == 8
        assert req.full_url == workos.WORKOS_COMPLETE_URL
        assert req.get_method() == "POST"
        assert req.get_header("Authorization") == "Bearer " + cfg.api_key
        called.update(json.loads(req.data))
        return Response()

    monkeypatch.setattr(workos, "urlopen", fake_urlopen)
    redirect = cfg.complete("ext_auth_01JX739KQ289Y3GRQP5CHTD5XB",
                            user_id=15, email="verified@example.com")
    assert redirect == ISSUER + "/oauth/authorize/complete?state=example"
    assert called == {
        "external_auth_id": "ext_auth_01JX739KQ289Y3GRQP5CHTD5XB",
        "user": {"id": "panadan-user-15", "email": "verified@example.com"},
    }


def test_complete_rejects_cross_origin_response(monkeypatch):
    class BadResponse:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, n):
            return b'{"redirect_uri":"https://evil.example.com/oauth2/finish"}'
    monkeypatch.setattr(workos, "urlopen", lambda request, timeout: BadResponse())
    with pytest.raises(workos.WorkOSBridgeError):
        config().complete("ext_auth_01JX739KQ289Y3GRQP5CHTD5XB",
                          user_id=12, email="verified@example.com")


def test_store_email_provisioning_only_after_admin_attestation(tmp_path):
    db = Store(str(tmp_path / "auth.sqlite"))
    db.bootstrap("admin", "a-test-admin-password-of-16chars")
    admin = db.verify_login("admin", "a-test-admin-password-of-16chars")
    user = db.create_user("alice", "a-test-password-longer-than-14", "analyst")
    assert db.workos_verified_email(user) is None
    with pytest.raises(ValueError):
        db.attest_workos_email(user, "alice@example.com",
                               attested_by=user, evidence_ref="ticket-123456")
    with pytest.raises(ValueError):
        db.attest_workos_email(user, "alice@example.com",
                               attested_by=admin, evidence_ref="x")
    db.attest_workos_email(user, "Alice+pilot@Example.com",
                           attested_by=admin, evidence_ref="verification-ticket-123")
    assert db.workos_verified_email(user) == "alice+pilot@example.com"
    assert len(db.list_workos_verified_emails()) == 1
    second = db.create_user("bob", "another-long-password-for-test", "analyst")
    with pytest.raises(Exception):
        db.attest_workos_email(second, "alice+pilot@example.com",
                               attested_by=admin, evidence_ref="verification-ticket-124")
    db.revoke_workos_email(user)
    assert db.workos_verified_email(user) is None


def test_signed_client_is_discovered_but_never_automatically_approved(tmp_path):
    db = Store(str(tmp_path / "auth.sqlite"))
    db.bootstrap("admin", "a-long-password-for-testing-only")
    user = db.create_user("alice", "another-long-password-for-test", "analyst")
    client = "https://chatgpt.com/.well-known/oauth-client"
    db.note_signed_mcp_client(user, client)
    pending = db.list_pending_mcp_clients(user)
    assert len(pending) == 1 and pending[0]["client_id"] == client
    assert db.client_grants(user, client) is None
    access = db.mcp_access(user, oauth_client=client)
    assert not access["capabilities"] and not access["fields"]
    assert not access["approved_capabilities"]
    db.note_signed_mcp_client(user, "")
    assert len(db.list_pending_mcp_clients(user)) == 1


def test_admin_role_change_invalidates_stale_email(tmp_path):
    db = Store(str(tmp_path / "auth.sqlite"))
    db.bootstrap("admin", "a-long-password-for-testing-only")
    admin = db.verify_login("admin", "a-long-password-for-testing-only")
    user = db.create_user("alice", "another-long-password-for-test", "analyst")
    db.attest_workos_email(user, "alice@example.com",
                           attested_by=admin, evidence_ref="verification-ticket-123")
    db.update_user(user, "analyst", None, True, admin)
    assert db.workos_verified_email(user) is None
