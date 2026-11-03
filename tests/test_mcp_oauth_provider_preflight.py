"""Offline hosted-IdP OAuth preflight; synthetic public metadata, no connections."""
import copy

import pytest

from tools import check_mcp_oauth as check

ISSUER = "https://identity.example.test"
JWKS = ISSUER + "/keys"
DOC = {
    "issuer": ISSUER,
    "authorization_endpoint": ISSUER + "/authorize",
    "token_endpoint": ISSUER + "/token",
    "code_challenge_methods_supported": ["S256"],
    "token_endpoint_auth_methods_supported": ["none", "private_key_jwt"],
    "grant_types_supported": ["authorization_code", "refresh_token"],
    "response_types_supported": ["code"],
    "scopes_supported": ["openid", "panadan:mcp:read"],
    "client_id_metadata_document_supported": True,
    "authorization_response_iss_parameter_supported": True,
    "jwks_uri": JWKS,
}
KEYS = {"keys": [{"kty": "RSA", "kid": "rsa-key-1", "alg": "RS256", "use": "sig"}]}


def stub_fetch(monkeypatch, *, doc=None, keys=None):
    values = {
        check.authorization_server_urls(ISSUER)[0]: copy.deepcopy(DOC if doc is None else doc),
        JWKS: copy.deepcopy(KEYS if keys is None else keys),
    }
    calls = []
    def fetch(url):
        calls.append(url)
        assert url in values, f"unexpected network URL {url}"
        return values[url]
    monkeypatch.setattr(check, "fetch_json", fetch)
    return calls


def test_candidate_provider_can_be_preflighted_without_production(monkeypatch, capsys):
    calls = stub_fetch(monkeypatch)
    check.check_provider(ISSUER)
    output = capsys.readouterr().out
    assert "PASS: Public issuer metadata" in output
    assert "Client identification: CIMD" in output
    assert "UNVERIFIED:" in output
    assert "legacy bearer mode" in output
    assert calls == [check.authorization_server_urls(ISSUER)[0], JWKS]


@pytest.mark.parametrize("field, invalid", [
    ("issuer", "https://unexpected.example"),
    ("code_challenge_methods_supported", ["plain"]),
    ("token_endpoint_auth_methods_supported", ["client_secret_post"]),
    ("grant_types_supported", ["client_credentials"]),
    ("response_types_supported", ["token"]),
    ("scopes_supported", ["openid"]),
    ("jwks_uri", "http://identity.example.test/keys"),
])
def test_invalid_provider_metadata_is_rejected(monkeypatch, field, invalid):
    doc = {**DOC, field: invalid}
    stub_fetch(monkeypatch, doc=doc)
    with pytest.raises(ValueError):
        check.check_provider(ISSUER)


@pytest.mark.parametrize("keyset", [
    {"keys": []},
    {"keys": [{"kty": "EC", "kid": "key-1", "alg": "ES256"}]},
    {"keys": [{"kty": "RSA", "kid": "key-1", "alg": "HS256"}]},
    {"keys": [{"kty": "RSA", "alg": "RS256"}]},
    {"keys": [{"kty": "RSA", "kid": "key-1", "use": "enc"}]},
])
def test_non_rs256_signature_jwks_rejected(monkeypatch, keyset):
    stub_fetch(monkeypatch, keys=keyset)
    with pytest.raises(ValueError, match="RSA signature key"):
        check.check_provider(ISSUER)


def test_dcr_is_supported_when_cimd_is_disabled(monkeypatch, capsys):
    doc = {
        **DOC,
        "client_id_metadata_document_supported": False,
        "registration_endpoint": ISSUER + "/register",
        "token_endpoint_auth_methods_supported": ["client_secret_basic"],
    }
    stub_fetch(monkeypatch, doc=doc)
    check.check_provider(ISSUER)
    assert "Client identification: DCR" in capsys.readouterr().out


def test_manual_registration_is_reported_not_misrepresented(monkeypatch, capsys):
    doc = {**DOC, "client_id_metadata_document_supported": False}
    stub_fetch(monkeypatch, doc=doc)
    check.check_provider(ISSUER)
    output = capsys.readouterr().out
    assert "pre-registered OAuth client" in output
    assert "Provision compatible" in output


def test_unsafe_issuer_rejected_before_any_network(monkeypatch):
    monkeypatch.setattr(check, "fetch_json", lambda _: pytest.fail("must not fetch"))
    for issuer in ("http://identity.example.test", "https://user:key@identity.example.test"):
        with pytest.raises(ValueError):
            check.check_provider(issuer)


def test_issuer_cli_does_not_check_production_resource(monkeypatch, capsys):
    stub_fetch(monkeypatch)
    monkeypatch.setattr("sys.argv", ["check_mcp_oauth.py", "--issuer", ISSUER])
    assert check.main() == 0
    assert "PASS" in capsys.readouterr().out
