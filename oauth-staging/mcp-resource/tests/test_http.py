"""Hermetic HTTP + signed JWT tests for the isolated synthetic MCP resource."""
import hashlib
import importlib
import json
import sys
import time
from types import SimpleNamespace

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

ISSUER = "https://viridian-faucet-2753.customers.stytch.dev"
RESOURCE = "https://panadan-mcp-oauth-staging.vercel.app/mcp/"
CLIENT = "connected-app-test-e2f5508f-e63e-4a7a-8fab-207276bda582"
SUB = "disposable-user-test-credential"


def setup_app(monkeypatch):
    vars = {
        "PANADAN_MCP_AUTH_MODE": "oauth",
        "PANADAN_OAUTH_ISSUER": ISSUER,
        "PANADAN_OAUTH_JWKS_URL": ISSUER + "/.well-known/jwks.json",
        "PANADAN_OAUTH_RESOURCE": RESOURCE,
        "PANADAN_OAUTH_SCOPE": "panadan:mcp:read",
        "PANADAN_STAGING_CLIENT_ID": CLIENT,
        "PANADAN_STAGING_SUBJECT_SHA256": hashlib.sha256(SUB.encode("utf8")).hexdigest(),
    }
    for name, value in vars.items():
        monkeypatch.setenv(name, value)
    sys.modules.pop("app", None)
    module = importlib.import_module("app")
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    module.verifier.jwks = SimpleNamespace(
        get_signing_key_from_jwt=lambda _: SimpleNamespace(key=private_key.public_key())
    )

    def token(**updates):
        now = int(time.time())
        claims = {
            "iss": ISSUER, "aud": RESOURCE, "iat": now,
            "exp": now + 300, "sub": SUB,
            "scope": "panadan:mcp:read", "client_id": CLIENT,
        }
        claims.update(updates)
        return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid":"synthetic-only"})

    return module.app, token


def test_discovery_challenge_and_synthetic_mcp_access(monkeypatch):
    app, token = setup_app(monkeypatch)
    with TestClient(app, base_url="https://panadan-mcp-oauth-staging.vercel.app") as client:
        assert client.get("/healthz").json()["data"] == "synthetic-only"
        for path in ("/.well-known/oauth-protected-resource",
                     "/.well-known/oauth-protected-resource/mcp"):
            r = client.get(path)
            assert r.status_code == 200
            assert r.json()["resource"] == RESOURCE
            assert r.json()["authorization_servers"] == [ISSUER]

        payload = {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name":"get_staging_access", "arguments":{}},
        }
        headers = {
            "content-type": "application/json",
            "accept": "application/json, text/event-stream",
        }
        unauth = client.post("/mcp/", json=payload, headers=headers)
        assert unauth.status_code == 401
        challenge = unauth.headers.get("www-authenticate", "")
        assert '/.well-known/oauth-protected-resource' in challenge
        assert 'scope="panadan:mcp:read"' in challenge
        for jwt_value in [
            "malformed",
            token(aud="https://some-other.example/mcp/"),
            token(iss="https://wrong.example"),
            token(scope="other:scope"),
            token(sub="unauthorized-other-member"),
            token(client_id="connected-app-test-11111111-2222-3333-4444-555555555555"),
            token(exp=int(time.time()) - 60),
        ]:
            denied = client.post("/mcp/", json=payload, headers=headers | {
                "authorization": "Bearer " + jwt_value,
            })
            assert denied.status_code == 401

        ok = client.post("/mcp/", json=payload, headers=headers | {
            "authorization": "Bearer " + token(),
        })
        assert ok.status_code == 200, ok.text
        assert "synthetic-only" in ok.text
        assert "customer" not in ok.text.lower()
