"""Actual Streamable HTTP MCP exchange with synthetic data and real auth.

No live PostgreSQL, VPN or customer data is used. This exercises the SDK,
MCP ASGI gate and per-request tool identity (not merely calling tool Python).
"""
from __future__ import annotations

import importlib
import json
import pytest
from fastapi.testclient import TestClient


def unwrap(result):
    # TestClient returns an HTTP Response; MCP can use JSON or SSE framing.
    if hasattr(result, 'headers'):
        if 'text/event-stream' in result.headers.get('content-type',''):
            lines=[line.removeprefix('data: ').strip()
                   for line in result.text.splitlines() if line.startswith('data: ')]
            assert lines, result.text
            result=json.loads(lines[-1])
        else:
            result=result.json()
    assert isinstance(result, dict), result
    if "error" in result:
        raise AssertionError(result)
    body=result.get("result",{})
    if 'tools' in body:
        return body
    if "structuredContent" in body:
        return body["structuredContent"]
    text=body.get("content",[])
    assert text, body
    if body.get("isError"):
        raise AssertionError(body)
    return json.loads(text[0]["text"])


def test_real_mcp_http_authorization_and_transcript_audit(tmp_path, monkeypatch):
    monkeypatch.setenv('PANADAN_AUTH_DB',str(tmp_path/'mcp-smoke.sqlite'))
    monkeypatch.setenv('PANADAN_ADMIN_PASSWORD','test-admin-password-very-long')
    monkeypatch.setenv('PANADAN_MCP_AUTH_MODE','legacy')
    monkeypatch.setenv('PANADAN_COOKIE_SECURE','false')
    import server.main as main
    main=importlib.reload(main)
    full='agent: call about 09121234567; follow-up.'
    db_calls=[]
    def excerpt(call_id,limit,offset):
        db_calls.append((call_id,limit,offset))
        start=max(0,offset-512)
        return {'id':call_id,'transcription':full[start:offset+limit+512],
                '_window_start':start,'total_chars':len(full)}
    monkeypatch.setattr(main.database,'transcript_excerpt',excerpt)
    monkeypatch.setattr(main.database,'statuses',lambda: ['Unchecked'])

    with TestClient(main.app,base_url='http://localhost:8508') as client:
        store=main.store
        reader=store.create_user('mcpreader','a-very-long-reader-password','analyst',
                                 ['calls:read','metrics:read','mcp:use'])
        approved=store.create_user('mcpanalyst','a-very-long-analyst-password','analyst',
                        ['calls:read','metrics:read','mcp:use','calls:transcript:read'])
        _,reader_token=store.create_token('reader','mcp:read',7,reader)
        _,approved_token=store.create_token('approved','mcp:read',7,approved)
        headers_base={'accept':'application/json, text/event-stream',
                      'content-type':'application/json'}
        def post(token,method,params=None,request_id=1):
            return client.post('/mcp/',headers=headers_base|
                               {'authorization':'Bearer '+token},
                               json={'jsonrpc':'2.0','id':request_id,
                                     'method':method,'params':params or {}})
        # Real MCP initialization and tool discovery.
        initialized=post(approved_token,'initialize',{
            'protocolVersion':'2025-03-26',
            'capabilities':{},
            'clientInfo':{'name':'Panadan security smoke','version':'1.0'}
        })
        assert initialized.status_code==200, initialized.text
        tools_result=post(approved_token,'tools/list',request_id=2)
        assert tools_result.status_code==200, tools_result.text
        names=[x['name'] for x in unwrap(tools_result)['tools']]
        assert 'get_redacted_call_transcript' in names

        # A valid MCP bearer is NOT sufficient to disclose transcript text.
        denied=post(reader_token,'tools/call',{
            'name':'get_redacted_call_transcript','arguments':{'call_id':81,'offset':0}
        },request_id=3)
        assert denied.status_code==200, denied.text
        denied_data=unwrap(denied)
        assert denied_data=={'error':'permission_denied'}
        assert db_calls==[]

        permitted=post(approved_token,'tools/call',{
            'name':'get_redacted_call_transcript','arguments':{'call_id':81,'offset':0}
        },request_id=4)
        assert permitted.status_code==200, permitted.text
        data=unwrap(permitted)
        assert data['call_id']==81
        assert '09121234567' not in data['text']
        assert db_calls==[(81,6000,0)]
        audit=store.list_transcript_audit()
        assert len(audit)==1
        assert audit[0]['username']=='mcpanalyst'
        assert audit[0]['surface']=='mcp'

        # Revocation is enforced on the very next MCP tool call.
        admin=store.verify_login('admin','test-admin-password-very-long')
        store.update_user(approved,'analyst',['calls:read','metrics:read','mcp:use'],True,admin)
        blocked=post(approved_token,'tools/call',{
            'name':'get_redacted_call_transcript','arguments':{'call_id':81}
        },request_id=5)
        assert blocked.status_code==401, blocked.text
