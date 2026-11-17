"""Test-only MCP discovery for a valid Stytch token without local data grants.

Do not copy this shim into production. It only permits standard, metadata-only
MCP protocol methods after the unmodified OAuthVerifier has verified signature,
issuer, audience, scope, TTL and signed client identity. All data-bearing tools
still go through the real production MCPBearerGate and field policy.
"""
from __future__ import annotations

import json
from collections import deque


_DISCOVERY_METHODS = frozenset({
    "initialize", "tools/list", "notifications/initialized", "ping",
})
_MAX_INSPECT_BYTES = 8192


class VerifiedDiscoveryGate:
    def __init__(self, gated_app, mcp_app, verify_details):
        self.gated_app = gated_app
        self.mcp_app = mcp_app
        self.verify_details = verify_details

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method", "").upper() != "POST":
            return await self.gated_app(scope, receive, send)

        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        auth = headers.get(b"authorization", b"").decode("latin1")
        if not auth.startswith("Bearer "):
            return await self.gated_app(scope, receive, send)

        # Use the exact same verifier as the data-bearing gate. Invalid or
        # wrong-audience tokens never reach even metadata-only discovery.
        details = self.verify_details(auth[7:])
        if not details or not details.get("client_id"):
            return await self.gated_app(scope, receive, send)

        cached = deque()
        payload = bytearray()
        complete = False
        while len(payload) <= _MAX_INSPECT_BYTES:
            item = await receive()
            cached.append(item)
            if item.get("type") != "http.request":
                break
            chunk = item.get("body", b"")
            if not isinstance(chunk, bytes) or len(payload) + len(chunk) > _MAX_INSPECT_BYTES:
                break
            payload.extend(chunk)
            if not item.get("more_body", False):
                complete = True
                break

        async def replay_receive():
            if cached:
                return cached.popleft()
            return await receive()

        if complete:
            try:
                request = json.loads(payload)
                if isinstance(request, dict) and request.get("jsonrpc") == "2.0" \
                        and request.get("method") in _DISCOVERY_METHODS:
                    # Never route tools/call or resources to the discovery app.
                    return await self.mcp_app(scope, replay_receive, send)
            except (ValueError, TypeError, UnicodeDecodeError):
                pass

        return await self.gated_app(scope, replay_receive, send)
