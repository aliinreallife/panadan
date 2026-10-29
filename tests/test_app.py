import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def client(tmp_path, monkeypatch):
    # Import after setting the auth DB path. Never connect to real PostgreSQL.
    monkeypatch.setenv('PANADAN_AUTH_DB',str(tmp_path/'auth.sqlite'))
    monkeypatch.setenv('PANADAN_ADMIN_USER','admin')
    monkeypatch.setenv('PANADAN_ADMIN_PASSWORD','a-long-safe-testing-password')
    monkeypatch.setenv('PANADAN_COOKIE_SECURE','false')
    import importlib, server.main as main
    # TestClient mocks data access. No business data or DB credentials required.
    main = importlib.reload(main)
    monkeypatch.setattr(main.database, 'list_calls',lambda *a,**k:[{'id':5,'CALLDATE':'2026-10-01','aicallinfostate':'Unchecked'}])
    monkeypatch.setattr(main.database, 'get_call',lambda *a,**k:{'id':5,'summary':'synthetic'} if k.get('sensitive') else {'id':5})
    monkeypatch.setattr(main.database, 'stats',lambda *a,**k:{'total':1,'sold_out':0,'avg_ai_score':10,'avg_voice_length':20})
    monkeypatch.setattr(main.database, 'statuses',lambda *a,**k:['Unchecked','System Invalid'])
    monkeypatch.setattr(main.database, 'call_types',lambda *a,**k:['FollowUp','FirstToch'])
    # Exercise dashboard/API permissions without restarting the singleton MCP
    # session manager, which the MCP SDK permits to run only once per process.
    from contextlib import asynccontextmanager
    @asynccontextmanager
    async def auth_test_lifespan(_app):
        main.store.bootstrap('admin', 'a-long-safe-testing-password')
        yield
    main.app.router.lifespan_context = auth_test_lifespan
    with TestClient(main.app) as c: yield c, main


def test_reject_unauthorized(client):
    c,_=client
    assert c.get('/api/v1/calls').status_code==401
    assert c.get('/dashboard/data').status_code==401
    assert c.post('/mcp/',json={}).status_code==401


def test_login_dashboard_and_revoke(client):
    c,main=client
    html=c.get('/login').text
    import re
    nonce=re.search(r'name="nonce" value="([^"]+)"',html).group(1)
    r=c.post('/login',data={'username':'admin','password':'a-long-safe-testing-password','nonce':nonce},follow_redirects=False)
    assert r.status_code==303
    assert c.get('/dashboard').status_code==200
    assert c.get('/dashboard/data').json()['items'][0]['id']==5
    csrf=main.store.session(c.cookies.get('panadan_session'))['csrf']
    r=c.post('/dashboard/tokens',data={'name':'test','scope':'api:read','days':7,'csrf':csrf})
    assert r.status_code==200
    assert 'panadan_' in r.text
    assert len(main.store.list_tokens())==1
    tid=main.store.list_tokens()[0]['id']
    assert c.post(f'/dashboard/tokens/{tid}/revoke',data={'csrf':'invalid'}).status_code==403
    assert c.post(f'/dashboard/tokens/{tid}/revoke',data={'csrf':csrf},follow_redirects=False).status_code==303
    assert not main.store.list_tokens()


def test_dashboard_only_cannot_bypass_sensitive_detail(client):
    c, main = client
    uid=main.store.create_user('callreader','another-long-password','reader',['calls:read'])
    raw,_=main.store.create_session(uid)
    c.cookies.set('panadan_session',raw)
    r=c.get('/dashboard/data/5')
    assert r.status_code==200
    assert 'summary' not in r.json()
    assert c.get('/dashboard/users').status_code==403

def test_stats_only_api_token(client):
    c, main = client
    uid=main.store.create_user('metricsonly','another-long-password','metrics',['metrics:read'])
    _, token=main.store.create_token('stats only','api:read',30,uid)
    headers={'Authorization':'Bearer '+token}
    assert c.get('/api/v1/stats',headers=headers).status_code==200
    assert c.get('/api/v1/calls',headers=headers).status_code==401
    assert c.get('/api/v1/calls/5',headers=headers).status_code==401

def test_filters_and_api_guide_require_session_permissions(client):
    c,main=client
    assert c.get('/dashboard/api').status_code == 401
    assert c.get('/dashboard/filter-options').status_code == 401
    admin = main.store.verify_login('admin','a-long-safe-testing-password')
    cookie,_=main.store.create_session(admin)
    c.cookies.set('panadan_session',cookie)
    guide=c.get('/dashboard/api')
    assert guide.status_code == 200
    assert 'Swagger UI' in guide.text
    assert 'call_type=FollowUp' in guide.text
    options=c.get('/dashboard/filter-options')
    assert options.status_code == 200
    assert options.json()['call_types'] == ['FollowUp','FirstToch']
    assert 'System Invalid' in options.json()['states']
    assert c.get('/dashboard/data?call_type=FollowUp&state=Unchecked').status_code == 200

