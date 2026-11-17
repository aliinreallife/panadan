"""Real Panadan MCP tool and permission code, synthetic input, offline RS256 tokens."""
from __future__ import annotations
import hashlib
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace

# Exact disposable Stytch Test issuer/resource; no bearer or personal data.
SUBJECT = "isolated-synthetic-member"
CLIENT_ID = "connected-app-test-11111111-2222-3333-4444-555555555555"
CHATGPT_CLIENT_ID = "connected-app-test-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
BASE = "https://panadan-authz-integration-staging.vercel.app"
os.environ.update({
    "PANADAN_INTEGRATION_STAGING_ENABLE": "YES",
    "PANADAN_MCP_AUTH_MODE": "oauth",
    "PANADAN_OAUTH_ISSUER": "https://viridian-faucet-2753.customers.stytch.dev",
    "PANADAN_OAUTH_JWKS_URL": "https://viridian-faucet-2753.customers.stytch.dev/.well-known/jwks.json",
    "PANADAN_OAUTH_RESOURCE": BASE + "/mcp/",
    "PANADAN_OAUTH_SCOPE": "panadan:mcp:read",
    "PANADAN_OAUTH_MAX_TOKEN_TTL": "3600",
    "PANADAN_INTEGRATION_APPROVED_CLIENT_ID": CLIENT_ID,
    "PANADAN_INTEGRATION_CHATGPT_STYTCH_CLIENT_ID": CHATGPT_CLIENT_ID,
    "PANADAN_INTEGRATION_TEST_SUBJECT_SHA256": hashlib.sha256(SUBJECT.encode()).hexdigest(),
})

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from server import main, database


def parse_result(resp):
    assert resp.status_code == 200, resp.text
    if "text/event-stream" in resp.headers.get("content-type", ""):
        events = [json.loads(line.removeprefix("data: ")) for line in resp.text.splitlines()
                  if line.startswith("data: ")]
        assert events
        parsed = events[-1]
    else:
        parsed = resp.json()
    assert "error" not in parsed, parsed
    result = parsed["result"]
    if "structuredContent" in result:
        return result["structuredContent"]
    blocks = result.get("content") or []
    assert blocks
    return json.loads(blocks[0]["text"])


