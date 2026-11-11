"""Isolated Stytch Test OAuth MCP resource.

This app has no production Panadan dependency, customer data, database,
VPN connectivity, or legacy bearer access. Its single tool is synthetic.
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
from policy import STAGING_RESOURCE, STYTCH_TEST_ISSUER, permitted_test_identity


def build_oauth_config() -> OAuthConfig:
    config = OAuthConfig.from_env()
    if config.mode != "oauth":
        raise RuntimeError("Staging MCP must run in strict OAuth mode")
    if (config.resource != STAGING_RESOURCE or config.issuer != STYTCH_TEST_ISSUER
            or config.jwks_url != STYTCH_TEST_ISSUER + "/.well-known/jwks.json"):
        raise RuntimeError("Staging MCP issuer, JWKS, and resource must match pinned Test values")
    return config


config = build_oauth_config()
verifier = OAuthVerifier(config)
expected_client = os.getenv("PANADAN_STAGING_CLIENT_ID", "")
expected_subject_sha256 = os.getenv("PANADAN_STAGING_SUBJECT_SHA256", "")

mcp = MCPServer(
    "Panadan Stytch OAuth Staging",
    version="0.1.0",
    instructions="Test-only synthetic MCP endpoint. No Panadan reporting or customer data.",
)
READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)


def approved_bearer(headers: dict[str, str]) -> bool:
    auth = headers.get("authorization", "")
    raw = auth[7:] if auth.startswith("Bearer ") else ""
    if not raw:
        return False
    details = verifier.verify_details(raw)
    return permitted_test_identity(details, expected_client, expected_subject_sha256)


@mcp.tool(title="Synthetic staging access", annotations=READ_ONLY)
def get_staging_access(ctx: Context) -> dict:
    """Return only synthetic staging status for the permitted test subject/client."""
    if not approved_bearer(ctx.headers or {}):
        return {"error": "permission_denied"}
    return {
        "environment": "stytch-test",
        "data": "synthetic-only",
        "actor": "authorized-test-member",
        "capabilities": ["mcp:staging:read"],
    }


class TestOAuthBearerGate:
    """Guard every MCP request before SDK transport, without logging bearer."""
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.inner(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        headers = {key.decode("latin1").lower(): value.decode("latin1")
                   for key, value in scope.get("headers", [])}
        if not approved_bearer(headers):
            challenge = (
                'Bearer realm="panadan-mcp-staging", '
                f'resource_metadata="{config.metadata_url}", '
                f'scope="{config.scope}"'
            )
            body = b'{"error":"unauthorized"}'
            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"cache-control", b"no-store"),
                    (b"www-authenticate", challenge.encode("ascii")),
                ],
            })
            await send({"type": "http.response.body", "body": body})
            return
        await self.inner(scope, receive, send)


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with mcp.session_manager.run():
        yield


app = FastAPI(
    title="Panadan MCP OAuth Staging",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "environment": "stytch-test", "data": "synthetic-only"}


@app.get("/.well-known/oauth-protected-resource", include_in_schema=False)
@app.get("/.well-known/oauth-protected-resource/mcp", include_in_schema=False)
def protected_resource_metadata():
    return JSONResponse(config.metadata(), headers={"Cache-Control": "no-store"})


app.mount(
    "/mcp",
    TestOAuthBearerGate(
        mcp.streamable_http_app(
            streamable_http_path="/",
            stateless_http=True,
            json_response=True,
            host="0.0.0.0",
            transport_security=TransportSecuritySettings(
                enable_dns_rebinding_protection=True,
                allowed_hosts=[
                    "panadan-mcp-oauth-staging.vercel.app",
                    "localhost:*",
                    "127.0.0.1:*",
                ],
                allowed_origins=[
                    "https://panadan-stytch-oauth-staging.vercel.app",
                    "https://panadan-mcp-oauth-staging.vercel.app",
                    "http://localhost:*",
                    "http://127.0.0.1:*",
                ],
            ),
        )
    ),
)
