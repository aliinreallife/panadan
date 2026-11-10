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

# Synthetic reporting values only; never connect to the production Odoo view.
secret = "SYNTHETIC-CUSTOMER-SECRET"
main.database.list_calls = lambda *a, **kw: [{
    "id": 73, "CALLDATE": "2026-11-09",
    "aicallinfostate": "Unchecked", "customername": secret,
}]
main.database.statuses = lambda: ["Unchecked"]
main.database.stats = lambda *a, **kw: {"total": 1, "sold_out": 0}
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
    try:
        store.create_token("forbidden reader MCP", "mcp:read", owner_id=restricted)
    except ValueError:
        pass
    else:
        raise AssertionError("reader unexpectedly permitted to create MCP bearer")

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
    # Seven current reporting/access tools plus the staging-only profile.
    # Discovery can advertise tools, but authorization occurs per call.
    expected_tools = {
        "get_profile", "get_my_access", "explain_access",
        "list_recent_calls", "get_call_summary", "get_call_metrics",
        "get_available_states", "get_redacted_call_transcript",
    }
    assert names == expected_tools
    assert len(tools) == len(names), "duplicate tool names"

    # Unified PostgreSQL auth must now enforce the SAME field-grant
    # intersections as SQLite on the real HTTP/MCP transport.
    def tool_call(token, name, arguments=None, request_id=20):
        return post(client, token, "tools/call", {
            "name": name, "arguments": arguments or {},
        }, request_id=request_id)

    mine = extract(tool_call(alice_token, "get_my_access", request_id=20))
    assert mine["actor"] == "self"
    assert "calls:read" in mine["capabilities"]
    assert "id" in {field["id"] for field in mine["columns"]}
    explanation = extract(tool_call(alice_token, "explain_access",
        {"field": "aicallinfostate"}, request_id=21))
    assert explanation["allowed"] is True
    recent = extract(tool_call(alice_token, "list_recent_calls",
        {"limit": 1}, request_id=22))
    assert recent["id"] == 73
    assert recent["CALLDATE"] == "2026-11-09"
    assert secret not in str(recent)
    assert secret not in tool_call(alice_token,"list_recent_calls",{"limit":1},
                                   request_id=23).text
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
    assert spoof.status_code in (200, 400, 422)
    if spoof.status_code == 200:
        answer = spoof.json()
        if "result" in answer and not answer["result"].get("isError"):
            # Some supported MCP SDK/Pydantic configurations ignore unknown
            # tool args. In either case identity MUST remain token-bound.
            details = answer["result"].get("structuredContent")
            if details is None:
                details = json.loads(answer["result"]["content"][0]["text"])
            assert details["id"] == a1["id"]

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
