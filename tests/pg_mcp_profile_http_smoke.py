"""Real MCP Streamable HTTP profile smoke in a FRESH, disposable PG18 process.

Invoked only by tests/test_auth_pg_migration.py with its loopback panadan_ci
fixture. No real Odoo, Plane, VPN, production auth or customer records.
An isolated process is essential: MCP SDK session-manager lifespan is
one-shot and cannot be restarted by repeated pytest TestClient fixtures.
"""
from __future__ import annotations

import json
import os

from fastapi.testclient import TestClient

# Gate must run before importing server.main, which creates the MCP singleton.
from server.auth_store import validate_staging_dsn

dsn = os.environ.get("PANADAN_AUTH_STAGING_DSN", "")
assert os.environ.get("PANADAN_PLATFORM_TEST_ALLOW_RESET") == "YES"
assert os.environ.get("PANADAN_AUTH_BACKEND") == "postgres-staging"
assert os.environ.get("PANADAN_AUTH_STAGING_ENABLE") == "YES"
assert os.environ.get("PANADAN_AUTH_STAGING_ISOLATED") == "YES"
validate_staging_dsn(dsn)

from server import main  # noqa: E402

store = main.store
# The caller creates an empty, dedicated CI auth schema with a setup fixture.
# Refuse to touch nonempty accounts/tokens instead of modifying an existing
# database. This smoke inserts ONLY temporary synthetic accounts.
with store.db() as con:
    occupied = con.execute(
        """SELECT (SELECT count(*) FROM panadan_auth.users)
                  + (SELECT count(*) FROM panadan_auth.access_tokens)
                  + (SELECT count(*) FROM panadan_auth.sessions) AS n"""
    ).fetchone()["n"]
assert occupied == 0, "refusing nonempty disposable auth database"


def extract(response):
    assert response.status_code == 200, "MCP request did not succeed"
    if "text/event-stream" in response.headers.get("content-type", ""):
        pieces = [
            json.loads(line[6:])
            for line in response.text.splitlines() if line.startswith("data: ")
        ]
        assert pieces
        payload = pieces[-1]
    else:
        payload = response.json()
    assert "error" not in payload, "MCP protocol error"
    result = payload["result"]
    assert not result.get("isError"), "MCP tool execution error"
    if "structuredContent" in result:
        return result["structuredContent"]
    if "tools" in result:
        return result
    return json.loads(result["content"][0]["text"])


def post(client, token, method, params=None, request_id=1):
    return client.post(
        "/mcp/",
        headers={
            "accept": "application/json, text/event-stream",
            "content-type": "application/json",
            "authorization": "Bearer " + token,
        },
        json={
            "jsonrpc": "2.0", "id": request_id, "method": method,
            "params": params or {},
        },
    )


with TestClient(main.app, base_url="http://localhost:8508") as client:
    admin = store.verify_login("synthetic_admin", os.environ["PANADAN_ADMIN_PASSWORD"])
    assert admin is not None
    alice = store.create_user("synthetic_alice", "synthetic-only-alice-password", "analyst")
    bob = store.create_user("synthetic_bob", "synthetic-only-bob-password", "analyst")
    restricted = store.create_user("synthetic_reader", "synthetic-only-reader-password", "reader")
    _, alice_token = store.create_token("synthetic Alice MCP", "mcp:read", owner_id=alice)
    _, bob_token = store.create_token("synthetic Bob MCP", "mcp:read", owner_id=bob)
    _, api_token = store.create_token("synthetic Alice API", "api:read", owner_id=alice)

    # Authentication occurs BEFORE the tool SDK sees the request.
    assert client.post("/mcp/", json={}).status_code == 401
    assert post(client, "not-a-token", "tools/list").status_code == 401
    assert post(client, api_token, "tools/list").status_code == 401

    initialize = post(client, alice_token, "initialize", {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "Panadan synthetic CI smoke", "version": "1.0"},
    })
    assert initialize.status_code == 200
    tools = extract(post(client, alice_token, "tools/list", request_id=2))["tools"]
    names = {t["name"] for t in tools}
    assert len(names) == 6, "staging profile is additive to the original five tools"
    profile_tool = next(t for t in tools if t["name"] == "get_profile")
    assert profile_tool["_meta"]["openai/profile"] is True
    assert profile_tool["annotations"]["readOnlyHint"] is True
    assert "id" in profile_tool["outputSchema"]["required"]

    def profile(token, request_id):
        return extract(post(
            client, token, "tools/call",
            {"name": "get_profile", "arguments": {}},
            request_id=request_id,
        ))

    a1 = profile(alice_token, 3)
    a2 = profile(alice_token, 4)
    b1 = profile(bob_token, 5)
    assert a1["id"].startswith("prf_") and a1["id"] == a2["id"]
    assert a1["id"] != b1["id"]
    assert a1["name"] == "synthetic_alice"
    assert b1["name"] == "synthetic_bob"
    assert set(a1) == {"id", "name"}
    assert store.mcp_profile(legacy_token=alice_token)["id"] == a1["id"]

    # Client-supplied account IDs cannot switch identity: no tool args.
    spoof = post(client, alice_token, "tools/call", {
        "name": "get_profile", "arguments": {"account_id": b1["id"]},
    }, request_id=6)
    assert spoof.status_code == 200
    payload = spoof.json()["result"]
    assert payload["isError"] is True, "unexpected account selector accepted"

    # Scope change invalidates session/token records, without stale MCP
    # authorization or a phantom profile for the former account.
    store.update_user(alice, "reader", ["calls:read"], True, admin)
    assert post(client, alice_token, "tools/list", request_id=7).status_code == 401
    assert post(client, alice_token, "tools/call", {
        "name": "get_profile", "arguments": {},
    }, request_id=8).status_code == 401
    assert profile(bob_token, 9)["id"] == b1["id"]

    assert store.actor_for_token(alice_token, "mcp:read") is None
    assert not store.mcp_profile(legacy_token=alice_token)
    # Explicit revoke of Bob's token must immediately prevent profile lookup.
    bob_entry = next(
        t for t in store.list_tokens()
        if t["scope"] == "mcp:read" and t["owner"] == "synthetic_bob"
    )
    store.revoke(bob_entry["id"])
    assert post(client, bob_token, "tools/list", request_id=10).status_code == 401

print("PASS: isolated PostgreSQL MCP HTTP profile, identity separation and revocation")
