"""Allow safe MCP metadata discovery after full OAuth JWT verification.

An OAuth client may need tools/list before its Panadan user binding or
per-client consent is established. The ordinary MCPBearerGate deliberately
rejects unbound identities. This middleware allows ONLY MCP protocol metadata
methods for an already cryptographically verified OAuth access token.

Never use this middleware in legacy bearer-token mode. Never dispatch
tools/call, resources, prompts or other data-bearing methods through the
metadata-only path. Production data authorization stays in MCPBearerGate
and the individual MCP tools.
"""
from __future__ import annotations

import json
from collections import deque
from typing import Callable, Awaitable, Any

# These requests do not retrieve Panadan report rows or user grants.
_METADATA_METHODS = frozenset({
    "initialize", "tools/list", "notifications/initialized", "ping",
})
_MAX_JSON_RPC_BODY = 8192


class VerifiedOAuthDiscovery:
    """ASGI wrapper, enabled only when PANADAN_MCP_AUTH_MODE=oauth.

    verify_details MUST be the existing OAuthVerifier.verify_details method
    (signature, pinned issuer, exact aud/resource, expiry, RS256, scope and
    signed client ID). It is not a general-purpose token decoder.
    """

    def __init__(
        self,
        authenticated_app: Callable[..., Awaitable[Any]],
        metadata_app: Callable[..., Awaitable[Any]],
        verify_details: Callable[[str], dict | None],
    ):
        self.authenticated_app = authenticated_app
        self.metadata_app = metadata_app
        self.verify_details = verify_details

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method", "").upper() != "POST":
            return await self.authenticated_app(scope, receive, send)

        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        authorization = headers.get(b"authorization", b"").decode("latin1")
        if not authorization.startswith("Bearer "):
            return await self.authenticated_app(scope, receive, send)

        # Never trust an unverified subject or a client_id from the HTTP body.
        # Invalid, expired, wrong-resource or unsigned tokens take the normal
        # MCPBearerGate path and receive its standard OAuth 401 challenge.
        identity = self.verify_details(authorization[7:])
        if not identity or not identity.get("client_id"):
            return await self.authenticated_app(scope, receive, send)

        buffered = deque()
        payload = bytearray()
        complete = False
        while len(payload) <= _MAX_JSON_RPC_BODY:
            message = await receive()
            buffered.append(message)
            if message.get("type") != "http.request":
                break
            chunk = message.get("body", b"")
            if not isinstance(chunk, bytes) or len(payload) + len(chunk) > _MAX_JSON_RPC_BODY:
                break
            payload.extend(chunk)
            if not message.get("more_body", False):
                complete = True
                break

        async def replay_receive():
            if buffered:
                return buffered.popleft()
            return await receive()

        if complete:
            try:
                rpc = json.loads(payload)
                if (isinstance(rpc, dict) and rpc.get("jsonrpc") == "2.0"
                        and rpc.get("method") in _METADATA_METHODS):
                    return await self.metadata_app(scope, replay_receive, send)
            except (UnicodeDecodeError, ValueError, TypeError):
                pass

        return await self.authenticated_app(scope, replay_receive, send)
