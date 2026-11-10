"""FastAPI dashboard, scoped REST API and authenticated MCP Streamable HTTP."""
from __future__ import annotations
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import Literal
import hmac
import os
import secrets
import time
import re
import json
import logging

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette import status

from . import database
from . import mirror_health
from .field_permissions import (capability_fields, effective_fields,
    field_catalog, project_call, project_metrics)
from .permission_catalog import (
    PERMISSION_CATEGORIES, ADMIN_ONLY, ROLE_RECOMMENDED_GROUP,
    group_options, matching_group,
)
from .ingress import allowed_hosts, external_base_url, read_public_origin, valid_form_origin
from .reporting_retries import read_with_retry
from .transcript_ai import transcript_for_ai, MAX_TRANSCRIPT_CHARS
from .mcp_tools import mcp
from mcp.server.transport_security import TransportSecuritySettings
from .oauth_mcp import OAuthConfig, OAuthVerifier
from .security import SESSION_SECONDS, CAPABILITIES, ROLE_GRANTS, permissions, has_capability, is_rate_limited, record_failure
from .auth_store import create_auth_store

# Default remains SQLite. A synthetic loopback PG18 test requires deliberate
# staging-only flags; invalid settings refuse startup with no fallback.
store = create_auth_store()
# Only the explicitly isolated PostgreSQL staging backend has persisted,
# globally unique opaque profile IDs. Keep the production SQLite five-tool
# surface unchanged until an independently approved auth migration.
if os.getenv('PANADAN_AUTH_BACKEND', 'sqlite') == 'postgres-staging':
    from .mcp_profile_staging import register_profile_tool
    register_profile_tool(mcp)
oauth_config = OAuthConfig.from_env()
oauth_verifier = OAuthVerifier(oauth_config) if oauth_config.mode == 'oauth' else None
COOKIE_SECURE = os.getenv('PANADAN_COOKIE_SECURE', 'true').lower() == 'true'
COOKIE_NAME = 'panadan_session'
PUBLIC_ORIGIN = read_public_origin(cookie_secure=COOKIE_SECURE)
templates = Jinja2Templates(directory='templates')
templates.env.filters['date_time'] = lambda value: datetime.fromtimestamp(value, timezone.utc).strftime('%Y-%m-%d %H:%M UTC') if value else '—'
# Date/time are separate isolated runs in RTL templates (clock on the right).
# Token timestamps remain UTC; never silently reinterpret them as Tehran.
templates.env.filters['date_time_day'] = lambda value: datetime.fromtimestamp(value, timezone.utc).strftime('%Y-%m-%d') if value else '—'
templates.env.filters['date_time_clock'] = lambda value: datetime.fromtimestamp(value, timezone.utc).strftime('%H:%M') if value else '—'
templates.env.filters['date_time_iso'] = lambda value: datetime.fromtimestamp(value, timezone.utc).isoformat() if value else ''


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.bootstrap(os.getenv('PANADAN_ADMIN_USER', 'admin'), os.getenv('PANADAN_ADMIN_PASSWORD'))
    async with mcp.session_manager.run():
        yield


app = FastAPI(title='Panadan API', version='0.8.0', docs_url=None,
              redoc_url=None, openapi_url=None, lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts(PUBLIC_ORIGIN))
app.mount('/static', StaticFiles(directory='static'), name='static')
# Activity logs contain ONLY a route category, actor, status and duration.
# Query strings, token headers, request bodies and response bodies are omitted.
@app.middleware('http')
async def audit_http_activity(request: Request, call_next):
    path = request.url.path
    if not (path.startswith('/dashboard') or path.startswith('/api/v1/')):
        return await call_next(request)
    start = time.monotonic()
    user_id = None
    if path.startswith('/dashboard'):
        session = store.session(request.cookies.get(COOKIE_NAME))
        user_id = session['user_id'] if session else None
        surface = 'dashboard'
    else:
        auth = request.headers.get('authorization', '')
        token = auth[7:] if auth.startswith('Bearer ') else ''
        user_id = store.actor_for_token(token, 'api:read')
        surface = 'api'
    # Prevent raw IDs, external names and query parameters entering the log.
    # Only known route families and sanitized method are recorded.
    approved = {
        '/dashboard', '/dashboard/data', '/dashboard/metrics',
        '/dashboard/filter-options', '/dashboard/api', '/dashboard/users',
        '/dashboard/tokens', '/dashboard/connect', '/dashboard/oauth',
        '/dashboard/activity', '/dashboard/activity/data',
        '/dashboard/mirror-health',
        '/dashboard/operator', '/dashboard/operators', '/dashboard/operators/assign'
    }
    if path in approved:
        action = path
    elif path.startswith('/dashboard/ai/transcript/'):
        action = '/dashboard/ai/transcript/{id}'
    elif path.startswith('/dashboard/overview/'):
        action = '/dashboard/overview/{id}'
    elif path.startswith('/dashboard/data/'):
        action = '/dashboard/data/{id}'
    elif path.startswith('/api/v1/calls/'):
        action = '/api/v1/calls/{id}'
    elif path.startswith('/dashboard/tokens/'):
        action = '/dashboard/tokens/{id}/action'
    elif path.startswith('/dashboard/users/'):
        action = '/dashboard/users/{id}/action'
    elif path.startswith('/dashboard/oauth/'):
        action = '/dashboard/oauth/{id}/action'
    else:
        action = '/dashboard/other' if path.startswith('/dashboard') else '/api/v1/other'
    action = request.method.upper() + ' ' + action
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        elapsed = int((time.monotonic()-start)*1000)
        try:
            store.record_activity(user_id=user_id, surface=surface,
                                  action=action, http_status=status_code,
                                  duration_ms=elapsed)
        except Exception:
            # Auditing failure must not turn an authorized read into a 500.
            # Production monitoring should separately alert on auth-store failures.
            pass



