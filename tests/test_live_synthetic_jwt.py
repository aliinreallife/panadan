"""Offline RS256 negative tests for *isolated* Live-synthetic audience.

Ephemeral RSA key is generated in-process; this does NOT mint real Stytch
tokens or communicate with Live IdP, customer reports, or the production VPS.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parents[1] / "oauth-live/mcp-synthetic"
name = "panadan_live_synthetic_oauth_verifier"
spec = importlib.util.spec_from_file_location(name, ROOT / "oauth_mcp.py")
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[name] = mod
spec.loader.exec_module(mod)

ISSUER = "https://flame-calf-4073.customers.stytch.com"
RESOURCE = "https://panadan-mcp-live-synthetic.vercel.app/mcp/"


def setup_verifier():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    config = mod.OAuthConfig(
        mode="oauth",
        issuer=ISSUER,
        jwks_url=ISSUER + "/.well-known/jwks.json",
        resource=RESOURCE,
        scope="panadan:mcp:read",
        max_ttl_seconds=3600,
    )
    verifier = object.__new__(mod.OAuthVerifier)
    verifier.config = config
    verifier.jwks = SimpleNamespace(
        get_signing_key_from_jwt=lambda _token: SimpleNamespace(key=key.public_key())
    )
    now = int(time.time())
    claims = {
        "iss": ISSUER, "aud": ["live-project-synthetic", RESOURCE],
        "sub": "member-live-synthetic-only", "iat": now - 10, "exp": now + 120,
        "scope": "openid panadan:mcp:read", "token_use": "access",
        "azp": "connected-app-live-synthetic-only",
        "client_id": "connected-app-live-synthetic-only",
    }
    def signed(override=None):
        return jwt.encode({**claims, **(override or {})}, key, algorithm="RS256",
                          headers={"kid": "ephemeral-test-key"})
    return verifier, signed, claims


def test_ephemeral_rs256_live_synthetic_claims_accepted_offline():
    verifier, signed, _ = setup_verifier()
    assert verifier.verify_details(signed()) == {
        "subject": "member-live-synthetic-only",
        "client_id": "connected-app-live-synthetic-only",
    }


def test_wrong_live_issuer_audience_and_scope_denied():
    verifier, signed, _ = setup_verifier()
    for override in (
        {"iss": "https://viridian-faucet-2753.customers.stytch.dev"},
        {"aud": "https://dan.panafor.com/mcp/"},
        {"aud": ["live-project-synthetic", RESOURCE, "https://dan.panafor.com/mcp/"]},
        {"scope": "openid"},
        {"token_use": "id"},
        {"client_id": "different-from-azp"},
        {"sub": ""},
        {"exp": int(time.time()) - 120},
        {"iat": int(time.time()) + 300},
        {"exp": int(time.time()) + 5000},
    ):
        assert verifier.verify_details(signed(override)) is None, override


def test_unsigned_and_wrong_signing_algorithm_denied():
    verifier, _, claims = setup_verifier()
    assert verifier.verify_details("not-a-jwt") is None
    hs_token = jwt.encode(claims, "ephemeral-hmac-secret", algorithm="HS256",
                          headers={"kid": "ephemeral-test-key"})
    assert verifier.verify_details(hs_token) is None
