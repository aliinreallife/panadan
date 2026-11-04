"""Isolated browser dashboard for approved operator-scoped local mirror.

Standalone staging only; no production Odoo access, hidden global grants,
client-supplied operator IDs, dashboard migration or public ingress.
"""
from __future__ import annotations

import hmac
import secrets

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .ingress import valid_form_origin
from . import odoo_local_reporting as local
from . import odoo_sensitive_detail as detail
from .security import Store, has_capability, SESSION_SECONDS

COOKIE_NAME = "panadan_local_mirror_session"
NONCE_COOKIE = "panadan_local_mirror_login_nonce"
templates = Jinja2Templates(directory="templates")


def create_dashboard_router(auth_store: Store, *, open_reporting,
                            open_sensitive) -> APIRouter:
    """Loopback staging pages. Every read is tied to a real session user."""
    router = APIRouter(prefix="/local", include_in_schema=False)

    def session_for(request: Request):
        session = auth_store.session(request.cookies.get(COOKIE_NAME))
        if not session:
            raise HTTPException(401, "Local mirror login required")
        return session

    def origin_and_csrf(request, csrf: str, session: dict):
        if (not isinstance(csrf, str) or
                not hmac.compare_digest(csrf, session["csrf"])
                or not valid_form_origin(request, None)):
            raise HTTPException(403, "Invalid local mirror request")

    @router.get("/login", response_class=HTMLResponse)
    def login_page(request: Request):
        nonce = secrets.token_urlsafe(24)
        response = templates.TemplateResponse(
            request, "odoo_mirror_local_login.html",
            {"nonce": nonce, "error": False},
            headers={"Cache-Control": "no-store"},
        )
        response.set_cookie(
            NONCE_COOKIE, nonce, httponly=True, secure=False,
            samesite="strict", max_age=600)
        return response

    @router.post("/login")
    def login(request: Request, username: str = Form(...),
              password: str = Form(...), nonce: str = Form(...)):
        existing = request.cookies.get(NONCE_COOKIE, "")
        if (not existing or not hmac.compare_digest(existing, nonce)
                or not valid_form_origin(request, None)):
            raise HTTPException(403, "Expired or invalid local mirror login")
        if auth_store.login_is_throttled(username):
            raise HTTPException(429, "Too many login attempts")
        user_id = auth_store.verify_login(username, password)
        if not user_id:
            auth_store.record_login_failure(username)
            response = RedirectResponse("/local/login?error=1", status_code=303)
            response.delete_cookie(NONCE_COOKIE)
            return response
        auth_store.clear_login_failures(username)
        raw, _ = auth_store.create_session(user_id)
        response = RedirectResponse("/local/dashboard", status_code=303)
        response.set_cookie(
            COOKIE_NAME, raw, httponly=True, secure=False,
            samesite="strict", max_age=SESSION_SECONDS)
        response.delete_cookie(NONCE_COOKIE)
        return response

    @router.post("/logout")
    def logout(request: Request, csrf: str = Form(...),
               session: dict = Depends(session_for)):
        origin_and_csrf(request, csrf, session)
        auth_store.logout(request.cookies.get(COOKIE_NAME))
        response = RedirectResponse("/local/login", status_code=303)
        response.delete_cookie(COOKIE_NAME)
        return response

    @router.get("/dashboard", response_class=HTMLResponse)
    def dashboard(request: Request,
                  after_id: int = Query(0, ge=0, le=999_999_999),
                  session: dict = Depends(session_for)):
        if not has_capability(session, "calls:read"):
            raise HTTPException(403, "Call viewing permission required")
        try:
            with open_reporting() as conn:
                rows = local.list_calls_for_session(
                    conn, auth_store,
                    session_token=request.cookies.get(COOKIE_NAME),
                    after_id=after_id, limit=50)
                count = local.count_calls_for_session(
                    conn, auth_store,
                    session_token=request.cookies.get(COOKIE_NAME))
        except PermissionError:
            raise HTTPException(403, "Operator permission denied") from None
        except Exception:
            raise HTTPException(503, "Local mirror unavailable") from None
        return templates.TemplateResponse(
            request, "odoo_mirror_local_dashboard.html",
            {
                "session": session, "csrf": session["csrf"],
                "calls": rows, "count": count, "after_id": after_id,
                "next_after_id": rows[-1]["call_id"] if rows else None,
                "can_sensitive": all(has_capability(session, cap) for cap in
                                     detail.REQUIRED_CAPABILITIES),
            },
            headers={"Cache-Control": "no-store"},
        )

    @router.get("/calls/{call_id}")
    def call_summary(request: Request, call_id: int,
                     session: dict = Depends(session_for)):
        if not has_capability(session, "calls:read"):
            raise HTTPException(403, "Call viewing permission required")
        if not 1 <= call_id <= 999_999_999:
            raise HTTPException(404, "Call not found")
        try:
            with open_reporting() as conn:
                item = local.get_call_for_session(
                    conn, auth_store,
                    session_token=request.cookies.get(COOKIE_NAME),
                    call_id=call_id)
        except PermissionError:
            raise HTTPException(403, "Operator permission denied") from None
        except Exception:
            raise HTTPException(503, "Local mirror unavailable") from None
        if item is None:
            raise HTTPException(404, "Call not found")
        return JSONResponse(item, headers={"Cache-Control": "no-store"})

    @router.get("/sensitive/calls/{call_id}")
    def call_detail(request: Request, call_id: int,
                    session: dict = Depends(session_for)):
        if not all(has_capability(session, cap)
                   for cap in detail.REQUIRED_CAPABILITIES):
            raise HTTPException(403, "Sensitive call permission required")
        if not 1 <= call_id <= 999_999_999:
            raise HTTPException(404, "Call not found")
        try:
            with open_sensitive() as conn:
                # Authentication is checked again by the detail reader,
                # which durably audits this attempt BEFORE any SQL SELECT.
                item = detail.get_sensitive_call_for_session(
                    conn, auth_store,
                    session_token=request.cookies.get(COOKIE_NAME),
                    call_id=call_id)
        except PermissionError:
            raise HTTPException(403, "Operator permission denied") from None
        except Exception:
            raise HTTPException(503, "Local mirror unavailable") from None
        if item is None:
            raise HTTPException(404, "Call not found")
        return JSONResponse(item, headers={"Cache-Control": "no-store"})

    return router