def current_session(request: Request) -> dict:
    session = store.session(request.cookies.get(COOKIE_NAME))
    if not session: raise HTTPException(status_code=401, detail='Login required')
    return session


def logged_in(request: Request):
    try: return current_session(request)
    except HTTPException: return None


def csrf_check(request: Request, csrf: str, session: dict):
    if not hmac.compare_digest(str(csrf), session['csrf']):
        raise HTTPException(403, 'Invalid CSRF token')
    # Also reject an obviously cross-site POST to defend login/session actions.
    if not valid_form_origin(request, PUBLIC_ORIGIN):
        raise HTTPException(403, 'Invalid request origin')


def required(session: dict, capability: str):
    if not has_capability(session, capability):
        raise HTTPException(403, 'Insufficient permissions')
    return session


def admin_only(session: dict):
    return required(session, 'users:manage')


def user_field_access(session: dict) -> frozenset[str]:
    access = store.user_access(session['user_id']) if hasattr(store, 'user_access') else None
    if access is None:
        raise HTTPException(403, 'Field authorization unavailable')
    return access['fields']


def api_field_access(request: Request, scope: str = 'api:read') -> frozenset[str]:
    auth = request.headers.get('authorization', '')
    raw = auth[7:] if auth.startswith('Bearer ') else ''
    actor = store.actor_for_token(raw, scope)
    if actor is None or not hasattr(store, 'user_access'):
        raise HTTPException(401, 'Unauthorized reporting identity')
    policy = store.user_access(actor)
    if policy is None:
        raise HTTPException(403, 'Reporting permission revoked')
    return policy['fields']


def require_field_filters(fields: frozenset[str], *, after=None, before=None,
                          created_after=None, created_before=None, state=None,
                          call_type=None, direction=None, operator=None,
                          operators=None, destination=None, team=None):
    constraints = (
        ((after is not None or before is not None), 'CALLDATE'),
        ((created_after is not None or created_before is not None), 'create_date'),
        (bool(state), 'aicallinfostate'),
        (bool(call_type), 'tellstate'),
        (bool(direction), 'tellside'),
        (bool(operator) or bool(operators) or bool(destination) or bool(team),
         'vw_danix_base_info_users_name'),
    )
    if any(on and field not in fields for on,field in constraints):
        raise HTTPException(403, 'Filter requires an unauthorized field')


def api_auth(request: Request, sensitive: bool = False, capability: str = "calls:read"):
    authorization = request.headers.get('authorization', '')
    token = authorization[7:] if authorization.startswith('Bearer ') else ''
    expected = 'api:sensitive' if sensitive else 'api:read'
    if not store.verify_token(token, expected, capability):
        raise HTTPException(status_code=401, detail='Invalid or insufficient API token',
                            headers={'WWW-Authenticate':'Bearer'})


bearer_scheme = HTTPBearer(auto_error=False)

def require_api(request: Request, _credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)):
    api_auth(request)

def require_metrics_api(request: Request, _credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)):
    api_auth(request, capability='metrics:read')


def require_sensitive_api(request: Request, _credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)):
    api_auth(request, True, capability="calls:sensitive")


def audit_auth_event(user_id: int | None, action: str, status_code: int):
    """Log only the login outcome and account, never password, IP or tokens."""
    try:
        store.record_activity(user_id=user_id, surface='auth', action=action,
                              http_status=status_code, duration_ms=0)
    except Exception:
        pass


REPORT_LOG = logging.getLogger("panadan.reporting")


def json_failure(error: Exception):
    # Do not expose database connection details, SQL, exception messages,
    # user inputs, customer data, or the traceback in logs or HTTP errors.
    if isinstance(error, ValueError):
        raise HTTPException(400, str(error))
    code = getattr(error, 'sqlstate', None)
    sqlstate = code if isinstance(code, str) and re.fullmatch(r'[0-9A-Z]{5}', code) else 'unknown'
    REPORT_LOG.warning('Reporting backend failed type=%s SQLSTATE=%s',
                       type(error).__name__, sqlstate)
    raise HTTPException(503, 'Reporting database unavailable or query timed out')


@app.get('/.well-known/oauth-protected-resource', include_in_schema=False)
@app.get('/.well-known/oauth-protected-resource/mcp', include_in_schema=False)
def oauth_protected_resource_metadata():
    if oauth_config.mode != 'oauth':
        raise HTTPException(404, 'OAuth MCP is not enabled')
    return JSONResponse(oauth_config.metadata(), headers={'Cache-Control': 'no-store'})


@app.get('/healthz')
def healthz(): return {'status':'ok'}


@app.get('/', include_in_schema=False)
def root(request: Request):
    return RedirectResponse('/dashboard' if logged_in(request) else '/login', status_code=303)


@app.get('/login', response_class=HTMLResponse, include_in_schema=False)
def login(request: Request):
    if logged_in(request): return RedirectResponse('/dashboard', status_code=303)
    nonce = secrets.token_urlsafe(24)
    response = templates.TemplateResponse(request, 'login.html', {'nonce':nonce, 'error':False})
    response.set_cookie('panadan_login_nonce', nonce, httponly=True, secure=COOKIE_SECURE,
                        samesite='lax', max_age=600)
    return response


