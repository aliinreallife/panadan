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
    monkeypatch.setattr(main.database, 'statuses',lambda *a,**k:['Unchecked'])
    with TestClient(main.app) as c: yield c,main


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