def test_metrics_user_cannot_read_call_filter_values_or_api_guide(client):
    c,main=client
    uid=main.store.create_user('metrics-only', 'another-long-password', 'metrics', ['metrics:read'])
    cookie,_=main.store.create_session(uid)
    c.cookies.set('panadan_session',cookie)
    assert c.get('/dashboard/filter-options').status_code == 403
    assert c.get('/dashboard/api').status_code == 403
    assert c.get('/dashboard/metrics').status_code == 200


def test_browser_overview_only_uses_public_columns(client, monkeypatch):
    c, main = client
    invocations = []
    def get_call(call_id, sensitive=False):
        invocations.append((call_id, sensitive))
        return {'id': call_id, 'CALLDATE': '2026-10-29'} if not sensitive else {
            'id': call_id, 'transcription': 'PRIVATE TEST TRANSCRIPT'
        }
    monkeypatch.setattr(main.database,'get_call',get_call)
    assert c.get('/dashboard/overview/5').status_code == 401
    user_id = main.store.create_user('readerwebmcp','another-long-password','reader',['calls:read'])
    raw, _ = main.store.create_session(user_id)
    c.cookies.set('panadan_session',raw)
    response=c.get('/dashboard/overview/5')
    assert response.status_code == 200
    assert response.json() == {'id':5,'CALLDATE':'2026-10-29'}
    assert response.headers['cache-control'] == 'no-store'
    assert invocations[-1] == (5,False)
    assert all(not sensitive for _,sensitive in invocations)

def test_browser_overview_denies_metrics_only_users(client):
    c, main = client
    user_id=main.store.create_user('onlymetricsweb','another-long-password','metrics',['metrics:read'])
    raw, _ = main.store.create_session(user_id)
    c.cookies.set('panadan_session',raw)
    assert c.get('/dashboard/overview/5').status_code == 403


def test_admin_activity_page_and_reporting_are_protected(client):
    c,main=client
    assert c.get('/dashboard/activity').status_code == 401
    assert c.get('/dashboard/activity/data').status_code == 401
    uid=main.store.create_user('activityreader','safe-reader-password-long','reader',['calls:read'])
    raw,_=main.store.create_session(uid)
    c.cookies.set('panadan_session',raw)
    assert c.get('/dashboard/activity').status_code == 403
    assert c.get('/dashboard/activity/data').status_code == 403
    admin=main.store.verify_login('admin','a-long-safe-testing-password')
    token,_=main.store.create_session(admin)
    c.cookies.set('panadan_session',token)
    page=c.get('/dashboard/activity')
    assert page.status_code == 200
    assert 'فعالیت کاربران' in page.text
    data=c.get('/dashboard/activity/data?days=14')
    assert data.status_code == 200
    assert 'total' in data.json()
    assert data.headers['cache-control']=='no-store'
    assert c.get('/dashboard/activity/data?surface=invalid').status_code==400


def test_ai_transcripts_are_separately_permissioned_and_paged(client,monkeypatch):
    c,main=client
    calls=[]
    def excerpt(call_id,limit,offset):
        calls.append((call_id,limit,offset))
        return {'id':call_id,'transcription':'Hello 09121234567',
                'total_chars':12000}
    monkeypatch.setattr(main.database,'transcript_excerpt',excerpt)
    uid=main.store.create_user('ai_reader','ai-reader-password-long','analyst',
                               ['calls:read','metrics:read','mcp:use'])
    token,_=main.store.create_session(uid)
    c.cookies.set('panadan_session',token)
    assert c.get('/dashboard/ai/transcript/8').status_code == 403
    assert not calls
    admin=main.store.verify_login('admin','a-long-safe-testing-password')
    raw,_=main.store.create_session(admin)
    c.cookies.set('panadan_session',raw)
    response=c.get('/dashboard/ai/transcript/8?offset=6000')
    assert response.status_code==200
    assert calls==[(8,6000,6000)]
    assert response.json()['has_more']
    assert response.json()['next_offset']==6017
    assert '09121234567' not in response.json()['text']
    logs=main.store.list_transcript_audit()
    assert logs[0]['surface']=='webmcp'
    assert logs[0]['call_id']==8