@app.post('/login', include_in_schema=False)
def login_submit(request: Request, username: str = Form(...), password: str = Form(...), nonce: str = Form(...)):
    cookie_nonce = request.cookies.get('panadan_login_nonce', '')
    if not cookie_nonce or not hmac.compare_digest(nonce, cookie_nonce) or (
        not valid_form_origin(request, PUBLIC_ORIGIN)):
        raise HTTPException(403, 'Login form expired; reload login page')
    ip = request.client.host if request.client else 'unknown'
    if store.login_is_throttled(username) or (not PUBLIC_ORIGIN and is_rate_limited(ip)):
        audit_auth_event(None, 'POST /login:throttled', 429)
        raise HTTPException(429, 'Too many attempts; retry later')
    uid = store.verify_login(username, password)
    if not uid:
        store.record_login_failure(username)
        if not PUBLIC_ORIGIN:
            record_failure(ip)
        audit_auth_event(None,'POST /login:failed',401)
        response = RedirectResponse('/login?error=1', status_code=303)
        response.delete_cookie('panadan_login_nonce')
        return response
    store.clear_login_failures(username)
    raw, _ = store.create_session(uid)
    audit_auth_event(uid,'POST /login:success',200)
    response = RedirectResponse('/dashboard', status_code=303)
    response.set_cookie(COOKIE_NAME, raw, max_age=SESSION_SECONDS, httponly=True,
                        secure=COOKIE_SECURE, samesite='lax')
    response.delete_cookie('panadan_login_nonce')
    return response


@app.post('/logout', include_in_schema=False)
def logout(request: Request, csrf: str = Form(...), session: dict = Depends(current_session)):
    csrf_check(request, csrf, session)
    store.logout(request.cookies.get(COOKIE_NAME))
    audit_auth_event(session['user_id'],'POST /logout',200)
    r = RedirectResponse('/login', status_code=303)
    r.delete_cookie(COOKIE_NAME)
    return r


def directory_operator_names(destination: str | None = None,
                             team: str | None = None) -> list[str] | None:
    """Destination/team are filters, NOT access-control rules."""
    if not destination and not team: return None
    if any(len(x)>80 for x in (destination,team) if x):
        raise ValueError('Invalid directory filter')
    entries=store.operator_assignments()
    return [name for name in database.operators()
            if (not destination or entries.get(name,{}).get('destination','نامشخص') == destination)
            and (not team or entries.get(name,{}).get('team','نامشخص') == team)]


def dashboard_filter_groups(destination: str | None, team: str | None,
                            mode: str):
    """Directory tags are query facets, NOT permission or access scopes."""
    if mode == 'any':
        groups = []
        if destination:
            groups.append(directory_operator_names(destination=destination))
        if team:
            groups.append(directory_operator_names(team=team))
        return None, groups or None
    return directory_operator_names(destination, team), None


def dashboard_multi_facets(operators: list[str] | None, states: list[str] | None,
                           call_types: list[str] | None, directions: list[str] | None,
                           destinations: list[str] | None, teams: list[str] | None):
    """Bounded UI report selections only. Never interpreted as permissions."""
    selections = {
        'operators': operators or [], 'states': states or [],
        'call_types': call_types or [], 'directions': directions or [],
    }
    for key, values in selections.items():
        max_length = 180 if key == 'operators' else 60
        if len(values) > 20 or any(not value or len(value) > max_length for value in values):
            raise ValueError('Invalid report filter values')
    directory = []
    for values, field in ((destinations or [], 'destination'), (teams or [], 'team')):
        if len(values) > 20 or any(not v or len(v) > 80 for v in values):
            raise ValueError('Invalid report directory selections')
        for value in dict.fromkeys(values):
            directory.append(directory_operator_names(**{field: value}))
    return selections, (directory or None)


def operator_display(name: str) -> str:
    return 'نامشخص' if name == database.UNSPECIFIED else name


@app.get('/dashboard', response_class=HTMLResponse, include_in_schema=False)
def dashboard(request: Request):
    session = logged_in(request)
    if not session: return RedirectResponse('/login', status_code=303)
    return templates.TemplateResponse(request, 'dashboard.html', {
        'csrf':session['csrf'],'session':session,
        'abilities':{cap:has_capability(session,cap) for cap in CAPABILITIES},
        'selected_operator':None, 'operator_title':None, 'operator_meta':{},
    })


@app.get('/dashboard/mirror-health', include_in_schema=False)
def dashboard_mirror_health(session: dict = Depends(current_session)):
    # Aggregate-only health; the reporting database is not touched here.
    admin_only(session)
    return JSONResponse(mirror_health.load_admin_mirror_health(),
                        headers={'Cache-Control': 'no-store'})


@app.get('/dashboard/operator', response_class=HTMLResponse, include_in_schema=False)
def operator_profile(request: Request, name: str = Query(...,min_length=1,max_length=180),
                     session: dict = Depends(current_session)):
    required(session,'calls:read')
    if 'vw_danix_base_info_users_name' not in user_field_access(session):
        raise HTTPException(403, 'Operator field unavailable')
    return templates.TemplateResponse(request,'dashboard.html',{
        'csrf':session['csrf'],'session':session,
        'abilities':{cap:has_capability(session,cap) for cap in CAPABILITIES},
        'selected_operator':name,'operator_title':operator_display(name),
        'operator_meta':store.operator_assignments().get(name,{'destination':'نامشخص','team':'نامشخص'}),
    },headers={'Cache-Control':'no-store'})


