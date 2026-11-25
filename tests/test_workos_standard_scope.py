"""Standard WorkOS scopes do not bypass resource or local authorization."""
from types import SimpleNamespace
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from server.oauth_mcp import OAuthConfig, OAuthVerifier
from tools import check_mcp_oauth as check

ISSUER = "https://workos.example.test"
RESOURCE = "https://panadan.example.test/mcp/"
JWKS = ISSUER + "/oauth2/jwks"
CLIENT = "https://client.example.test/oauth-client-metadata.json"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def verifier(monkeypatch):
    config = OAuthConfig(mode="oauth", issuer=ISSUER, jwks_url=JWKS,
                         resource=RESOURCE, scope="openid")
    verifier = OAuthVerifier(config)
    monkeypatch.setattr(verifier.jwks, "get_signing_key_from_jwt",
                        lambda _: SimpleNamespace(key=KEY.public_key()))
    return verifier


def claims():
    now = int(time.time())
    return dict(iss=ISSUER, aud=RESOURCE, sub="panadan-user-1",
                client_id=CLIENT, sid="app_consent_example", jti="test-id",
                scope="openid profile email offline_access",
                iat=now, exp=now + 300)


def sign(payload):
    return jwt.encode(payload, KEY, algorithm="RS256", headers={"kid": "test"})


def test_standard_workos_access_token(verifier):
    assert verifier.verify_details(sign(claims())) == {
        "subject": "panadan-user-1", "client_id": CLIENT,
    }
    assert verifier.config.metadata()["scopes_supported"] == ["openid"]


@pytest.mark.parametrize("change", [
    {"iss": "https://different.example.test"},
    {"aud": CLIENT},
    {"aud": [RESOURCE, CLIENT]},
    {"aud": [RESOURCE]},
    {"scope": "profile email"},
    {"scope": ["openid"]},
    {"sub": "user_workos"},
    {"sub": "panadan-user-0"},
    {"sub": "panadan-user-1-other"},
    {"sub_profile": "ai_agent"},
    {"sid": ""},
    {"jti": ""},
    {"client_id": ""},
    {"client_id": 123},
    {"azp": "other-client"},
    {"token_use": "id"},
])
def test_standard_scope_rejects_invalid_access_tokens(verifier, change):
    assert verifier.verify_details(sign({**claims(), **change})) is None


@pytest.mark.parametrize("claim", ["sid", "jti", "client_id", "scope"])
def test_standard_scope_requires_signed_claims(verifier, claim):
    payload = claims()
    del payload[claim]
    assert verifier.verify_details(sign(payload)) is None


def test_provider_discovery_with_standard_scope():
    doc = dict(issuer=ISSUER, authorization_endpoint=ISSUER + "/authorize",
               token_endpoint=ISSUER + "/token",
               code_challenge_methods_supported=["S256"],
               token_endpoint_auth_methods_supported=["none"],
               grant_types_supported=["authorization_code", "refresh_token"],
               response_types_supported=["code"],
               scopes_supported=["openid", "profile", "email", "offline_access"],
               client_id_metadata_document_supported=True, jwks_uri=JWKS)
    assert check.validate_authorization_server(doc, ISSUER,
                                               required_scope="openid") == "CIMD"
    with pytest.raises(ValueError):
        check.validate_authorization_server(doc, ISSUER)
    for scopes in (None, ["profile"]):
        bad = {**doc, "scopes_supported": scopes}
        with pytest.raises(ValueError):
            check.validate_authorization_server(bad, ISSUER, required_scope="openid")


def test_resource_scope_is_explicit():
    metadata = OAuthConfig(mode="oauth", issuer=ISSUER, jwks_url=JWKS,
                           resource=RESOURCE, scope="openid").metadata()
    assert check.validate_resource(metadata, RESOURCE,
                                   required_scope="openid") == (ISSUER, "openid")
    with pytest.raises(ValueError):
        check.validate_resource(metadata, RESOURCE)
