"""Opt-in Persian workspace UI using existing browser authentication.

No production activation, profile installer, login creation or global
workspace discovery. The explicitly configured synthetic workspace UUIDs
are candidates only; each is resolved through the trusted scope boundary.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
import hmac
import os
import re
from uuid import UUID

import psycopg
from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from .ingress import valid_form_origin
from .knowledge_authorization import AccessDenied, CAPABILITIES
from .knowledge_identity import SQLiteIdentityBridge
from .knowledge_resource_views import PAGES as RESOURCE_PAGES, ResourceFilters, parse_uuid
from .knowledge_scope import ScopedWorkspace
from .security import Store, has_capability

# Chromium sends Origin: null on form POST from a no-referrer document.
# Keep same-origin forms usable without sending workspace URLs off-site.
HEADERS = {"Cache-Control": "no-store, private", "Pragma": "no-cache",
           "Referrer-Policy": "same-origin", "X-Content-Type-Options": "nosniff",
           "Content-Security-Policy": "default-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"}
PAGES = {"overview": "مرور کلی", "members": "اعضا", "roles": "نقش‌ها و دسترسی",
         "resources": "منابع", "resource": "جزئیات تماس", "integrations": "اتصال‌ها"}
LABELS = {"workspace.read": "مشاهده فضای کاری", "members.manage": "مدیریت اعضا",
          "roles.manage": "مدیریت نقش‌ها و دسترسی", "resource.list": "فهرست منابع",
          "resource.read": "مشاهده منبع", "representation.read": "مشاهده متن پالایش‌شده"}
ACTIONS = {"add_member": "members", "revoke_membership": "members",
           "create_role": "roles", "assign_role": "roles", "grant_scope": "roles",
           "revoke_scope": "roles", "revoke_role": "roles", "retire_role": "roles"}


@dataclass(frozen=True)
class PreviewConfig:
    port: int
    installation: UUID
    candidates: tuple[UUID, ...]
    resources: bool = False

    @classmethod
    def from_env(cls, env):
        if env.get("PANADAN_KNOWLEDGE_PREVIEW") != "YES":
            return None
        if (env.get("PANADAN_KNOWLEDGE_PREVIEW_ISOLATED") != "YES"
                or env.get("PANADAN_AUTH_BACKEND","sqlite") != "sqlite"
                or env.get("PANADAN_PUBLIC_ORIGIN")
                or env.get("PANADAN_COOKIE_SECURE") != "false"
                or any(value for key,value in env.items() if key.startswith("PG"))):
            raise ValueError("Workspace preview requires isolated local SQLite and no source credentials")
        raw_port=env.get("PANADAN_KNOWLEDGE_PREVIEW_PORT","")
        if not re.fullmatch(r"[0-9]{1,5}",raw_port) or not 1<=int(raw_port)<=65535:
            raise ValueError("Explicit disposable PostgreSQL port required")
        try:
            installation=UUID(env["PANADAN_KNOWLEDGE_PREVIEW_INSTALLATION"])
            candidates=tuple(dict.fromkeys(UUID(x) for x in env["PANADAN_KNOWLEDGE_PREVIEW_WORKSPACES"].split(",")))
            if not installation.int or not 1<=len(candidates)<=16 or any(not x.int for x in candidates):
                raise ValueError()
        except (KeyError,ValueError):
            raise ValueError("Explicit synthetic installation and workspace candidates required") from None
        return cls(int(raw_port),installation,candidates,env.get("PANADAN_KNOWLEDGE_PREVIEW_RESOURCES") == "YES")


def build_router(store: Store, templates, config: PreviewConfig, *, cookie_name="panadan_session"):
    if type(store) is not Store:
        raise ValueError("Existing SQLite authority required")
    bridge=SQLiteIdentityBridge(store,config.installation)
    router=APIRouter(prefix="/workspace",include_in_schema=False)

    @contextmanager
    def scoped():
        # Fixed disposable login; no caller-supplied DSN or environment-based
        # libpq target selection. All PG variables are refused at activation.
        if any(value for key,value in os.environ.items() if key.startswith("PG")):
            raise AccessDenied("Access denied")
        with psycopg.connect(host="127.0.0.1",port=config.port,dbname="panadan_ci",
                user="panadan_knowledge_test_login",password="synthetic_knowledge_test_only",
                connect_timeout=3,autocommit=True,sslmode="disable") as conn:
            yield ScopedWorkspace(conn,bridge,enabled=True,resources=config.resources)

    def render(request, **context):
        status=context.pop("status_code",200)
        return templates.TemplateResponse(request,"knowledge_workspace.html",
            {"pages":PAGES,"labels":LABELS,"choices":[],"data":None,"page":"overview",
             "csrf":"","legacy":False,"message":"","error":False,**context},
            status_code=status,headers=HEADERS)

    def denied(request):
        return render(request,status_code=404,error=True,message="فضای کاری در دسترس نیست یا مجوز لازم را ندارید.")

    def unavailable(request):
        return render(request,status_code=503,error=True,message="ارتباط با فضای کاری برقرار نشد. برای بررسی مجدد، صفحه را تازه کنید.")

    def auth(request):
        raw=request.cookies.get(cookie_name)
        if bridge.resolve_session(raw) is None:
            return None,None
        return raw,store.session(raw)

    def choices_for(svc,raw):
        choices=[]
        for candidate in config.candidates:
            try:
                choices.append(svc.read_workspace(raw,candidate))
            except AccessDenied:
                continue
        return choices

    def base_context(session):
        return {"csrf":session["csrf"],"username":session["username"],
                "legacy":has_capability(session,"calls:read") or has_capability(session,"metrics:read")}

    @router.get("")
    def index(request: Request):
        raw,session=auth(request)
        if not session:
            return denied(request)
        try:
            with scoped() as svc:
                choices=choices_for(svc,raw)
                if bridge.resolve_session(raw) is None:
                    return denied(request)
                return render(request,choices=choices,**base_context(session))
        except (AccessDenied,psycopg.Error):
            return unavailable(request)

    def workspace_page(request, workspace_id, page, resource_id=None, filters=None):
        raw,session=auth(request)
        try:
            workspace=UUID(workspace_id)
        except ValueError:
            return denied(request)
        if (not session or workspace not in config.candidates or page not in PAGES
                or (page in RESOURCE_PAGES and not config.resources)):
            return denied(request)
        try:
            with scoped() as svc:
                choices=choices_for(svc,raw)
                data=svc.ui_view(raw,workspace,page,resource_id=resource_id,filters=filters)
                if bridge.resolve_session(raw) is None:
                    return denied(request)
                return render(request,choices=choices,data=data,page=page,**base_context(session))
        except AccessDenied:
            return denied(request)
        except psycopg.Error:
            return unavailable(request)

    @router.get("/{workspace_id}/resources/{resource_id}")
    def resource_detail(request: Request, workspace_id: str, resource_id: str,
                        source: str="", call: str="", state: str="", after: str=""):
        try:
            filters = ResourceFilters.parse(source, call, state, after)
            key = parse_uuid(resource_id)
        except AccessDenied:
            return denied(request)
        return workspace_page(request,workspace_id,"resource",resource_id=key,filters=filters)

    @router.get("/{workspace_id}/{page}")
    def page(request: Request, workspace_id: str, page: str,
             source: str="", call: str="", state: str="", after: str=""):
        try:
            filters = ResourceFilters.parse(source, call, state, after) if page == "resources" else None
        except AccessDenied:
            return denied(request)
        return workspace_page(request,workspace_id,page,filters=filters)

    @router.post("/{workspace_id}/command")
    def command(request: Request, workspace_id: str, operation: str=Form(...),
                csrf: str=Form(...), target: str=Form(""), role: str=Form(""),
                role_key: str=Form(""), name: str=Form(""),
                capabilities: list[str]=Form([]), capability: str=Form(""),
                valid_until: str=Form(""), confirm: str=Form("")):
        raw,session=auth(request)
        try:
            workspace=UUID(workspace_id)
        except ValueError:
            return denied(request)
        if (not session or workspace not in config.candidates or operation not in ACTIONS
                or not hmac.compare_digest(csrf.encode("utf-8"),session["csrf"].encode("utf-8"))
                or not valid_form_origin(request,None)
                or ((operation.startswith("revoke_") or operation=="retire_role") and confirm!="yes")):
            return denied(request)
        try:
            until=None
            if valid_until:
                if len(valid_until)>40:
                    raise ValueError()
                until=datetime.fromisoformat(valid_until)
                if until.tzinfo is None:
                    raise ValueError()
            kwargs={}
            if operation=="create_role":
                if not capabilities or len(capabilities)>len(CAPABILITIES):
                    raise ValueError()
                args=(role_key,name,capabilities)
            elif operation=="assign_role":
                args=(UUID(target),UUID(role))
                kwargs={"valid_until":until}
            elif operation=="grant_scope":
                args=(UUID(target),capability)
                kwargs={"valid_until":until}
            else:
                args=(UUID(target),)
            with scoped() as svc:
                svc.ui_command(raw,workspace,operation,*args,**kwargs)
            # Post/redirect/get; no sensitive result or stale form data cached.
            return RedirectResponse(f"/workspace/{workspace}/{ACTIONS[operation]}",303,headers=HEADERS)
        except (AccessDenied,ValueError,psycopg.IntegrityError):
            return denied(request)
        except psycopg.Error:
            return unavailable(request)
    return router