@app.get('/dashboard/operators', response_class=HTMLResponse, include_in_schema=False)
def operators_page(request: Request, session: dict = Depends(current_session)):
    required(session,'calls:read')
    if 'vw_danix_base_info_users_name' not in user_field_access(session):
        raise HTTPException(403, 'Operator field unavailable')
    try: names=read_with_retry(database.operators)
    except Exception as e: json_failure(e)
    assignments=store.operator_assignments()
    entries=[{
        'name':name, 'label':operator_display(name),
        'destination':assignments.get(name,{}).get('destination','نامشخص'),
        'team':assignments.get(name,{}).get('team','نامشخص'),
    } for name in names]
    return templates.TemplateResponse(request,'operators.html',{
        'session':session,'csrf':session['csrf'],
        'entries':entries,'can_manage':has_capability(session,'users:manage'),
    },headers={'Cache-Control':'no-store'})


@app.post('/dashboard/operators/assign', include_in_schema=False)
def assign_operator(request: Request, name: str = Form(...),
                    destination: str = Form(''), team: str = Form(''),
                    csrf: str = Form(...),
                    session: dict = Depends(current_session)):
    admin_only(session)
    csrf_check(request,csrf,session)
    try:
        if name not in database.operators():
            raise ValueError('Operator not in reporting source')
        store.set_operator_assignment(name,destination,team)
    except ValueError as e:
        raise HTTPException(400,str(e)) from e
    except Exception as e:
        json_failure(e)
    return RedirectResponse('/dashboard/operators',status_code=303)


@app.get('/dashboard/tokens', response_class=HTMLResponse, include_in_schema=False)
def token_page(request: Request):
    session = logged_in(request)
    if not session: return RedirectResponse('/login', status_code=303)
    admin_only(session)
    return templates.TemplateResponse(request, 'tokens.html', {
        'session':session, 'csrf':session['csrf'], 'tokens':store.list_tokens(), 'users':store.list_users(), 'new_token':None, 'oauth_mode': oauth_config.mode})


@app.post('/dashboard/tokens', response_class=HTMLResponse, include_in_schema=False)
def create_token(request: Request, name: str = Form(...), scope: str = Form(...),
                 days: int = Form(30), owner_id: int = Form(0), csrf: str = Form(...),
                 session: dict = Depends(current_session)):
    csrf_check(request, csrf, session)
    admin_only(session)
    if not name.strip() or len(name) > 80: raise HTTPException(400, 'Invalid token name')
    if oauth_config.mode == 'oauth' and scope == 'mcp:read':
        raise HTTPException(400, 'Manual MCP tokens are disabled in OAuth mode')
    try: _, token = store.create_token(name.strip(), scope, days, owner_id or session['user_id'])
    except ValueError: raise HTTPException(400, 'Invalid token options')
    response = templates.TemplateResponse(request, 'tokens.html', {
        'session':session, 'csrf':session['csrf'], 'tokens':store.list_tokens(), 'users':store.list_users(), 'new_token':token, 'oauth_mode': oauth_config.mode},
        headers={'Cache-Control':'no-store'})
    return response


@app.post('/dashboard/tokens/{tid}/revoke', include_in_schema=False)
def revoke_token(request: Request, tid: int, csrf: str = Form(...),
                 session: dict = Depends(current_session)):
    csrf_check(request, csrf, session)
    admin_only(session)
    store.revoke(tid)
    return RedirectResponse('/dashboard/tokens', status_code=303)


@app.get('/dashboard/data', include_in_schema=False)
def dashboard_data(request: Request, limit: int = Query(20, ge=1, le=100),
                   offset: int = Query(0, ge=0, le=10000), after: date | None = None,
                   before: date | None = None,
                   operator: str | None = Query(None, max_length=180),
                   operators: list[str] | None = Query(None),
                   state: list[str] | None = Query(None),
                   call_type: list[str] | None = Query(None),
                   direction: list[str] | None = Query(None),
                   destination: list[str] | None = Query(None),
                   team: list[str] | None = Query(None),
                   created_after: datetime | None = None, created_before: datetime | None = None,
                   session: dict = Depends(current_session)):
    required(session, 'calls:read')
    fields = user_field_access(session)
    require_field_filters(fields, after=after, before=before, created_after=created_after,
                          created_before=created_before, operator=operator,
                          operators=operators, state=state, call_type=call_type,
                          direction=direction, destination=destination, team=team)
    try:
        selected, groups = dashboard_multi_facets(
            operators, state, call_type, direction, destination, team)
        rows = read_with_retry(lambda: database.list_calls(
            limit, offset, after, before, None, created_after, created_before,
            operator=operator, filter_mode='any', selected_facets=selected,
            any_operator_groups=groups,
            sort_by_date='CALLDATE' in fields,
            sort_by_id='id' in fields))
        return {'items': [project_call(item, fields) for item in rows]}
    except Exception as e: json_failure(e)

