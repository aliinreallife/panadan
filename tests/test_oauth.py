"""Offline OAuth resource-server security tests. No external IdP or customer DB."""
import asyncio
import json
import sqlite3
import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from server.oauth_mcp import OAuthConfig, OAuthVerifier
from server.security import Store


@pytest.fixture
def oauth_config():
    return OAuthConfig(
        mode="oauth", issuer="https://identity.example.test",
        jwks_url="https://identity.example.test/jwks",
        resource="https://reports.example.test/mcp/",
        scope="panadan:mcp:read",
    )


@pytest.fixture
def signer(oauth_config):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = OAuthVerifier(oauth_config)
    verifier.jwks = SimpleNamespace(
        get_signing_key_from_jwt=lambda _: SimpleNamespace(key=key.public_key())
    )

    def mint(**updates):
        now = int(time.time())
        claims = {
            "iss": oauth_config.issuer,
            "aud": oauth_config.resource,
            "iat": now,
            "nbf": now - 1,
            "exp": now + 240,
            "sub": "provider-user-123",
            "scope": oauth_config.scope,
        }
        claims.update(updates)
        return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "key-1"})

    return verifier, mint


def test_resource_metadata_is_explicit_and_not_based_on_request(oauth_config):
    assert oauth_config.metadata() == {
        "resource": "https://reports.example.test/mcp/",
        "authorization_servers": ["https://identity.example.test"],
        "scopes_supported": ["panadan:mcp:read"],
        "bearer_methods_supported": ["header"],
    }
    assert oauth_config.metadata_url == (
        "https://reports.example.test/.well-known/oauth-protected-resource"
    )


@pytest.mark.parametrize("field, value", [
    ("issuer", "http://not-secure.example"),
    ("issuer", "https://user:secret@identity.example.test"),
    ("jwks_url", "http://localhost:9000/jwks"),
    ("resource", "http://reports.example.test/mcp/"),
    ("resource", "https://reports.example.test/wrong"),
    ("scope", "two scopes"),
])
def test_invalid_oauth_setup_rejected(oauth_config, field, value):
    data = vars(oauth_config) | {field: value}
    with pytest.raises(ValueError):
        OAuthConfig(**data).validate()


def test_oauth_mode_off_by_default(monkeypatch):
    for name in (
        "PANADAN_MCP_AUTH_MODE", "PANADAN_OAUTH_ISSUER",
        "PANADAN_OAUTH_JWKS_URL", "PANADAN_OAUTH_RESOURCE",
    ):
        monkeypatch.delenv(name, raising=False)
    assert OAuthConfig.from_env().mode == "legacy"
    monkeypatch.setenv("PANADAN_MCP_AUTH_MODE", "oauth")
    with pytest.raises(ValueError):
        OAuthConfig.from_env()


def test_signed_access_token_validation(signer):
    verifier, mint = signer
    assert verifier.verify(mint()) == "provider-user-123"
    assert verifier.verify(mint(aud="https://other.example/mcp/")) is None
    assert verifier.verify(mint(iss="https://attacker.example")) is None
    assert verifier.verify(mint(scope="other:scope")) is None
    assert verifier.verify(mint(sub="")) is None
    assert verifier.verify(mint(token_use="id")) is None
    assert verifier.verify(mint(exp=int(time.time())-60)) is None
    assert verifier.verify(mint(exp=int(time.time())+7200)) is None
    assert verifier.verify(mint(iat=int(time.time())+100)) is None
    assert verifier.verify("not.a.jwt") is None
    assert verifier.verify("x" * 10000) is None
    # Use >=32 bytes for this intentionally invalid HS256 token, so the test
    # verifies RS256 algorithm rejection without a weak-key library warning.
    # This is synthetic test data, never an OAuth signing credential.
    test_hmac_key = "synthetic-hs256-rejection-fixture-key-2026"
    assert len(test_hmac_key.encode("utf-8")) >= 32
    assert verifier.verify(jwt.encode(
        {"sub": "provider-user-123"}, test_hmac_key,
        algorithm="HS256", headers={"kid": "key-1"}
    )) is None


