"""FastAPI dashboard, scoped REST API and authenticated MCP Streamable HTTP."""
from __future__ import annotations
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
import hmac
import os
import secrets

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette import status

from . import database
from .mcp_tools import mcp
from .oauth_mcp import OAuthConfig, OAuthVerifier
from .security import Store, SESSION_SECONDS, CAPABILITIES, ROLE_GRANTS, permissions, has_capability, is_rate_limited, record_failure

store = Store(os.getenv('PANADAN_AUTH_DB', '/data/auth.sqlite'))
oauth_config = OAuthConfig.from_env()
oauth_verifier = OAuthVerifier(oauth_config) if oauth_config.mode == 'oauth' else None
COOKIE_SECURE = os.getenv('PANADAN_COOKIE_SECURE', 'true').lower() == 'true'
COOKIE_NAME = 'panadan_session'
templates = Jinja2Templates(directory='templates')
templates.env.filters['date_time'] = lambda value: datetime.fromtimestamp(value, timezone.utc).strftime('%Y-%m-%d %H:%M UTC') if value else '—'


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.bootstrap(os.getenv('PANADAN_ADMIN_USER', 'admin'), os.getenv('PANADAN_ADMIN_PASSWORD'))
    async with mcp.session_manager.run():
        yield


app = FastAPI(title='Panadan API', version='0.6.0', docs_url=None,
              redoc_url=None, openapi_url=None, lifespan=lifespan)
app.mount('/static', StaticFiles(directory='static'), name='static')


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
    origin = request.headers.get('origin')
    if origin and origin.rstrip('/') != str(request.base_url).rstrip('/'):
        raise HTTPException(403, 'Invalid request origin')


def required(session: dict, capability: str):
    if not has_capability(session, capability):
        raise HTTPException(403, 'Insufficient permissions')
    return session


def admin_only(session: dict):
    return required(session, 'users:manage')


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


def json_failure(error: Exception):
    # Do not expose the database server details or customer data in HTTP errors.
    if isinstance(error, ValueError): raise HTTPException(400, str(error))
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
    origin = request.headers.get('origin')
    if not cookie_nonce or not hmac.compare_digest(nonce, cookie_nonce) or (
        origin and origin.rstrip('/') != str(request.base_url).rstrip('/')):
        raise HTTPException(403, 'Login form expired; reload login page')
    ip = request.client.host if request.client else 'unknown'
    if is_rate_limited(ip):
        raise HTTPException(429, 'Too many attempts; retry later')
    uid = store.verify_login(username, password)
    if not uid:
        record_failure(ip)
        response = RedirectResponse('/login?error=1', status_code=303)
        response.delete_cookie('panadan_login_nonce')
        return response
    raw, _ = store.create_session(uid)
    response = RedirectResponse('/dashboard', status_code=303)
    response.set_cookie(COOKIE_NAME, raw, max_age=SESSION_SECONDS, httponly=True,
                        secure=COOKIE_SECURE, samesite='lax')
    response.delete_cookie('panadan_login_nonce')
    return response


@app.post('/logout', include_in_schema=False)
def logout(request: Request, csrf: str = Form(...), session: dict = Depends(current_session)):
    csrf_check(request, csrf, session)
    store.logout(request.cookies.get(COOKIE_NAME))
    r = RedirectResponse('/login', status_code=303)
    r.delete_cookie(COOKIE_NAME)
    return r


@app.get('/dashboard', response_class=HTMLResponse, include_in_schema=False)
def dashboard(request: Request):
    session = logged_in(request)
    if not session: return RedirectResponse('/login', status_code=303)
    return templates.TemplateResponse(request, 'dashboard.html', {'csrf':session['csrf'], 'session':session, 'abilities':{cap:has_capability(session,cap) for cap in CAPABILITIES}})


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
                   before: date | None = None, state: str | None = None,
                   call_type: str | None = None, created_after: datetime | None = None, created_before: datetime | None = None,
                   session: dict = Depends(current_session)):
    required(session, 'calls:read')
    try: return {'items':database.list_calls(limit,offset,after,before,state,created_after,created_before,call_type)}
    except Exception as e: json_failure(e)


@app.get('/dashboard/filter-options', include_in_schema=False)
def dashboard_filter_options(session: dict = Depends(current_session)):
    required(session, 'calls:read')
    try:
        return {'states': database.statuses(), 'call_types': database.call_types()}
    except Exception as e: json_failure(e)


@app.get('/dashboard/data/{call_id}', include_in_schema=False)
def dashboard_detail(call_id: int, session: dict = Depends(current_session)):
    required(session,'calls:read')
    try: result = database.get_call(call_id, sensitive=has_capability(session,'calls:sensitive'))
    except Exception as e: json_failure(e)
    if not result: raise HTTPException(404, 'Call not found')
    return JSONResponse(result, headers={'Cache-Control':'no-store'})


