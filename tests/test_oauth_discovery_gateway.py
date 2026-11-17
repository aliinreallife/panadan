"""Offline verified OAuth discovery gate tests: no Stytch, VPN or Odoo.

The actual signature, audience and expiry rules are independently tested in
tests/test_oauth.py and tests/test_signed_oauth_client.py. Here, the verifier
is intentionally a stub so that only the metadata routing boundary is under
test, including body replay and wrong-method rejection.
"""
from __future__ import annotations

import asyncio
import json

from server.oauth_discovery import VerifiedOAuthDiscovery


async def _invoke(*, token="valid", method="tools/list", rpc=None,
                  chunks=None, http_method="POST"):
    records = []

    async def authenticated(scope, receive, send):
        records.append(("authenticated", await receive()))
        await send({"type": "http.response.start", "status": 401, "headers": []})
        await send({"type": "http.response.body", "body": b"denied"})

    async def metadata(scope, receive, send):
        data = []
        while True:
            item = await receive()
            data.append(item.get("body", b""))
            if not item.get("more_body"):
                break
        records.append(("metadata", b"".join(data)))
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    def verify(raw):
        return {"subject": "synthetic-user", "client_id": "verified-client"} if raw == "valid" else None

    request = rpc if rpc is not None else {
        "jsonrpc": "2.0", "id": 1, "method": method
    }
    payload = json.dumps(request).encode("utf8")
    parts = chunks if chunks is not None else [payload]
    messages = [
        {"type": "http.request", "body": part, "more_body": i + 1 < len(parts)}
        for i, part in enumerate(parts)
    ]
    iterator = iter(messages)
    async def receive():
        return next(iterator)
    response = []
    async def send(item):
        response.append(item)

    headers = [(b"authorization", ("Bearer " + token).encode("ascii"))] if token else []
    gate = VerifiedOAuthDiscovery(authenticated, metadata, verify)
    await gate({"type": "http", "method": http_method, "headers": headers}, receive, send)
    return response[0]["status"], records


def test_only_metadata_methods_route_around_local_consent():
    for method in ("initialize", "tools/list", "notifications/initialized", "ping"):
        status, entries = asyncio.run(_invoke(method=method))
        assert status == 200
        assert [entry[0] for entry in entries] == ["metadata"]


def test_all_data_calls_remain_behind_real_bearer_gate():
    for method in ("tools/call", "resources/list", "resources/read", "prompts/get",
                   "sampling/createMessage", "unknown"):
        status, entries = asyncio.run(_invoke(method=method))
        assert status == 401
        assert entries[0][0] == "authenticated"


def test_invalid_missing_or_mismatched_token_cannot_discover_tools():
    for token in ("", "expired", "wrong-audience", "unsigned"):
        status, entries = asyncio.run(_invoke(token=token))
        assert status == 401
        assert entries[0][0] == "authenticated"


def test_no_json_rpc_batch_or_wrong_protocol_or_get_bypass():
    for rpc in (
        [{"jsonrpc": "2.0", "method": "tools/list"}],
        {"jsonrpc": "1.0", "method": "tools/list"},
        {"method": "tools/list"},
        {"jsonrpc": "2.0", "method": "tools/call"},
    ):
        status, _ = asyncio.run(_invoke(rpc=rpc))
        assert status == 401
    status, _ = asyncio.run(_invoke(http_method="GET"))
    assert status == 401


def test_metadata_request_body_is_replayed_exactly_to_sdk():
    payload = json.dumps({"jsonrpc": "2.0", "id": 8, "method": "tools/list"}).encode()
    parts = [payload[:5], payload[5:19], payload[19:]]
    status, entries = asyncio.run(_invoke(chunks=parts))
    assert status == 200
    assert entries == [("metadata", payload)]


def test_oversized_request_fails_closed():
    payload = json.dumps({"jsonrpc": "2.0", "method": "tools/list",
                          "padding": "x" * 10000}).encode()
    status, entries = asyncio.run(_invoke(chunks=[payload]))
    assert status == 401
    assert entries[0][0] == "authenticated"