def test_idp_binding_requires_admin_approved_identity_and_active_permissions(tmp_path, oauth_config):
    store = Store(str(tmp_path / "auth.sqlite"))
    store.bootstrap("admin", "a-long-admin-password-for-testing")
    admin = store.verify_login("admin", "a-long-admin-password-for-testing")
    analyst = store.create_user(
        "analyst", "another-very-long-password", "analyst",
        ["calls:read", "metrics:read", "mcp:use"],
    )
    metrics = store.create_user(
        "metrics", "another-very-long-password", "metrics", ["metrics:read"],
    )
    assert not store.oauth_identity_has_mcp_access(oauth_config.issuer, "provider-user-123")
    with pytest.raises(ValueError):
        store.bind_oauth_identity(oauth_config.issuer, "provider-user-123", metrics)
    link = store.bind_oauth_identity(oauth_config.issuer, "provider-user-123", analyst)
    assert store.oauth_identity_has_mcp_access(oauth_config.issuer, "provider-user-123")
    assert store.list_oauth_identities(oauth_config.issuer)[0]["id"] == link
    assert not store.oauth_identity_has_mcp_access("https://other-issuer.example", "provider-user-123")
    with pytest.raises(sqlite3.IntegrityError):
        store.bind_oauth_identity(oauth_config.issuer, "provider-user-123", analyst)
    store.update_user(analyst, "reader", ["calls:read"], True, admin)
    assert not store.oauth_identity_has_mcp_access(oauth_config.issuer, "provider-user-123")
    assert store.list_oauth_identities(oauth_config.issuer) == []
    store.update_user(analyst, "analyst", ["calls:read", "metrics:read", "mcp:use"], True, admin)
    store.bind_oauth_identity(oauth_config.issuer, "provider-user-123", analyst)
    store.revoke_oauth_identity(oauth_config.issuer, link + 1)
    assert not store.oauth_identity_has_mcp_access(oauth_config.issuer, "provider-user-123")


def test_oauth_gate_rejects_legacy_tokens_and_requires_bound_user(
    tmp_path, oauth_config, signer, monkeypatch
):
    from server import main
    verifier, mint = signer
    store = Store(str(tmp_path / "auth.sqlite"))
    store.bootstrap("admin", "a-long-admin-password-for-testing")
    admin = store.verify_login("admin", "a-long-admin-password-for-testing")
    _, legacy = store.create_token("manual", "mcp:read", 7, admin)
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "oauth_config", oauth_config)
    monkeypatch.setattr(main, "oauth_verifier", verifier)

    async def inner(scope, receive, send):
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    gate = main.MCPBearerGate(inner)

    def call(raw):
        result = []
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}
        async def send(message):
            result.append(message)
        asyncio.run(gate({
            "type": "http", "headers": [(b"authorization", ("Bearer " + raw).encode())]
        }, receive, send))
        return result

    denied = call(legacy)
    assert denied[0]["status"] == 401
    challenge = dict(denied[0]["headers"])[b"www-authenticate"].decode()
    assert oauth_config.metadata_url in challenge
    assert denied[0]["status"] == call(mint())[0]["status"] == 401
    store.bind_oauth_identity(oauth_config.issuer, "provider-user-123", admin)
    assert call(mint())[0]["status"] == 204
    assert call(mint(aud="https://other.example/mcp/"))[0]["status"] == 401
    identity = store.list_oauth_identities(oauth_config.issuer)[0]
    store.revoke_oauth_identity(oauth_config.issuer, identity["id"])
    assert call(mint())[0]["status"] == 401


def test_resource_metadata_disabled_without_oauth(monkeypatch):
    from server import main
    from fastapi import HTTPException
    monkeypatch.setattr(main, "oauth_config", OAuthConfig())
    with pytest.raises(HTTPException) as exc:
        main.oauth_protected_resource_metadata()
    assert exc.value.status_code == 404