@app.get('/dashboard/filter-options', include_in_schema=False)
def dashboard_filter_options(session: dict = Depends(current_session)):
    required(session, 'calls:read')
    fields = user_field_access(session)
    try:
        names=database.operators()
        assignments=store.operator_assignments()
        return {
            'states': read_with_retry(database.statuses) if 'aicallinfostate' in fields else [],
            'call_types': read_with_retry(database.call_types) if 'tellstate' in fields else [],
            'directions': read_with_retry(database.directions) if 'tellside' in fields else [],
            'operators':[{'value':name,'label':operator_display(name),
                          'destination':assignments.get(name,{}).get('destination','نامشخص'),
                          'team':assignments.get(name,{}).get('team','نامشخص')}
                         for name in names] if 'vw_danix_base_info_users_name' in fields else [],
            'destinations':sorted({'نامشخص',*(row['destination'] for row in assignments.values())}) if 'vw_danix_base_info_users_name' in fields else [],
            'teams':sorted({'نامشخص',*(row['team'] for row in assignments.values())}) if 'vw_danix_base_info_users_name' in fields else [],
        }
    except Exception as e: json_failure(e)


@app.get('/dashboard/ai/transcript/{call_id}', include_in_schema=False)
def browser_ai_transcript(call_id: int, offset: int = Query(0,ge=0,le=2147483646),
                          limit: int = Query(6000,ge=1,le=6000),
                          session: dict = Depends(current_session)):
    """Authorized WebMCP retrieval: redacted, bounded, auditable and read-only."""
    required(session,'calls:read')
    required(session,'calls:transcript:read')
    if not {'id','transcription'} <= user_field_access(session):
        raise HTTPException(403, 'Transcript requires call ID and transcript grants')
    if call_id <= 0:
        raise HTTPException(400, 'Invalid call ID')
    allowed = store.audit_transcript_request(
        user_id=session['user_id'], surface='webmcp',
        call_id=call_id, char_limit=limit,
    )
    if not allowed:
        raise HTTPException(429, 'Transcript access unavailable or hourly limit reached')
    try: raw = database.transcript_excerpt(call_id, limit, offset)
    except Exception as e: json_failure(e)
    if not raw:
        raise HTTPException(404, 'Call not found')
    return JSONResponse(transcript_for_ai(raw, limit=limit, offset=offset), headers={'Cache-Control':'no-store'})


@app.get('/dashboard/overview/{call_id}', include_in_schema=False)
def dashboard_public_call_overview(call_id: int, session: dict = Depends(current_session)):
    """Metadata-only lookup for browser agents; never fetch sensitive columns."""
    required(session, 'calls:read')
    fields = user_field_access(session)
    if 'id' not in fields:
        raise HTTPException(403, 'Call ID field required for individual lookup')
    try: result = read_with_retry(lambda: database.get_call(call_id, sensitive=False))
    except Exception as e: json_failure(e)
    if not result: raise HTTPException(404, 'Call not found')
    return JSONResponse(project_call(result, fields), headers={'Cache-Control': 'no-store'})


@app.get('/dashboard/data/{call_id}', include_in_schema=False)
def dashboard_detail(call_id: int, session: dict = Depends(current_session)):
    required(session,'calls:read')
    fields = user_field_access(session)
    if 'id' not in fields:
        raise HTTPException(403, 'Call ID field required for individual lookup')
    try: result = read_with_retry(lambda: database.get_call(call_id, sensitive=has_capability(session,'calls:sensitive')))
    except Exception as e: json_failure(e)
    if not result: raise HTTPException(404, 'Call not found')
    return JSONResponse(project_call(result, fields), headers={'Cache-Control':'no-store'})


@app.get('/dashboard/metrics', include_in_schema=False)
def dashboard_metrics(after: date | None = None, before: date | None = None,
                      created_after: datetime | None = None, created_before: datetime | None = None,
                      operator: str | None = Query(None,max_length=180),
                      operators: list[str] | None = Query(None),
                      destination: list[str] | None = Query(None),
                      team: list[str] | None = Query(None),
                      state: list[str] | None = Query(None),
                      call_type: list[str] | None = Query(None),
                      direction: list[str] | None = Query(None),
                      session: dict = Depends(current_session)):
    required(session,'metrics:read')
    fields = user_field_access(session)
    require_field_filters(fields, after=after, before=before, created_after=created_after,
                          created_before=created_before, operator=operator,
                          operators=operators, state=state, call_type=call_type,
                          direction=direction, destination=destination, team=team)
    try:
        selected, groups = dashboard_multi_facets(
            operators, state, call_type, direction, destination, team)
        data = read_with_retry(lambda: database.stats(
            after, before, created_after, created_before, operator,
            state=None, filter_mode='any', selected_facets=selected,
            any_operator_groups=groups))
        return project_metrics(data, fields)
    except Exception as e: json_failure(e)

@app.get('/api/v1/calls', dependencies=[Depends(require_api)], tags=['Calls'])
def api_calls(request: Request, limit: int = Query(20,ge=1,le=100), offset: int = Query(0,ge=0,le=10000),
              after: date | None = None, before: date | None = None, state: str | None = None,
              call_type: str | None = None,
              operator: str | None = Query(None,max_length=180),
              destination: str | None = Query(None,max_length=80),
              team: str | None = Query(None,max_length=80)):
    fields = api_field_access(request)
    require_field_filters(fields, after=after, before=before, state=state,
                          call_type=call_type, operator=operator,
                          destination=destination, team=team)
    try:
        rows = database.list_calls(limit,offset,after,before,state,call_type=call_type,
                                   operator=operator,
                                   operator_names=directory_operator_names(destination,team),
                                   sort_by_date='CALLDATE' in fields,
                                   sort_by_id='id' in fields)
        return {'items':[project_call(row, fields) for row in rows]}
    except Exception as e: json_failure(e)


