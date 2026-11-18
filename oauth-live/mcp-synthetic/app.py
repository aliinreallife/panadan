"""Synthetic-only Stytch *Live* MCP resource; no customer database or VPS access.

Unlike the separate Stytch Test environment, this app verifies only Live
RS256 access JWTs. Its distinct audience prevents resource-server confusion.
All MCP requests require an explicitly approved signed client and subject.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from mcp.server.mcpserver import MCPServer, Context
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from oauth_mcp import OAuthConfig, OAuthVerifier
from policy import (
    LIVE_ISSUER, LIVE_JWKS, SYNTHETIC_RESOURCE, REQUIRED_SCOPE, approved_live_pilot,
)

config = OAuthConfig.from_env()
if (
    config.mode != "oauth"
    or config.issuer != LIVE_ISSUER
    or config.jwks_url != LIVE_JWKS
    or config.resource != SYNTHETIC_RESOURCE
    or config.scope != REQUIRED_SCOPE
):
    raise RuntimeError("Live synthetic OAuth configuration must exactly match pinned policy")
verifier = OAuthVerifier(config)

# No fallback to a member email, Live session cookie, metadata URL, or client name.
pilot_client = os.getenv("PANADAN_LIVE_PILOT_CLIENT_ID", "")
pilot_subject_sha256 = os.getenv("PANADAN_LIVE_PILOT_SUBJECT_SHA256", "")
if len(pilot_client) > 160 or len(pilot_subject_sha256) > 64:
    raise RuntimeError("Pilot binding configuration is invalid")

mcp = MCPServer(
    "Panadan Live Synthetic MCP",
    version="0.1.0",
    instructions="Isolated Stytch Live OAuth verification. Synthetic data only; no reports.",
)
READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)


def is_approved(headers: dict[str, str]) -> bool:
    auth = headers.get("authorization", "")
    raw = auth[7:] if auth.startswith("Bearer ") else ""
    return approved_live_pilot(
        verifier.verify_details(raw), pilot_client, pilot_subject_sha256
    ) if raw else False


@mcp.tool(title="Check synthetic Live access", annotations=READ_ONLY)
def get_live_synthetic_access(ctx: Context) -> dict:
    """Return synthetic test flags after validated Live bearer authentication."""
    if not is_approved(ctx.headers or {}):
        return {"error": "permission_denied"}
    return {
        "environment": "stytch-live",
        "data": "synthetic-only",
        "actor": "authorized-live-pilot",
        "capabilities": ["mcp:synthetic:read"],
    }


class RequireLiveOAuth:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.inner(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        headers = {
            name.decode("latin1").lower(): value.decode("latin1")
            for name, value in scope.get("headers", [])
        }
        if not is_approved(headers):
            # OAuth discovery is deliberately public, but all tool discovery
            # and execution is denied before exact verified member+client binding.
            challenge = (
                'Bearer realm="panadan-live-synthetic", '
                f'resource_metadata="{config.metadata_url}", '
                f'scope="{config.scope}"'
            )
            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"cache-control", b"no-store"),
                    (b"www-authenticate", challenge.encode("ascii")),
                ],
            })
            await send({
                "type": "http.response.body",
                "body": b'{"error":"unauthorized"}',
            })
            return
        await self.inner(scope, receive, send)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    async with mcp.session_manager.run():
        yield


app = FastAPI(
    title="Panadan Live Synthetic OAuth MCP",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


@app.get("/healthz")
def healthz():
    return JSONResponse({
        "status": "ok",
        "environment": "stytch-live",
        "data": "synthetic-only",
        "pilot_authorization": (
            "configured" if pilot_client and pilot_subject_sha256 else "not-configured"
        ),
    }, headers={"Cache-Control": "no-store"})


@app.get("/.well-known/oauth-protected-resource", include_in_schema=False)
@app.get("/.well-known/oauth-protected-resource/mcp", include_in_schema=False)
def oauth_metadata():
    return JSONResponse(config.metadata(), headers={"Cache-Control": "no-store"})


app.mount(
    "/mcp",
    RequireLiveOAuth(
        mcp.streamable_http_app(
            streamable_http_path="/",
            stateless_http=True,
            json_response=True,
            host="0.0.0.0",
            transport_security=TransportSecuritySettings(
                enable_dns_rebinding_protection=True,
                allowed_hosts=[
                    "panadan-mcp-live-synthetic.vercel.app", "localhost:*", "127.0.0.1:*"
                ],
                allowed_origins=[
                    "https://panadan-stytch-oauth-live.vercel.app",
                    "https://panadan-mcp-live-synthetic.vercel.app",
                    "http://localhost:*", "http://127.0.0.1:*",
                ],
            ),
        )
    ),
)
