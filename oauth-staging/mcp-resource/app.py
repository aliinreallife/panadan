"""Standalone, synthetic-only WorkOS OAuth MCP test resource.

Does not import Panadan's production store, users, queries or report tools.
Only the public WorkOS staging issuer and pre-registered test client are accepted.
The exact user subject must be configured out of band; defaults deny all tools.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
import hmac
import os
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from mcp.server.mcpserver import MCPServer, Context
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from oauth_mcp import OAuthConfig, OAuthVerifier
from oauth_discovery import VerifiedOAuthDiscovery

ISSUER = "https://artistic-environment-06-staging.authkit.app"
RESOURCE = "https://panadan-mcp-oauth-staging.vercel.app/mcp/"
CLIENT_ID = "client_01M8165V9W1G296975A3X3CACM"
SCOPE = "panadan:mcp:read"

# No configuration accepts the real dan.panafor.com MCP audience.
config = OAuthConfig(
    mode="oauth",
    issuer=ISSUER,
    jwks_url=ISSUER + "/oauth2/jwks",
    resource=RESOURCE,
    scope=SCOPE,
    max_ttl_seconds=3600,
)
config.validate()
verifier = OAuthVerifier(config)

# Not the WorkOS dashboard user: an already verified *staging end-user*
# whose sub is learned from the staging account lookup. No email is used
# for authorization. Missing env means all tool calls fail closed.
approved_subject = os.environ.get("PANADAN_SANDBOX_WORKOS_SUB", "").strip()
if len(approved_subject) > 256:
    raise RuntimeError("Invalid staging subject setting")


def verified_pilot(headers: dict[str, str]) -> bool:
    value = headers.get("authorization", "")
    if not value.startswith("Bearer "):
        return False
    details = verifier.verify_details(value[7:])
    return bool(
        details
        and approved_subject
        and details.get("client_id") == CLIENT_ID
        and isinstance(details.get("subject"), str)
        and hmac.compare_digest(details["subject"], approved_subject)
    )


mcp = MCPServer(
    "Panadan WorkOS OAuth Sandbox",
    version="0.1.0",
    instructions="WorkOS sandbox only. No user reports, customer data or Panadan database.",
)
READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)


@mcp.tool(title="Verify synthetic OAuth access", annotations=READ_ONLY)
def get_synthetic_access(ctx: Context) -> dict:
    """Return only synthetic OAuth test flags; never report records or user PII."""
    if not verified_pilot(ctx.headers or {}):
        return {"error": "permission_denied"}
    return {
        "environment": "workos-staging",
        "data": "synthetic-only",
        "authorized": True,
        "capabilities": ["synthetic:read"],
    }


class RequireApprovedToken:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.inner(scope, receive, send)
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        headers = {
            k.decode("latin1").lower(): v.decode("latin1")
            for k, v in scope.get("headers", [])
        }
        if not verified_pilot(headers):
            challenge = (
                'Bearer realm="panadan-workos-synthetic", '
                f'resource_metadata="{config.metadata_url}", '
                f'scope="{SCOPE}"'
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
            await send({"type": "http.response.body", "body": b'{"error":"unauthorized"}'})
            return
        return await self.inner(scope, receive, send)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    async with mcp.session_manager.run():
        yield


app = FastAPI(
    title="Panadan Synthetic WorkOS MCP",
    docs_url=None, redoc_url=None, openapi_url=None,
    lifespan=lifespan,
)


@app.get("/healthz", include_in_schema=False)
def healthz():
    return JSONResponse({
        "status": "ok",
        "environment": "workos-staging",
        "data": "synthetic-only",
        "pilot_authorization": "configured" if approved_subject else "not-configured",
    }, headers={"Cache-Control": "no-store"})


@app.get("/.well-known/oauth-protected-resource", include_in_schema=False)
@app.get("/.well-known/oauth-protected-resource/mcp", include_in_schema=False)
def resource_metadata():
    return JSONResponse(config.metadata(), headers={"Cache-Control": "no-store"})


allowed_hosts = [
    urlsplit(RESOURCE).netloc,
    "localhost:*", "127.0.0.1:*",
]
# Vercel's preview deployment hostname is server-supplied, never from
# incoming untrusted Host/X-Forwarded-Host headers.
if os.environ.get("VERCEL_URL", "").endswith(".vercel.app"):
    allowed_hosts.append(os.environ["VERCEL_URL"])
allowed_origins = [
    "https://chatgpt.com",
    "https://panadan-mcp-oauth-staging.vercel.app",
    "http://localhost:*",
    "http://127.0.0.1:*",
]

transport = mcp.streamable_http_app(
    streamable_http_path="/",
    stateless_http=True,
    json_response=True,
    host="0.0.0.0",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    ),
)
app.mount(
    "/mcp",
    VerifiedOAuthDiscovery(
        authenticated_app=RequireApprovedToken(transport),
        metadata_app=transport,
        verify_details=verifier.verify_details,
    ),
)