@app.get('/api/v1/calls/{call_id}', dependencies=[Depends(require_api)], tags=['Calls'])
def api_call(call_id: int, request: Request, include_sensitive: bool = False):
    if include_sensitive: api_auth(request, sensitive=True)
    fields = api_field_access(request, 'api:sensitive' if include_sensitive else 'api:read')
    if 'id' not in fields:
        raise HTTPException(403, 'Call ID field required for individual lookup')
    try: result = database.get_call(call_id, sensitive=include_sensitive)
    except Exception as e: json_failure(e)
    if not result: raise HTTPException(404, 'Call not found')
    return JSONResponse(project_call(result, fields), headers={'Cache-Control':'no-store'})


@app.get('/api/v1/stats', dependencies=[Depends(require_metrics_api)], tags=['Analytics'])
def api_stats(request: Request, after: date | None = None, before: date | None = None,
              operator: str | None = Query(None,max_length=180),
              destination: str | None = Query(None,max_length=80),
              team: str | None = Query(None,max_length=80)):
    fields = api_field_access(request)
    require_field_filters(fields, after=after, before=before, operator=operator,
                          destination=destination, team=team)
    try:
        result = database.stats(after,before,operator=operator,
                                operator_names=directory_operator_names(destination,team))
        return project_metrics(result, fields)
    except Exception as e: json_failure(e)


@app.get('/api/v1/states', dependencies=[Depends(require_metrics_api)], tags=['Analytics'])
def api_states(request: Request):
    if 'aicallinfostate' not in api_field_access(request):
        raise HTTPException(403, 'Status field not available')
    try: return {'states':database.statuses()}
    except Exception as e: json_failure(e)


@app.get('/docs', include_in_schema=False)
def private_docs(request: Request, session: dict = Depends(current_session)):
    admin_only(session)
    return get_swagger_ui_html(openapi_url='/openapi.json',title='Panadan API Docs')


@app.get('/openapi.json', include_in_schema=False)
def private_openapi(request: Request, session: dict = Depends(current_session)):
    admin_only(session)
    from fastapi.openapi.utils import get_openapi
    return get_openapi(title=app.title, version=app.version, routes=app.routes)




@app.get('/dashboard/users', response_class=HTMLResponse, include_in_schema=False)
def users_page(request: Request, session: dict = Depends(current_session)):
    admin_only(session)
    users = store.list_users()
    user_caps = {
        user['id']: permissions(user['role'], user['grants']) for user in users
    }
    return templates.TemplateResponse(request, 'users.html', {
        'session': session, 'csrf': session['csrf'],
        'users': users,
        'roles': ROLE_GRANTS,
        'capabilities': CAPABILITIES,
        'user_caps': user_caps,
        'user_groups': {
            user['id']: matching_group(user['role'], user_caps[user['id']])
            for user in users
        },
        'permission_categories': PERMISSION_CATEGORIES,
        'permission_groups': group_options(),
        'field_catalog': field_catalog(),
        'default_fields': capability_fields(set(ROLE_GRANTS['analyst'])),
        'user_fields': {user['id']: effective_fields(
            permissions(user['role'],user['grants']),user['field_grants'])
            for user in users},
        'recommended_groups': ROLE_RECOMMENDED_GROUP,
        'admin_only_caps': ADMIN_ONLY,
        'cap_labels': {
            item['id']: item['label']
            for category in PERMISSION_CATEGORIES
            for item in category['items']
        },
        'role_labels': {
            'admin': 'مدیر کل',
            'analyst': 'تحلیل‌گر',
            'reader': 'خواننده',
            'metrics': 'فقط آمار',
        },
        'error': request.query_params.get('error'),
    })


@app.post('/dashboard/users', include_in_schema=False)
def add_user(request: Request, username: str = Form(...), password: str = Form(...),
             role: str = Form(...), csrf: str = Form(...),
             grants: list[str] = Form([]), fields: list[str] = Form([]),
             fields_present: bool = Form(False), session: dict = Depends(current_session)):
    csrf_check(request, csrf, session)
    admin_only(session)
    try: store.create_user(username.strip(),password,role,grants if role != 'admin' else None,
                           fields=fields if fields_present else None)
    except (ValueError, __import__('sqlite3').IntegrityError) as exc:
        raise HTTPException(400, 'Invalid user options or username already exists') from exc
    return RedirectResponse('/dashboard/users',status_code=303)


@app.post('/dashboard/users/{uid}/update', include_in_schema=False)
def update_user(request: Request, uid: int, role: str = Form(...), csrf: str = Form(...),
                is_active: bool = Form(False), grants: list[str] = Form([]),
                fields: list[str] = Form([]), fields_present: bool = Form(False),
                session: dict = Depends(current_session)):
    csrf_check(request, csrf, session)
    admin_only(session)
    try: store.update_user(uid,role,grants if role != 'admin' else None,is_active,session['user_id'],
                           fields=fields if fields_present else None)
    except ValueError as exc: raise HTTPException(400,str(exc)) from exc
    return RedirectResponse('/dashboard/users',status_code=303)


