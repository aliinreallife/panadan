"""Optional standalone, loopback-only mirror staging API.

Do NOT mount this router on live Panadan. Running with the existing Web
container, production auth DB or Odoo connection must refuse startup.
There is deliberately no scheduler, source importer, MCP or public ingress.
This module is inactive unless PANADAN_LOCAL_MIRROR_STAGING_ENABLE=YES.

For isolated testing only:
    uvicorn server.odoo_staging_app:app --host 127.0.0.1 --port 19087
"""
from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from collections.abc import Mapping
import os
import stat

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from mcp.server.transport_security import TransportSecuritySettings
from .odoo_mirror_mcp import create_mirror_mcp

from .security import Store
from .odoo_staging_api import create_router

REPORT_ROLE = "panadan_report_reader"
SENSITIVE_ROLE = "panadan_mirror_sensitive_reader"
_ALLOWED_CONN_KEYS = frozenset((
    "host", "port", "dbname", "user", "password", "sslmode",
    "connect_timeout", "application_name",
))
_LIBPQ_REDIRECT_KEYS = (
    "PGHOST", "PGHOSTADDR", "PGDATABASE", "PGUSER", "PGPORT",
    "PGSERVICE", "PGSERVICEFILE", "PGOPTIONS", "PGPASSFILE",
)


def _private_file(value: str, *, kind: str) -> Path:
    if not isinstance(value, str) or not value or len(value) > 512:
        raise ValueError(f"Explicit private {kind} path required")
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Invalid {kind} path")
    try:
        meta = path.lstat()
        if (not stat.S_ISREG(meta.st_mode)
                or stat.S_IMODE(meta.st_mode) & 0o077
                or meta.st_uid not in (os.geteuid(), 0)
                or not 16 <= meta.st_size <= (4096 if kind == "reader DSN" else 20_000_000)):
            raise ValueError(f"Private {kind} file required")
    except OSError:
        raise ValueError(f"Cannot read private {kind} file") from None
    return path


def _dsn_file(value: str, *, role: str, environ: Mapping[str, str]) -> str:
    path = _private_file(value, kind="reader DSN")
    dsn = path.read_text(encoding="utf-8").strip()
    if "\n" in dsn or "\r" in dsn:
        raise ValueError("Exactly one DSN line required")
    try:
        opts = conninfo_to_dict(dsn)
    except Exception:
        raise ValueError("Malformed staging DSN") from None
    if (set(opts) - _ALLOWED_CONN_KEYS
            or opts.get("host") != "127.0.0.1"
            or opts.get("dbname") != "panadan_ci"
            or opts.get("user") != role
            or not opts.get("password")
            or opts.get("sslmode") not in ("prefer", "require", "verify-full")
            or not (opts.get("port", "").isdigit()
                    and 1 <= int(opts["port"]) <= 65535)):
        raise ValueError("Only loopback disposable PG18 staging readers permitted")
    if any(environ.get(key) for key in _LIBPQ_REDIRECT_KEYS):
        raise ValueError("Unexpected libpq connection override")
    return dsn


def staging_settings(environ: Mapping[str, str]) -> tuple[str, str, str]:
    """Validate every isolation gate BEFORE connecting to the data stores."""
    if (environ.get("PANADAN_LOCAL_MIRROR_STAGING_ENABLE") != "YES"
            or environ.get("PANADAN_LOCAL_MIRROR_STAGING_ISOLATED") != "YES"
            or environ.get("PANADAN_AUTH_BACKEND", "sqlite") != "sqlite"
            or environ.get("PANADAN_PUBLIC_ORIGIN")):
        raise ValueError("Isolated private staging API is not enabled")

    # Require an explicitly disposable SQLite path, not live /data/auth.sqlite.
    auth_path = environ.get("PANADAN_LOCAL_MIRROR_STAGING_AUTH_DB", "")
    if (not auth_path.startswith("/tmp/panadan-mirror-staging-")
            or not auth_path.endswith(".sqlite")):
        raise ValueError("Use an existing disposable staging SQLite authority")
    _private_file(auth_path, kind="staging auth database")
    report_dsn = _dsn_file(
        environ.get("PANADAN_LOCAL_MIRROR_STAGING_REPORT_DSN_FILE", ""),
        role=REPORT_ROLE, environ=environ,
    )
    sensitive_dsn = _dsn_file(
        environ.get("PANADAN_LOCAL_MIRROR_STAGING_SENSITIVE_DSN_FILE", ""),
        role=SENSITIVE_ROLE, environ=environ,
    )
    return auth_path, report_dsn, sensitive_dsn


