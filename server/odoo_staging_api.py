"""Isolated staging-only local-mirror REST router.

Do not attach to the live Panadan app without the explicit staging gate in
main.py. Existing /api/v1/calls, dashboard, and MCP continue using Odoo.
Raw source data is never logged. HTTP query parameters cannot grant operator
access: the authenticated token owner determines numeric operator scopes.
"""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Callable

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from . import odoo_local_reporting as reporting
from . import odoo_sensitive_detail as sensitive

ConnectionFactory = Callable[[], AbstractContextManager]


def _bearer(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    # Don't accept Basic, arbitrary whitespace, or malformed Bearer strings.
    if (not authorization.startswith("Bearer ")
            or len(authorization) > 280):
        raise HTTPException(401, "A valid API bearer token is required",
                            headers={"WWW-Authenticate": "Bearer"})
    token = authorization[7:]
    if not token or any(ch.isspace() for ch in token):
        raise HTTPException(401, "A valid API bearer token is required",
                            headers={"WWW-Authenticate": "Bearer"})
    return token


def _failure(error: Exception):
    # All backend errors are indistinguishable to the client. Do not log
    # parameters, SQL, PII, DSNs, secret tokens, or exception text.
    if isinstance(error, PermissionError):
        raise HTTPException(403, "Operator permission denied") from None
    if isinstance(error, ValueError):
        raise HTTPException(503, "Local mirror unavailable") from None
    raise HTTPException(503, "Local mirror unavailable") from None


def create_router(
    auth_store, *,
    open_reporting: ConnectionFactory,
    open_sensitive: ConnectionFactory,
) -> APIRouter:
    """Create only the staging REST routes with injected restricted connections.

    Connection factories must establish authenticated PG18 reader roles. Each
    library operation independently verifies current_user/database/version.
    Neither factory is invoked until an HTTP request is authenticated.
    """
    router = APIRouter(
        prefix="/api/v1/local-mirror", tags=["Local mirror (staging)"],
        include_in_schema=False,
    )

    @router.get("/calls")
    def calls(request: Request,
              after_id: int = Query(0, ge=0, le=999_999_999),
              limit: int = Query(50, ge=1, le=100)):
        token = _bearer(request)
        try:
            if not auth_store.verify_token(token, "api:read", "calls:read"):
                raise HTTPException(401, "Invalid or insufficient API token",
                                    headers={"WWW-Authenticate": "Bearer"})
            with open_reporting() as conn:
                items = reporting.list_calls_for_token(
                    conn, auth_store, token=token,
                    after_id=after_id, limit=limit)
            return JSONResponse(
                {"items": items}, headers={"Cache-Control": "no-store"})
        except HTTPException:
            raise
        except Exception as exc:
            _failure(exc)

    @router.get("/count")
    def count(request: Request):
        token = _bearer(request)
        try:
            if not auth_store.verify_token(token, "api:read", "calls:read"):
                raise HTTPException(401, "Invalid or insufficient API token",
                                    headers={"WWW-Authenticate": "Bearer"})
            with open_reporting() as conn:
                total = reporting.count_calls_for_token(
                    conn, auth_store, token=token)
            return JSONResponse(
                {"count": total}, headers={"Cache-Control": "no-store"})
        except HTTPException:
            raise
        except Exception as exc:
            _failure(exc)

    @router.get("/calls/{call_id}")
    def call(request: Request, call_id: int):
        token = _bearer(request)
        if not 1 <= call_id <= 999_999_999:
            raise HTTPException(404, "Call not found")
        try:
            if not auth_store.verify_token(token, "api:read", "calls:read"):
                raise HTTPException(401, "Invalid or insufficient API token",
                                    headers={"WWW-Authenticate": "Bearer"})
            with open_reporting() as conn:
                item = reporting.get_call_for_token(
                    conn, auth_store, token=token, call_id=call_id)
            if item is None:
                raise HTTPException(404, "Call not found")
            return JSONResponse(item, headers={"Cache-Control": "no-store"})
        except HTTPException:
            raise
        except Exception as exc:
            _failure(exc)

    @router.get("/sensitive/calls/{call_id}")
    def sensitive_call(request: Request, call_id: int):
        token = _bearer(request)
        if not 1 <= call_id <= 999_999_999:
            raise HTTPException(404, "Call not found")
        try:
            # Pre-authenticate *before opening* the sensitive PG connection.
            required = ("calls:read", "calls:sensitive",
                        "calls:transcript:read")
            if not all(auth_store.verify_token(
                    token, "api:sensitive", capability) for capability in required):
                raise HTTPException(401, "Invalid or insufficient sensitive token",
                                    headers={"WWW-Authenticate": "Bearer"})
            with open_sensitive() as conn:
                # This library writes the durable sensitive-access audit
                # before querying the dedicated sensitive SQL view.
                item = sensitive.get_sensitive_call_for_token(
                    conn, auth_store, token=token, call_id=call_id)
            if item is None:
                raise HTTPException(404, "Call not found")
            return JSONResponse(item, headers={"Cache-Control": "no-store"})
        except HTTPException:
            raise
        except Exception as exc:
            _failure(exc)

    return router
