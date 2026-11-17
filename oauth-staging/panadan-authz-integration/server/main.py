"""Disposable Stytch Test integration using REAL Panadan permission code.

This is not the Panadan production server and contains NO Odoo access.
The exact MCPBearerGate, OAuthVerifier, Store, field policy and MCP tool
functions are retained from the reviewed PR. Reporting is a synthetic stub.
The test-only first-use account binding is not a production onboarding flow.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from mcp.server.transport_security import TransportSecuritySettings

from . import database
from .mcp_tools import mcp
from .security import Store
from .oauth_mcp import OAuthConfig, OAuthVerifier
from .staging_discovery import VerifiedDiscoveryGate
import jwt

TEST_ISSUER = "https://viridian-faucet-2753.customers.stytch.dev"
TEST_RESOURCE = "https://panadan-authz-integration-staging.vercel.app/mcp/"
TEST_JWKS = TEST_ISSUER + "/.well-known/jwks.json"
CLIENT_PATTERN = re.compile(r"connected-app-test-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z", re.I)
HASH_PATTERN = re.compile(r"[0-9a-f]{64}\Z")

if os.getenv("PANADAN_INTEGRATION_STAGING_ENABLE") != "YES":
    raise RuntimeError("synthetic integration requires explicit staging flag")
if os.getenv("PANADAN_MCP_AUTH_MODE") != "oauth":
    raise RuntimeError("this app requires OAuth-only mode")
if not database.SYNTHETIC_ONLY:
    raise RuntimeError("synthetic-only reporting backend is mandatory")
if any(os.getenv(k) for k in ("PGHOST", "PGUSER", "PGPASSWORD", "PGDATABASE",
                               "PANADAN_AUTH_STAGING_DSN", "PANADAN_AUTH_DB")):
    raise RuntimeError("production/remote database credentials are forbidden here")

oauth_config = OAuthConfig.from_env()
if (oauth_config.issuer != TEST_ISSUER or oauth_config.resource != TEST_RESOURCE
        or oauth_config.jwks_url != TEST_JWKS
        or oauth_config.scope != "panadan:mcp:read"
        or oauth_config.max_ttl_seconds > 3600):
    raise RuntimeError("synthetic integration must pin Stytch Test and own exact audience")
oauth_verifier = OAuthVerifier(oauth_config)

approved_client = os.getenv("PANADAN_INTEGRATION_APPROVED_CLIENT_ID", "").strip()
# Stytch CIMD authorizes using ChatGPT's HTTPS metadata URL, but the
# *signed access token* contains Stytch's internal connected-app-test UUID.
# Never mistake the public metadata URL for the JWT client_id.
CHATGPT_STYTCH_CLIENT_ID = os.getenv(
    "PANADAN_INTEGRATION_CHATGPT_STYTCH_CLIENT_ID", ""
).strip()
subject_hash = os.getenv("PANADAN_INTEGRATION_TEST_SUBJECT_SHA256", "").strip()
if not CLIENT_PATTERN.fullmatch(approved_client) or not HASH_PATTERN.fullmatch(subject_hash):
    raise RuntimeError("explicit approved Test client and Test-member hash are required")
if CHATGPT_STYTCH_CLIENT_ID and not CLIENT_PATTERN.fullmatch(CHATGPT_STYTCH_CLIENT_ID):
    raise RuntimeError("ChatGPT Test client must be Stytch's exact signed client UUID")
APPROVED_CLIENTS = frozenset(
    [approved_client] + ([CHATGPT_STYTCH_CLIENT_ID] if CHATGPT_STYTCH_CLIENT_ID else [])
)

# /tmp is local to one disposable Vercel function instance, never durable.
# The actual Panadan Store class handles grants and local revocations.
sqlite_path = "/tmp/panadan-authz-integration-synthetic.sqlite"
store = Store(sqlite_path)
store.bootstrap("synthetic_bootstrap_admin", secrets.token_urlsafe(32))
with store.db() as _c:
    _row = _c.execute("SELECT id FROM users WHERE username='synthetic_reader'").fetchone()
if _row:
    synthetic_user_id = int(_row["id"])
else:
    synthetic_user_id = store.create_user(
        "synthetic_reader", secrets.token_urlsafe(32), "analyst",
        ["calls:read", "mcp:use"], fields=["id", "CALLDATE"])

def directory_operator_names(destination=None, team=None):
    # Never open the source operator directory or query Odoo.
    return []

_provision_lock = threading.RLock()
_provisioned_clients: set[str] = set()

def _token_rejection_reason(raw: str) -> str:
    """Diagnostics only: never use partially verified claims for authorization."""
    try:
        if len(raw) > 8192 or raw.count(".") != 2:
            return "invalid_token_shape"
        header = jwt.get_unverified_header(raw)
        if header.get("alg") != "RS256":
            return "unexpected_token_algorithm"
        key = oauth_verifier.jwks.get_signing_key_from_jwt(raw)
        # Signature verification is mandatory even for *diagnostic* claims.
        claims = jwt.decode(
            raw, key.key, algorithms=["RS256"],
            options={"verify_aud": False, "verify_iss": False,
                     "verify_exp": False, "verify_nbf": False,
                     "verify_iat": False},
        )
        if claims.get("iss") != TEST_ISSUER:
            return "issuer_mismatch"
        audience = claims.get("aud", [])
        if TEST_RESOURCE not in ([audience] if isinstance(audience, str) else
                                audience if isinstance(audience, list) else []):
            return "audience_mismatch"
        scopes = claims.get("scope", claims.get("scp", ""))
        granted = scopes.split() if isinstance(scopes, str) else (
            scopes if isinstance(scopes, list) else [])
        if "panadan:mcp:read" not in granted:
            return "scope_missing"
        if not claims.get("client_id") and not claims.get("azp"):
            return "signed_client_id_missing"
        return "jwt_other_validation"
    except Exception:
        return "signature_or_claim_rejected"


def provision_disposable_identity(raw: str) -> bool:
    """An exact approved, signed Stytch client and pinned Test member can seed
    one disposable synthetic grant per client and serverless instance.
    Never use this first-use bootstrap for production data.
    """
    details = oauth_verifier.verify_details(raw)
    if not details:
        print("panadan_test_auth stage=" + _token_rejection_reason(raw), flush=True)
        return False
    client_id = details.get("client_id")
    if not isinstance(client_id, str) or client_id not in APPROVED_CLIENTS:
        print("panadan_test_auth stage=client_not_approved", flush=True)
        return False
    digest = hashlib.sha256(details["subject"].encode("utf-8")).hexdigest()
    if not hmac.compare_digest(digest, subject_hash):
        print("panadan_test_auth stage=test_subject_not_approved", flush=True)
        return False
    with _provision_lock:
        if client_id in _provisioned_clients:
            return False
        actor = store.actor_for_oauth(oauth_config.issuer, details["subject"])
        if actor is None:
            store.bind_oauth_identity(oauth_config.issuer, details["subject"], synthetic_user_id)
            actor = synthetic_user_id
        # If this grant is locally revoked, do not re-provision it.
        if store.client_grants(actor, client_id) is None:
            store.approve_mcp_client(
                actor, client_id, ["mcp:use", "calls:read"], ["id", "CALLDATE"]
            )
        _provisioned_clients.add(client_id)
    return True


class PinnedTestSubjectProvisioning:
    """Allow only validated Test tokens to initialize disposable local consent.
    This is an isolated test fixture; production identity bindings are admin-only.
    """
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path", "").startswith("/mcp"):
            headers = {k.lower(): v for k, v in scope.get("headers", [])}
            auth = headers.get(b"authorization", b"").decode("latin1")
            if auth.startswith("Bearer "):
                provision_disposable_identity(auth[7:])
        await self.inner(scope, receive, send)


# Production MCPBearerGate below is copied byte-for-byte from server/main.py.
# CI explicitly checks the AST/source of this class against the original.


class MCPBearerGate:
    """Authenticate MCP requests, and audit their method/tool without payloads.

    We only inspect the first 8 KiB of a JSON-RPC request in memory to discover
    a known tool name. The request bytes are passed unchanged to the SDK.
    Never persist tool arguments, transcript text, headers or bearer tokens.
    """
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope['type'] not in ('http', 'websocket'):
            await self.inner(scope, receive, send)
            return
        if scope['type'] != 'http':
            await send({'type': 'websocket.close', 'code': 1008})
            return
        start = time.monotonic()
        headers = {k.lower(): v for k, v in scope.get('headers', [])}
        auth = headers.get(b'authorization', b'').decode('latin1')
        raw = auth[7:] if auth.startswith('Bearer ') else ''
        actor = None
        if oauth_config.mode == 'oauth':
            details = oauth_verifier.verify_details(raw) if oauth_verifier else None
            # An IdP's signed subject alone does not identify the AI client.
            # An unconsented, signed client may discover consent instructions,
            # but a token with no signed client identity is rejected here.
            valid = bool(details and details.get('client_id') and
                         store.oauth_identity_has_mcp_access(
                             oauth_config.issuer, details['subject']))
            if valid:
                actor = store.actor_for_oauth(oauth_config.issuer, details['subject'])
        else:
            valid = store.verify_token(raw, 'mcp:read')
            if valid: actor=store.actor_for_token(raw, 'mcp:read')
        def record(action, status_code):
            try:
                store.record_activity(
                    user_id=actor, surface='mcp', action=action,
                    http_status=status_code,
                    duration_ms=int((time.monotonic()-start)*1000),
                )
            except Exception:
                pass

        if not valid:
            challenge = 'Bearer realm="panadan-mcp"'
            if oauth_config.mode == 'oauth':
                challenge += (f', resource_metadata="{oauth_config.metadata_url}", '
                              f'scope="{oauth_config.scope}"')
            body = b'{"error":"unauthorized"}'
            await send({'type': 'http.response.start', 'status': 401, 'headers': [
                (b'content-type', b'application/json'),
                (b'cache-control', b'no-store'),
                (b'www-authenticate', challenge.encode('ascii')),
            ]})
            await send({'type': 'http.response.body', 'body': body})
            record('MCP unauthorized',401)
            return

        prefix = bytearray()
        overflow = False
        result_status = 500
        async def inspect_receive():
            nonlocal overflow
            message = await receive()
            if message.get('type') == 'http.request':
                data = message.get('body', b'')
                if len(prefix) + len(data) > 8192:
                    overflow = True
                elif not overflow:
                    prefix.extend(data)
            return message

        async def inspect_send(message):
            nonlocal result_status
            if message.get('type') == 'http.response.start':
                result_status = message.get('status', 500)
            await send(message)

        try:
            await self.inner(scope, inspect_receive, inspect_send)
        finally:
            action = 'MCP '+scope.get('method','POST').upper()
            if not overflow and prefix:
                try:
                    message=json.loads(prefix)
                    if isinstance(message, dict):
                        method=message.get('method','')
                        if method in ('initialize','tools/list','tools/call',
                                      'resources/list','ping','notifications/initialized'):
                            action='MCP '+method
                            if method=='tools/call':
                                name=(message.get('params') or {}).get('name')
                                allowed={tool.name for tool in mcp._tool_manager.list_tools()}
                                if isinstance(name,str) and name in allowed:
                                    action+=':'+name
                except (ValueError, TypeError, AttributeError):
                    pass
            record(action, result_status)




# Only these synthetic endpoints are published; no dashboards or real APIs.
@asynccontextmanager
async def lifespan(_: FastAPI):
    async with mcp.session_manager.run():
        yield


app = FastAPI(
    title="Panadan Stytch Test Permission Integration",
    docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan,
)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "environment": "stytch-test",
            "data": "synthetic-only", "authorization": "panadan-real-policy"}


@app.get("/.well-known/oauth-protected-resource", include_in_schema=False)
@app.get("/.well-known/oauth-protected-resource/mcp", include_in_schema=False)
def protected_resource_metadata():
    return JSONResponse(oauth_config.metadata(), headers={"Cache-Control": "no-store"})


_mcp_transport = mcp.streamable_http_app(
    streamable_http_path="/",
    stateless_http=True,
    json_response=True,
    host="0.0.0.0",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[
            "panadan-authz-integration-staging.vercel.app",
            "127.0.0.1:*", "localhost:*",
        ],
        allowed_origins=[
            "https://panadan-authz-integration-staging.vercel.app",
            "https://panadan-stytch-oauth-staging.vercel.app",
            "http://127.0.0.1:*", "http://localhost:*",
        ],
    ),
)
app.mount(
    "/mcp",
    PinnedTestSubjectProvisioning(
        VerifiedDiscoveryGate(
            MCPBearerGate(_mcp_transport),
            _mcp_transport,
            oauth_verifier.verify_details,
        )
    ),
)