@app.get('/dashboard/mcp-apps', response_class=HTMLResponse, include_in_schema=False)
def my_connected_ai_apps(request: Request, session: dict = Depends(current_session)):
    """Self-service client-bound consent; not an OAuth authorization server."""
    if not hasattr(store, 'user_access') or not hasattr(store, 'list_mcp_clients'):
        raise HTTPException(503, 'Consent store unavailable')
    access = store.user_access(session['user_id'])
    if access is None:
        raise HTTPException(403, 'Account disabled')
    client_rows = []
    for record in store.list_mcp_clients(session['user_id']):
        try:
            client_rows.append({
                'client_id': record['client_id'],
                'capabilities': set(json.loads(record['capabilities'])),
                'fields': set(json.loads(record['fields'])),
                'approved_at': record['approved_at']
            })
        except (TypeError, ValueError, KeyError):
            continue
    return templates.TemplateResponse(request, 'mcp_apps.html', {
        'session': session, 'csrf': session['csrf'],
        'capabilities': access['capabilities'] & {
            'calls:read','metrics:read','calls:transcript:read','mcp:use'},
        'fields': access['fields'] & capability_fields(access['capabilities'] & {
            'mcp:use','calls:read','metrics:read','calls:transcript:read'}),
        'field_catalog': field_catalog(),
        'client_grants': client_rows,
        'can_manage': 'users:manage' in access['capabilities'],
        'oauth_mode': oauth_config.mode,
    }, headers={'Cache-Control':'no-store'})


@app.post('/dashboard/mcp-apps/approve', include_in_schema=False)
def approve_my_ai_app(request: Request, csrf: str = Form(...),
                      client_id: str = Form(...),
                      capabilities: list[str] = Form([]),
                      fields: list[str] = Form([]),
                      session: dict = Depends(current_session)):
    csrf_check(request, csrf, session)
    if not hasattr(store, 'approve_mcp_client'):
        raise HTTPException(503, 'Consent store unavailable')
    try:
        store.approve_mcp_client(session['user_id'], client_id,
                                 ['mcp:use', *capabilities], fields)
        store.record_activity(user_id=session['user_id'], surface='auth',
                              action='MCP client consent updated',
                              http_status=200, duration_ms=0)
    except ValueError as exc:
        raise HTTPException(400, 'Invalid client or delegated permissions') from exc
    return RedirectResponse('/dashboard/mcp-apps', status_code=303)


@app.post('/dashboard/mcp-apps/revoke', include_in_schema=False)
def revoke_my_ai_app(request: Request, csrf: str = Form(...),
                     client_id: str = Form(...),
                     session: dict = Depends(current_session)):
    csrf_check(request, csrf, session)
    if not hasattr(store, 'revoke_mcp_client'):
        raise HTTPException(503, 'Consent store unavailable')
    store.revoke_mcp_client(session['user_id'], client_id)
    store.record_activity(user_id=session['user_id'], surface='auth',
                          action='MCP client consent revoked',
                          http_status=200, duration_ms=0)
    return RedirectResponse('/dashboard/mcp-apps', status_code=303)


@app.get('/api/v1/me/access', tags=['Authorization'])
def read_my_access(request: Request):
    """Self-only metadata, never arbitrary user-id lookup or customer payload."""
    if not hasattr(store, 'user_access'):
        raise HTTPException(503, 'Field authorization unavailable')
    auth = request.headers.get('authorization', '')
    session = logged_in(request) if not auth else None
    if session:
        access = store.user_access(session['user_id'])
        caps = access['capabilities'] if access else frozenset()
        fields = access['fields'] if access else frozenset()
    else:
        raw = auth[7:] if auth.startswith('Bearer ') else ''
        if oauth_config.mode == 'oauth':
            details = oauth_verifier.verify_details(raw) if oauth_verifier else None
            if not details or not details.get('client_id'):
                raise HTTPException(401, 'Verified OAuth client required')
            actor = store.actor_for_oauth(oauth_config.issuer, details['subject'])
            if actor is None:
                raise HTTPException(401, 'OAuth account is not linked')
            delegated = store.mcp_access(actor, oauth_client=details['client_id'])
            if delegated is None:
                raise HTTPException(403, 'MCP authorization unavailable')
            caps, fields = delegated['capabilities'], delegated['fields']
        else:
            actor = (store.actor_for_token(raw, 'api:read') or
                     store.actor_for_token(raw, 'api:sensitive') or
                     store.actor_for_token(raw, 'mcp:read'))
            if actor is None:
                raise HTTPException(401, 'Authentication required')
            user = store.user_access(actor)
            if user is None:
                raise HTTPException(403, 'Account disabled')
            if store.actor_for_token(raw, 'mcp:read'):
                delegated = store.mcp_access(actor, legacy_token=raw)
                if delegated is None:
                    raise HTTPException(403, 'MCP authorization unavailable')
                caps = delegated['capabilities']
                fields = delegated['fields']
            else:
                caps, fields = user['capabilities'], user['fields']
                if not store.actor_for_token(raw, 'api:sensitive'):
                    fields = fields - set(database.SENSITIVE_COLUMNS)
    if not caps:
        raise HTTPException(403, 'Account has no active access')
    return JSONResponse({
        'schema_version': 1, 'actor': 'self',
        'capabilities': sorted(caps & {'calls:read','metrics:read',
                                      'calls:transcript:read','mcp:use'}),
        'fields': [
            {'id': item['id'], 'label': item['label'],
             'category': item['category']}
            for item in field_catalog() if item['id'] in fields
        ],
        'hint': 'To change user grants ask an administrator; AI clients need separate consent.',
    }, headers={'Cache-Control':'no-store'})


@app.get('/dashboard/activity', response_class=HTMLResponse, include_in_schema=False)
def activity_page(request: Request, session: dict = Depends(current_session)):
    admin_only(session)
    return templates.TemplateResponse(request, 'activity.html', {
        'session':session, 'csrf':session['csrf'],
        'users':store.list_users(),
    },headers={'Cache-Control':'no-store'})