class _StagingMCPBearerGate:
    """Every transport request needs an active scoped MCP token."""
    def __init__(self, inner, auth_store):
        self.inner = inner
        self.auth_store = auth_store

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.inner(scope, receive, send)
            return
        if scope["type"] != "http":
            await send({"type": "websocket.close", "code": 1008})
            return
        headers = {key.lower(): val for key, val in scope.get("headers", [])}
        authorization = headers.get(b"authorization", b"").decode("latin1")
        token = authorization[7:] if authorization.startswith("Bearer ") else ""
        valid = (1 <= len(token) <= 256
                 and not any(ch.isspace() for ch in token)
                 and self.auth_store.verify_token(
                     token, "mcp:read", "calls:read"))
        if not valid:
            await send({
                "type": "http.response.start", "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"cache-control", b"no-store"),
                    (b"www-authenticate", b'Bearer realm="local-mirror"'),
                ],
            })
            await send({
                "type": "http.response.body",
                "body": b'{"error":"unauthorized"}',
            })
            return
        await self.inner(scope, receive, send)


def create_staging_app(environ: Mapping[str, str] | None = None) -> FastAPI:
    env = os.environ if environ is None else environ
    auth_path, report_dsn, sensitive_dsn = staging_settings(env)
    auth_store = Store(auth_path)

    @contextmanager
    def open_report():
        with psycopg.connect(
            report_dsn, row_factory=dict_row, autocommit=True,
            connect_timeout=5, options="-c statement_timeout=5000",
        ) as conn:
            yield conn

    @contextmanager
    def open_sensitive():
        with psycopg.connect(
            sensitive_dsn, row_factory=dict_row, autocommit=True,
            connect_timeout=5, options="-c statement_timeout=5000",
        ) as conn:
            yield conn

    # Staging has an independent, summary-only MCP tool registry.
    # Never attach these tools to the live Panadan MCP singleton.
    scoped_mcp = create_mirror_mcp(
        auth_store, open_reporting=open_report)

    @asynccontextmanager
    async def lifespan(_app):
        async with scoped_mcp.session_manager.run():
            yield

    instance = FastAPI(
        title="Panadan isolated mirror staging", version="0.0.0-staging",
        docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan,
    )
    # Even if a careless operator starts uvicorn on 0.0.0.0, only the
    # actual TCP loopback peer may access the app. Never trust forwarded
    # IP headers as a replacement for socket-peer validation.
    @instance.middleware("http")
    async def deny_remote_peers(request: Request, call_next):
        remote = request.client.host if request.client else None
        if remote not in ("127.0.0.1", "::1"):
            return JSONResponse({"detail": "Local staging only"}, status_code=403,
                                headers={"Cache-Control": "no-store"})
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    instance.include_router(create_router(
        auth_store, open_reporting=open_report, open_sensitive=open_sensitive,
    ))
    # Only private loopback clients and a valid mcp:read user may reach SDK.
    # The SDK also applies its own exact localhost Host/Origin checks.
    instance.mount("/mcp", _StagingMCPBearerGate(
        scoped_mcp.streamable_http_app(
            streamable_http_path="/",
            stateless_http=True,
            json_response=True,
            host="127.0.0.1",
            transport_security=TransportSecuritySettings(
                enable_dns_rebinding_protection=True,
                allowed_hosts=["localhost:*", "127.0.0.1:*", "[::1]:*"],
                allowed_origins=[
                    "http://localhost:*", "http://127.0.0.1:*",
                ],
            ),
        ),
        auth_store,
    ))
    return instance


# Deliberately absent during normal production imports. Uvicorn refuses a
# disabled staging entrypoint instead of constructing a production fallback.
if os.environ.get("PANADAN_LOCAL_MIRROR_STAGING_ENABLE") == "YES":
    app = create_staging_app()
