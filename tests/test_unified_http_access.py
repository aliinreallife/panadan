"""HTTP tests for field-level access across browser, REST and local consent.

Synthetic reporting data only; no network or Odoo database contact.
"""
from contextlib import asynccontextmanager
import importlib

from fastapi.testclient import TestClient
import pytest


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv('PANADAN_AUTH_DB', str(tmp_path / 'auth.sqlite'))
    monkeypatch.setenv('PANADAN_ADMIN_USER', 'admin')
    monkeypatch.setenv('PANADAN_ADMIN_PASSWORD', 'admin-password-very-long')
    monkeypatch.setenv('PANADAN_COOKIE_SECURE', 'false')
    monkeypatch.setenv('PANADAN_MCP_AUTH_MODE', 'legacy')

    import server.main as main
    main = importlib.reload(main)
    secret = 'SENSITIVE-DO-NOT-DISCLOSE'
    row = {
        'id': 81, 'CALLDATE': '2026-11-09', 'aicallinfostate': 'Unchecked',
        'tellstate': 'Inbound', 'customername': secret,
        'customertell': secret, 'summary': secret, 'transcription': secret,
        'voice_length': 20, 'possibility_of_sale_ai': 50,
    }
    monkeypatch.setattr(main.database, 'list_calls', lambda *a, **k: [row.copy()])
    monkeypatch.setattr(main.database, 'get_call', lambda *a, **k: row.copy())
    monkeypatch.setattr(main.database, 'stats', lambda *a, **k: {
        'total': 1, 'sold_out': 0, 'scored_calls': 1,
        'avg_ai_score': 50, 'avg_voice_length': 20
    })
    monkeypatch.setattr(main.database, 'statuses', lambda: ['Unchecked'])
    monkeypatch.setattr(main.database, 'call_types', lambda: ['Inbound'])
    monkeypatch.setattr(main.database, 'directions', lambda: ['Incoming'])
    monkeypatch.setattr(main.database, 'operators', lambda: ['Sample Agent'])
    @asynccontextmanager
    async def auth_lifespan(_):
        main.store.bootstrap('admin', 'admin-password-very-long')
        yield
    main.app.router.lifespan_context = auth_lifespan
    with TestClient(main.app) as client:
        yield client, main, secret


def test_user_column_limits_apply_to_browser_and_api(app_client):
    c, main, secret = app_client
    uid = main.store.create_user('limited1', 'example-password-very-long',
                                  'analyst',
                                  ['calls:read','metrics:read','mcp:use'],
                                  fields=['id','CALLDATE','aicallinfostate'])
    cookie, csrf = main.store.create_session(uid)
    c.cookies.set('panadan_session', cookie)
    list_result = c.get('/dashboard/data')
    assert list_result.status_code == 200, list_result.text
    assert list_result.json()['items'] == [
        {'id': 81, 'CALLDATE': '2026-11-09',
         'aicallinfostate':'Unchecked'}]
    assert secret not in list_result.text
    detail = c.get('/dashboard/data/81')
    assert detail.status_code == 200
    assert detail.json() == list_result.json()['items'][0]
    stats = c.get('/dashboard/metrics')
    assert stats.status_code == 200
    assert stats.json() == {'total': 1, 'sold_out': 0}
    assert c.get('/dashboard/data?call_type=Inbound').status_code == 403
    assert c.get('/dashboard/data?state=Unchecked').status_code == 200

    me = c.get('/api/v1/me/access')
    assert me.status_code == 200
    assert {v['id'] for v in me.json()['fields']} == {
        'id','CALLDATE','aicallinfostate'}
    assert secret not in me.text
    _, bearer = main.store.create_token('Test REST','api:read',7,uid)
    headers = {'authorization':'Bearer '+bearer}
    rest = c.get('/api/v1/calls', headers=headers)
    assert rest.status_code == 200
    assert rest.json()['items'][0] == detail.json()
    assert c.get('/api/v1/stats',headers=headers).json() == {
        'total':1,'sold_out':0}
    assert c.get('/api/v1/states',headers=headers).status_code == 200


def test_oauth_client_consent_is_bound_to_current_user_and_is_revocable(app_client):
    c, main, _ = app_client
    uid = main.store.create_user('owner1','example-password-very-long','analyst',
                                  ['calls:read','metrics:read','mcp:use'],
                                  fields=['id','CALLDATE','aicallinfostate'])
    raw, csrf = main.store.create_session(uid)
    c.cookies.set('panadan_session', raw)
    page = c.get('/dashboard/mcp-apps')
    assert page.status_code == 200
    assert 'CALLDATE' in page.text
    data = {
        'csrf':csrf, 'client_id':'signed-oauth-client',
        'capabilities':['calls:read'], 'fields':['id','CALLDATE']
    }
    saved = c.post('/dashboard/mcp-apps/approve',data=data,follow_redirects=False)
    assert saved.status_code == 303, saved.text
    allowed = main.store.mcp_access(uid,oauth_client='signed-oauth-client')
    assert allowed['fields'] == {'id','CALLDATE'}
    assert allowed['capabilities'] == {'calls:read','mcp:use'}

    rejected = c.post('/dashboard/mcp-apps/approve',data={
        'csrf':csrf, 'client_id':'malicious-client',
        'capabilities':['calls:read'], 'fields':['customertell']
    }, follow_redirects=False)
    assert rejected.status_code == 400
    assert not main.store.client_grants(uid,'malicious-client')

    revoked = c.post('/dashboard/mcp-apps/revoke',data={
        'csrf':csrf,'client_id':'signed-oauth-client'
    },follow_redirects=False)
    assert revoked.status_code == 303
    assert not main.store.client_grants(uid,'signed-oauth-client')


def test_another_user_cannot_approve_or_revoke_the_owners_client(app_client):
    c, main, _ = app_client
    user1 = main.store.create_user('owner2','example-password-very-long','analyst',
                                  ['calls:read','metrics:read','mcp:use'])
    user2 = main.store.create_user('another2','example-password-very-long','analyst',
                                  ['calls:read','metrics:read','mcp:use'])
    main.store.approve_mcp_client(user1,'some-client',
                                 ['mcp:use','calls:read'],['id'])
    raw, csrf = main.store.create_session(user2)
    c.cookies.set('panadan_session', raw)
    c.post('/dashboard/mcp-apps/revoke',data={'csrf':csrf,'client_id':'some-client'})
    assert main.store.client_grants(user1,'some-client')
    assert main.store.client_grants(user2,'some-client') is None


def test_field_form_requires_server_owned_allowlist(app_client):
    c, main, _ = app_client
    admin = main.store.verify_login('admin','admin-password-very-long')
    raw, csrf = main.store.create_session(admin)
    c.cookies.set('panadan_session',raw)
    denied = c.post('/dashboard/users',data={
        'csrf':csrf,'username':'wrongfields','password':'a-long-test-password',
        'role':'reader','grants':['calls:read'],
        'fields_present':'true','fields':['customertell']
    },follow_redirects=False)
    assert denied.status_code == 400
    assert all(u['username'] != 'wrongfields' for u in main.store.list_users())