@app.get('/dashboard/metrics', include_in_schema=False)
def dashboard_metrics(after: date | None = None, before: date | None = None,
                      created_after: datetime | None = None, created_before: datetime | None = None,
                      session: dict = Depends(current_session)):
    required(session,'metrics:read')
    try: return database.stats(after, before, created_after, created_before)
    except Exception as e: json_failure(e)


@app.get('/api/v1/calls', dependencies=[Depends(require_api)], tags=['Calls'])
def api_calls(limit: int = Query(20,ge=1,le=100), offset: int = Query(0,ge=0,le=10000),
              after: date | None = None, before: date | None = None, state: str | None = None,
              call_type: str | None = None):
    try: return {'items':database.list_calls(limit,offset,after,before,state,call_type=call_type)}
    except Exception as e: json_failure(e)


@app.get('/api/v1/calls/{call_id}', dependencies=[Depends(require_api)], tags=['Calls'])
def api_call(call_id: int, request: Request, include_sensitive: bool = False):
    if include_sensitive: api_auth(request, sensitive=True)
    try: result = database.get_call(call_id, sensitive=include_sensitive)
    except Exception as e: json_failure(e)
    if not result: raise HTTPException(404, 'Call not found')
    return JSONResponse(result, headers={'Cache-Control':'no-store'})


@app.get('/api/v1/stats', dependencies=[Depends(require_metrics_api)], tags=['Analytics'])
def api_stats(after: date | None = None, before: date | None = None):
    try: return database.stats(after, before)
    except Exception as e: json_failure(e)


@app.get('/api/v1/states', dependencies=[Depends(require_metrics_api)], tags=['Analytics'])
def api_states():
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
    return templates.TemplateResponse(request,'users.html', {
        'session':session, 'csrf':session['csrf'], 'users':store.list_users(),
        'roles':ROLE_GRANTS, 'capabilities':CAPABILITIES, 'user_caps':{u['id']:permissions(u['role'],u['grants']) for u in store.list_users()}, 'error':request.query_params.get('error'),
    })


@app.post('/dashboard/users', include_in_schema=False)
def add_user(request: Request, username: str = Form(...), password: str = Form(...),
             role: str = Form(...), csrf: str = Form(...),
             grants: list[str] = Form([]), session: dict = Depends(current_session)):
    csrf_check(request, csrf, session)
    admin_only(session)
    try: store.create_user(username.strip(),password,role,grants if role != 'admin' else None)
    except (ValueError, __import__('sqlite3').IntegrityError) as exc:
        raise HTTPException(400, 'Invalid user options or username already exists') from exc
    return RedirectResponse('/dashboard/users',status_code=303)


@app.post('/dashboard/users/{uid}/update', include_in_schema=False)
def update_user(request: Request, uid: int, role: str = Form(...), csrf: str = Form(...),
                is_active: bool = Form(False), grants: list[str] = Form([]),
                session: dict = Depends(current_session)):
    csrf_check(request, csrf, session)
    admin_only(session)
    try: store.update_user(uid,role,grants if role != 'admin' else None,is_active,session['user_id'])
    except ValueError as exc: raise HTTPException(400,str(exc)) from exc
    return RedirectResponse('/dashboard/users',status_code=303)


@app.get('/dashboard/api', response_class=HTMLResponse, include_in_schema=False)
def api_guide(request: Request, session: dict = Depends(current_session)):
    admin_only(session)
    return templates.TemplateResponse(request, 'api.html', {
        'session': session, 'csrf': session['csrf'],
        'base_url': str(request.base_url).rstrip('/'),
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
        'mcp_path':'/mcp/', 'base_url':str(request.base_url).rstrip('/'),
        'oauth': oauth_config,
    },headers={'Cache-Control':'no-store'})


class MCPBearerGate:
    """Enforce OAuth OR legacy tokens on every MCP HTTP request.

    The modes are mutually exclusive: once OAuth is enabled, legacy manually
    issued MCP tokens cannot bypass the identity-provider flow.
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
        headers = {k.lower(): v for k, v in scope.get('headers', [])}
        auth = headers.get(b'authorization', b'').decode('latin1')
        raw = auth[7:] if auth.startswith('Bearer ') else ''
        if oauth_config.mode == 'oauth':
            subject = oauth_verifier.verify(raw) if oauth_verifier else None
            valid = bool(subject and store.oauth_identity_has_mcp_access(oauth_config.issuer, subject))
        else:
            valid = store.verify_token(raw, 'mcp:read')
        if not valid:
            # Invalid JWTs/unknown identities are denied without DB access.
            # The OAuth challenge identifies the protected resource metadata
            # for standards-compatible clients such as ChatGPT and Codex.
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
            return
        await self.inner(scope, receive, send)


# /mcp/ always requires authentication, and tools never allow arbitrary SQL.
app.mount('/mcp', MCPBearerGate(mcp.streamable_http_app()))
