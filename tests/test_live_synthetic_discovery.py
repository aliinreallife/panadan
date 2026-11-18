"""Metadata vs data gate for isolated Live synthetic MCP, no external traffic."""
from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
import sys

PATH = Path(__file__).resolve().parents[1] / "oauth-live/mcp-synthetic/oauth_discovery.py"
spec = importlib.util.spec_from_file_location("synthetic_live_oauth_discovery", PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


async def send_request(method="initialize", *, token="live-valid", rpc=None, http_method="POST"):
    called = []

    async def metadata(scope, receive, send):
        body = b""
        while True:
            message = await receive()
            body += message.get("body", b"")
            if not message.get("more_body"):
                break
        called.append(("metadata", body))
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"metadata-only"})

    async def gated(scope, receive, send):
        called.append(("gated", None))
        await send({"type": "http.response.start", "status": 401, "headers": []})
        await send({"type": "http.response.body", "body": b"denied"})

    def verify(jwt):
        if jwt == "live-valid":
            return {"subject": "verified-live-member", "client_id": "verified-live-client"}
        if jwt == "missing-signed-client":
            return {"subject": "verified-live-member", "client_id": None}
        return None

    payload = json.dumps(rpc if rpc is not None else
                         {"jsonrpc": "2.0", "method": method, "id": 1}).encode()
    messages = iter([{"type": "http.request", "body": payload, "more_body": False}])
    async def receive():
        return next(messages)
    output = []
    async def send(msg):
        output.append(msg)
    gate = mod.VerifiedOAuthDiscovery(gated, metadata, verify)
    headers = [(b"authorization", ("Bearer " + token).encode())] if token else []
    await gate(
        {"type": "http", "method": http_method, "headers": headers},
        receive, send,
    )
    return output[0]["status"], called, payload


def test_verified_live_jwt_may_discover_only_metadata():
    for method in ("initialize", "tools/list", "notifications/initialized", "ping"):
        status, calls, payload = asyncio.run(send_request(method))
        assert status == 200
        assert calls == [("metadata", payload)]


def test_no_data_bypass_even_with_verified_bearer():
    for method in ("tools/call", "resources/list", "resources/read",
                   "prompts/get", "unknown"):
        status, calls, _ = asyncio.run(send_request(method))
        assert status == 401
        assert calls == [("gated", None)]


def test_missing_invalid_or_clientless_bearer_denied():
    for token in ("", "expired", "wrong-issuer", "wrong-audience",
                  "missing-signed-client"):
        status, calls, _ = asyncio.run(send_request("tools/list", token=token))
        assert status == 401
        assert calls == [("gated", None)]


def test_wrong_transport_and_batch_do_not_bypass():
    for rpc in (
        [{"jsonrpc": "2.0", "method": "tools/list"}],
        {"jsonrpc": "1.0", "method": "tools/list"},
        {"jsonrpc": "2.0", "method": "tools/call"},
    ):
        status, calls, _ = asyncio.run(send_request(rpc=rpc))
        assert status == 401
        assert calls == [("gated", None)]
    status, calls, _ = asyncio.run(send_request(http_method="GET"))
    assert status == 401
    assert calls == [("gated", None)]


def test_large_metadata_request_is_gated():
    status, calls, _ = asyncio.run(send_request(
        rpc={"jsonrpc": "2.0", "method": "tools/list", "padding": "x" * 9000}
    ))
    assert status == 401
    assert calls == [("gated", None)]