def test_signed_stytch_test_subject_to_real_panadan_permission_lifecycle(monkeypatch):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(main.oauth_verifier, "jwks", SimpleNamespace(
        get_signing_key_from_jwt=lambda raw: SimpleNamespace(key=private.public_key())
    ))

    def token(**overrides):
        now = int(time.time())
        payload = {
            "iss": main.TEST_ISSUER, "aud": [main.TEST_RESOURCE, "synthetic-project"],
            "sub": SUBJECT, "client_id": CLIENT_ID,
            "scope": "openid panadan:mcp:read", "iat": now,
            "exp": now + 3600, "nbf": now - 1,
        }
        payload.update(overrides)
        return jwt.encode(payload, private, algorithm="RS256", headers={"kid": "synthetic-test-key"})

    def post(client, raw, name, args=None):
        return client.post("/mcp/", json={
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": name, "arguments": args or {}},
        }, headers={
            "authorization": "Bearer " + raw,
            "accept": "application/json, text/event-stream",
            "content-type": "application/json",
        })

    valid = token()
    unapproved = token(client_id="connected-app-test-55555555-6666-7777-8888-999999999999")
    with TestClient(main.app, base_url=BASE) as client:
        assert client.get("/healthz").json()["data"] == "synthetic-only"
        assert client.get("/.well-known/oauth-protected-resource").json()["resource"] == BASE + "/mcp/"
        assert client.post("/mcp/", json={}).status_code == 401
        assert post(client, "invalid-token", "get_my_access").status_code == 401
        assert post(client, token(aud="https://evil.test/mcp/"), "get_my_access").status_code == 401
        assert post(client, token(exp=int(time.time()) + 7200), "get_my_access").status_code == 401
        assert post(client, token(sub="unknown-member"), "get_my_access").status_code == 401
        assert post(client, unapproved, "get_my_access").status_code == 401

        # Safe metadata discovery for valid signed OAuth tokens is possible
        # without a Panadan client grant; data-bearing calls stay blocked.
        def tools_list(raw):
            return client.post("/mcp/", json={
                "jsonrpc": "2.0", "id": 4, "method": "tools/list",
            }, headers={
                "authorization": "Bearer " + raw,
                "accept": "application/json, text/event-stream",
                "content-type": "application/json",
            })
        assert tools_list(unapproved).status_code == 200
        assert "get_my_access" in tools_list(unapproved).text
        assert tools_list(token(aud="https://evil.test/mcp/")).status_code == 401

        # The approved, signed Test subject and exact signed client seed
        # ONLY this disposable Panadan account. The actual verifier,
        # Store and per-tool permission code are reused without edits.
        access = parse_result(post(client, valid, "get_my_access"))
        assert access["actor"] == "self"
        assert {field["id"] for field in access["columns"]} == {"id", "CALLDATE"}

        rows = post(client, valid, "list_recent_calls")
        assert rows.status_code == 200
        assert "73104" in rows.text
        assert "CALLDATE" in rows.text
        assert "SYNTHETIC_SECRET_MUST_NOT_LEAK" not in rows.text
        assert "customername" not in rows.text
        assert "aicallinfostate" not in rows.text
        assert parse_result(post(client, valid, "get_call_metrics"))["error"] == "permission_denied"

        # Real Panadan signed-subject gate admits this linked user, but
        # only the explicitly approved client has report-field consent.
        assert parse_result(post(client, unapproved, "get_my_access"))["columns"] == []
        assert parse_result(post(client, unapproved, "list_recent_calls"))["error"] == "permission_denied"

        # ChatGPT CIMD is represented by Stytch's *internal signed* client UUID,
        # not the public HTTPS CIMD metadata URL presented at authorization.
        chatgpt = token(client_id=CHATGPT_CLIENT_ID)
        chatgpt_access = parse_result(post(client, chatgpt, "get_my_access"))
        assert {f["id"] for f in chatgpt_access["columns"]} == {"id", "CALLDATE"}
        chatgpt_rows = post(client, chatgpt, "list_recent_calls")
        assert chatgpt_rows.status_code == 200
        assert "73104" in chatgpt_rows.text
        assert "SYNTHETIC_SECRET_MUST_NOT_LEAK" not in chatgpt_rows.text
        assert parse_result(post(client, chatgpt, "get_call_metrics"))["error"] == "permission_denied"

        # A lookalike CIMD URL, arbitrary HTTPS URL, and wrong Test member
        # must NOT be silently registered or granted synthetic fields.
        for forbidden in (
            "https://chatgpt.com/oauth/client.json.evil",
            "https://chatgpt.com/oauth/unknown/client.json",
            "https://other.example/oauth/client.json",
        ):
            raw = token(client_id=forbidden)
            assert parse_result(post(client, raw, "get_my_access"))["columns"] == []
            assert parse_result(post(client, raw, "list_recent_calls"))["error"] == "permission_denied"
        wrong_subject = token(client_id=CHATGPT_CLIENT_ID, sub="wrong-member")
        assert post(client, wrong_subject, "get_my_access").status_code == 401

        main.store.revoke_mcp_client(main.synthetic_user_id, CHATGPT_CLIENT_ID)
        assert parse_result(post(client, chatgpt, "list_recent_calls"))["error"] == "permission_denied"
        assert main.store.client_grants(main.synthetic_user_id, CHATGPT_CLIENT_ID) is None
        # Revoking ChatGPT's client does not revoke the Inspector grant.
        assert "73104" in post(client, valid, "list_recent_calls").text

        main.store.revoke_mcp_client(main.synthetic_user_id, CLIENT_ID)
        revoked = parse_result(post(client, valid, "list_recent_calls"))
        assert revoked["error"] == "permission_denied"
        # No re-provisioning when a local grant was revoked.
        assert main.store.client_grants(main.synthetic_user_id, CLIENT_ID) is None

        main.store.approve_mcp_client(main.synthetic_user_id, CLIENT_ID,
                                      ["mcp:use", "calls:read"], ["id"])
        after_narrow = post(client, valid, "list_recent_calls")
        assert after_narrow.status_code == 200
        assert "73104" in after_narrow.text
        assert "CALLDATE" not in after_narrow.text
        assert "SYNTHETIC_SECRET_MUST_NOT_LEAK" not in after_narrow.text

        record = main.store.list_oauth_identities(main.oauth_config.issuer)
        assert len(record) == 1
        main.store.revoke_oauth_identity(main.oauth_config.issuer, record[0]["id"])
        assert post(client, valid, "get_my_access").status_code == 401

        main.store.bind_oauth_identity(main.oauth_config.issuer, SUBJECT, main.synthetic_user_id)
        assert parse_result(post(client, valid, "get_my_access"))["columns"] == [{"id": "id", "label": "شناسه تماس"}]
        main.store.update_user(main.synthetic_user_id, "analyst",
                               ["calls:read", "mcp:use"], False, 0, fields=["id", "CALLDATE"])
        assert post(client, valid, "get_my_access").status_code == 401
        assert post(client, unapproved, "get_my_access").status_code == 401


def test_no_real_database_code_can_run():
    assert database.SYNTHETIC_ONLY is True
    assert not hasattr(database, "connect")
    import ast
    tree = ast.parse(Path(database.__file__).read_text())
    assert not any(
        isinstance(node, (ast.Import, ast.ImportFrom))
        and "psycopg" in ast.unparse(node)
        for node in ast.walk(tree)
    )