@app.get('/dashboard/activity/data', include_in_schema=False)
def activity_data(days: int = Query(14,ge=1,le=90),
                  user_id: int | None = Query(None,ge=1),
                  surface: str | None = None, errors_only: bool = False,
                  session: dict = Depends(current_session)):
    admin_only(session)
    try: result = store.activity_report(days=days,user_id=user_id,surface=surface,errors_only=errors_only)
    except ValueError as e: raise HTTPException(400,str(e)) from e
    return JSONResponse(result,headers={'Cache-Control':'no-store'})


@app.get('/dashboard/api', response_class=HTMLResponse, include_in_schema=False)
def api_guide(request: Request, session: dict = Depends(current_session)):
    admin_only(session)
    return templates.TemplateResponse(request, 'api.html', {
        'session': session, 'csrf': session['csrf'],
        'base_url': external_base_url(request, PUBLIC_ORIGIN),
    }, headers={'Cache-Control': 'no-store'})


@app.get('/dashboard/oauth', response_class=HTMLResponse, include_in_schema=False)
def oauth_admin_page(request: Request, session: dict = Depends(current_session)):
    admin_only(session)
    return templates.TemplateResponse(request, 'oauth.html', {
        'session': session,
        'csrf': session['csrf'],
        'oauth': oauth_config,
        'users': store.list_users(),
        'bindings': store.list_oauth_identities(oauth_config.issuer) if oauth_config.mode == 'oauth' else [],
    }, headers={'Cache-Control': 'no-store'})


@app.post('/dashboard/oauth/link', include_in_schema=False)
def oauth_admin_link(request: Request, user_id: int = Form(...), subject: str = Form(...),
                     csrf: str = Form(...), session: dict = Depends(current_session)):
    csrf_check(request, csrf, session)
    admin_only(session)
    if oauth_config.mode != 'oauth':
        raise HTTPException(400, 'Enable OAuth configuration first')
    try:
        store.bind_oauth_identity(oauth_config.issuer, subject, user_id)
    except (ValueError, __import__('sqlite3').IntegrityError) as exc:
        raise HTTPException(400, 'Invalid or already-linked identity') from exc
    return RedirectResponse('/dashboard/oauth', status_code=303)


@app.post('/dashboard/oauth/{identity_id}/revoke', include_in_schema=False)
def oauth_admin_unlink(request: Request, identity_id: int, csrf: str = Form(...),
                       session: dict = Depends(current_session)):
    csrf_check(request, csrf, session)
    admin_only(session)
    if oauth_config.mode != 'oauth':
        raise HTTPException(400, 'OAuth is not enabled')
    store.revoke_oauth_identity(oauth_config.issuer, identity_id)
    return RedirectResponse('/dashboard/oauth', status_code=303)


@app.get('/dashboard/connect', response_class=HTMLResponse, include_in_schema=False)
def connect_page(request: Request, session: dict = Depends(current_session)):
    admin_only(session)
    return templates.TemplateResponse(request,'connect.html', {
        'session':session,'csrf':session['csrf'],
        'mcp_path':'/mcp/', 'base_url':external_base_url(request, PUBLIC_ORIGIN),
        'oauth': oauth_config,
    },headers={'Cache-Control':'no-store'})


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
            subject = oauth_verifier.verify(raw) if oauth_verifier else None
            valid = bool(subject and store.oauth_identity_has_mcp_access(oauth_config.issuer, subject))
            if valid: actor=store.actor_for_oauth(oauth_config.issuer,subject)
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


# /mcp/ always requires authentication, and tools never allow arbitrary SQL.
def mcp_transport_settings() -> TransportSecuritySettings:
    """Require explicit host/origin allowlists for SDK v2 MCP transport.

    Default hosts/origins are loopback-only. Public proxy hostnames must be
    added explicitly before exposing the MCP route. Do not use wildcards.
    """
    def extras(name: str, *, origin: bool = False) -> list[str]:
        items=[value.strip() for value in os.getenv(name,'').split(',') if value.strip()]
        for value in items:
            if ('*' in value or len(value)>253 or
                    any(ch.isspace() for ch in value)):
                raise ValueError(f'{name} must contain exact values without wildcards')
            if origin:
                from urllib.parse import urlsplit
                parsed=urlsplit(value)
                if (parsed.scheme!='https' or not parsed.hostname or
                        parsed.username or parsed.password or parsed.path not in ('','/') or
                        parsed.query or parsed.fragment):
                    raise ValueError(f'{name} must contain specific HTTPS origins')
            elif any(ch in value for ch in '/@?#') or value.startswith(':'):
                raise ValueError(f'{name} must contain exact public hostnames or host:port values')
        return items
    hosts=['localhost:*','127.0.0.1:*','[::1]:*'] + extras('PANADAN_MCP_ALLOWED_HOSTS')
    origins=['http://localhost:*','http://127.0.0.1:*'] + extras('PANADAN_MCP_ALLOWED_ORIGINS',origin=True)
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
        allowed_origins=origins,
    )


# SDK v2 requires stateless/JSON and transport path on the ASGI factory,
# not on MCPServer's constructor. Keep the source reporting tools read-only.
app.mount('/mcp', MCPBearerGate(mcp.streamable_http_app(
    streamable_http_path='/',
    stateless_http=True,
    json_response=True,
    host='0.0.0.0',
    transport_security=mcp_transport_settings(),
)))
