"""Offline OAuth discovery contract tests; no IdP, network, VPN or Odoo access."""
import pytest
from fastapi.testclient import TestClient

from server.oauth_mcp import OAuthConfig
from server.security import Store
from tools.check_mcp_oauth import (
    authorization_server_urls, protected_resource_url, require_https,
    validate_authorization_server, validate_resource, verify_challenge,
)

RESOURCE = "https://dan.panafor.com/mcp/"
ISSUER = "https://identity.example.test/realms/panadan"
METADATA = "https://dan.panafor.com/.well-known/oauth-protected-resource"
SCOPE = "panadan:mcp:read"


@pytest.fixture()
def config():
    return OAuthConfig(
        mode="oauth", issuer=ISSUER,
        jwks_url=ISSUER + "/protocol/openid-connect/certs",
        resource=RESOURCE, scope=SCOPE,
    )


def test_protected_resource_contract(config):
    issuer, scope = validate_resource(config.metadata(), RESOURCE)
    assert issuer == ISSUER
    assert scope == SCOPE
    assert protected_resource_url(RESOURCE) == METADATA
    assert authorization_server_urls(ISSUER) == (
        "https://identity.example.test/.well-known/oauth-authorization-server/realms/panadan",
        ISSUER + "/.well-known/openid-configuration",
    )


def test_hostile_metadata_rejected(config):
    data = config.metadata()
    for changed in (
        dict(data, resource="https://attacker.example/mcp/"),
        dict(data, authorization_servers=["http://insecure.example"]),
        dict(data, authorization_servers=[]),
        dict(data, scopes_supported=["other:scope"]),
    ):
        with pytest.raises(ValueError):
            validate_resource(changed, RESOURCE)
    with pytest.raises(ValueError):
        require_https("http://dan.panafor.com/mcp/")


def test_authorization_server_pkce_and_registration_requirements():
    original = {
        "issuer": ISSUER,
        "authorization_endpoint": ISSUER + "/authorize",
        "token_endpoint": ISSUER + "/token",
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "client_id_metadata_document_supported": True,
    }
    assert validate_authorization_server(original, ISSUER) == "CIMD"
    assert validate_authorization_server(
        {**original, "client_id_metadata_document_supported": False,
         "registration_endpoint": ISSUER + "/register"}, ISSUER,
    ) == "DCR"
    for changed in (
        dict(original, issuer="https://wrong.example.test"),
        dict(original, code_challenge_methods_supported=["plain"]),
        dict(original, token_endpoint="http://unsafe.example.test/token"),
        dict(original, token_endpoint_auth_methods_supported=[]),
    ):
        with pytest.raises(ValueError):
            validate_authorization_server(changed, ISSUER)


def test_auth_challenge_requires_exact_metadata_and_scope():
    verify_challenge(f'Bearer resource_metadata="{METADATA}", scope="{SCOPE}"',
                     METADATA, SCOPE)
    for invalid in (
        'Basic realm="panadan"',
        'Bearer realm="panadan"',
        'Bearer resource_metadata="https://evil.example/.well-known/oauth-protected-resource", scope="panadan:mcp:read"',
        f'Bearer resource_metadata="{METADATA}", scope="wrong:scope"',
    ):
        with pytest.raises(ValueError):
            verify_challenge(invalid, METADATA, SCOPE)


def test_actual_fastapi_metadata_and_401_route_contract(monkeypatch, tmp_path, config):
    from server import main
    monkeypatch.setenv("PANADAN_ADMIN_PASSWORD", "synthetic-unique-admin-password-123")
    monkeypatch.setattr(main, "store", Store(str(tmp_path / "auth.sqlite")))
    monkeypatch.setattr(main, "oauth_config", config)
    # This is an unauthenticated test. Never supply or mint tokens.
    monkeypatch.setattr(main, "oauth_verifier", None)
    with TestClient(main.app, base_url="http://localhost:8508") as client:
        for route in (
            "/.well-known/oauth-protected-resource",
            "/.well-known/oauth-protected-resource/mcp",
        ):
            response = client.get(route)
            assert response.status_code == 200
            assert response.json() == config.metadata()
            assert response.headers.get("cache-control") == "no-store"
        denied = client.get("/mcp/")
        assert denied.status_code == 401
        verify_challenge(denied.headers["www-authenticate"], METADATA, SCOPE)


def test_legacy_mode_disables_discovery_but_still_denies_tools(monkeypatch, tmp_path):
    from server import main
    monkeypatch.setenv("PANADAN_ADMIN_PASSWORD", "synthetic-unique-admin-password-123")
    monkeypatch.setattr(main, "store", Store(str(tmp_path / "auth.sqlite")))
    monkeypatch.setattr(main, "oauth_config", OAuthConfig())
    monkeypatch.setattr(main, "oauth_verifier", None)
    with TestClient(main.app, base_url="http://localhost:8508") as client:
        assert client.get("/.well-known/oauth-protected-resource").status_code == 404
        denied = client.get("/mcp/")
        assert denied.status_code == 401
        assert "resource_metadata=" not in denied.headers["www-authenticate"]
