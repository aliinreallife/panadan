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
from .knowledge_authorization import AccessDenied, WORKSPACE_CAPABILITIES
from .knowledge_configuration import ConfigurationChanged
from .knowledge_identity import SQLiteIdentityBridge
from .knowledge_objectives import OutputField
from .knowledge_resource_views import PAGES as RESOURCE_PAGES, ResourceFilters, parse_uuid
from .knowledge_scope import ScopedWorkspace
from .knowledge_studio_views import PAGES as STUDIO_PAGES
from .security import Store, has_capability

# Chromium sends Origin: null on form POST from a no-referrer document.
# Keep same-origin forms usable without sending workspace URLs off-site.
HEADERS = {"Cache-Control": "no-store, private", "Pragma": "no-cache",
           "Referrer-Policy": "same-origin", "X-Content-Type-Options": "nosniff",
           "Content-Security-Policy": "default-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"}
PAGES = {"overview": "مرور کلی", "members": "اعضا", "roles": "نقش‌ها و دسترسی",
         "resources": "منابع", "resource": "جزئیات تماس", "integrations": "اتصال‌ها",
         "objectives": "اهداف دانش", "pipelines": "خطوط پردازش", "runs": "اجراها"}
LABELS = {"workspace.read": "مشاهده فضای کاری", "members.manage": "مدیریت اعضا",
          "roles.manage": "مدیریت نقش‌ها و دسترسی", "resource.list": "فهرست منابع",
          "resource.read": "مشاهده منبع", "representation.read": "مشاهده متن پالایش‌شده",
          "objective.configure": "تنظیم اهداف دانش", "pipeline.configure": "تنظیم خطوط پردازش",
          "pipeline.run": "اجرای خطوط پردازش"}
ACTIONS = {"add_member": "members", "revoke_membership": "members",
           "create_role": "roles", "assign_role": "roles", "grant_scope": "roles",
           "revoke_scope": "roles", "revoke_role": "roles", "retire_role": "roles"}


@dataclass(frozen=True)
class PreviewConfig:
    port: int
    installation: UUID
    candidates: tuple[UUID, ...]
    resources: bool = False
    studio: bool = False
    objective_authoring: bool = False

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
        resources = env.get("PANADAN_KNOWLEDGE_PREVIEW_RESOURCES") == "YES"
        studio = env.get("PANADAN_KNOWLEDGE_PREVIEW_STUDIO") == "YES"
        authoring = env.get("PANADAN_KNOWLEDGE_PREVIEW_OBJECTIVE_AUTHORING") == "YES"
        if (studio and not resources) or (authoring and not studio):
            raise ValueError("Studio requires the isolated resource preview")
        return cls(int(raw_port),installation,candidates,resources,studio,authoring)


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
            yield ScopedWorkspace(conn,bridge,enabled=True,resources=config.resources,studio=config.studio,
                                  objective_authoring=config.objective_authoring)

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
                or (page in RESOURCE_PAGES and not config.resources) or (page in STUDIO_PAGES and not config.studio)):
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

    @router.post("/{workspace_id}/objective")
    def objective(request: Request, workspace_id: str, csrf: str=Form(...), key: str=Form(...),
                  label: str=Form(...), purpose: str=Form(...), expected_revision: int=Form(...),
                  policy: str=Form(""), template: str=Form(""), field: str=Form(""), kind: str=Form("text")):
        raw,session=auth(request)
        if (not config.objective_authoring or not session
                or not hmac.compare_digest(csrf.encode("utf-8"),session["csrf"].encode("utf-8"))
                or not valid_form_origin(request,None)):
            return denied(request)
        try:
            workspace=parse_uuid(workspace_id)
            if workspace not in config.candidates:
                return denied(request)
            options={}
            if expected_revision == 0:
                if bool(template) == bool(field):
                    raise ValueError("Choose a template or a custom field")
                options=dict(validation_policy=parse_uuid(policy),template_key=template or None,
                             fields=(OutputField(field,kind,True),) if field else None)
            with scoped() as svc:
                svc.objective_command(raw,workspace,key=key,label=label,purpose=purpose,
                                      expected_revision=expected_revision,**options)
            return RedirectResponse(f"/workspace/{workspace}/objectives",303,headers=HEADERS)
        except ConfigurationChanged:
            return render(request,status_code=409,error=True,message="نسخهٔ هدف تغییر کرده است. صفحه را تازه کنید.")
        except ValueError:
            return render(request,status_code=400,error=True,message="اطلاعات هدف کامل یا معتبر نیست.")
        except (AccessDenied,psycopg.IntegrityError):
            return denied(request)
        except psycopg.Error:
            return unavailable(request)

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
                if not capabilities or len(capabilities)>len(WORKSPACE_CAPABILITIES):
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
