"""Synthetic, non-production tests for transcript access and activity audit."""
from types import SimpleNamespace
from datetime import datetime

import pytest

from server.security import Store, permissions
from server.transcript_ai import transcript_for_ai
from server import database


def new_store(tmp_path):
    store=Store(str(tmp_path/'auth.sqlite'))
    store.bootstrap('admin','test-admin-password-very-long')
    admin=store.verify_login('admin','test-admin-password-very-long')
    return store,admin


def test_transcript_permission_is_not_part_of_analyst_defaults():
    assert 'calls:transcript:read' in permissions('admin')
    assert 'calls:transcript:read' not in permissions('analyst')
    assert 'calls:transcript:read' not in permissions('reader')


def test_explicit_permission_and_audit_no_hourly_quota(tmp_path):
    store,admin=new_store(tmp_path)
    uid=store.create_user('transcript_analyst','analyst-password-very-long','analyst',
        ['calls:read','metrics:read','mcp:use','calls:transcript:read'])
    _,token=store.create_token('MCP','mcp:read',7,uid)
    assert store.authorized_transcript_actor(legacy_token=token)==uid
    for _ in range(25):
        assert store.audit_transcript_request(user_id=uid,surface='mcp',call_id=22,char_limit=6000)
    records=store.list_transcript_audit()
    assert len(records)==25
    assert records[0]['call_id']==22
    assert all('text' not in row and 'token' not in row for row in records)
    store.update_user(uid,'analyst',['calls:read','metrics:read','mcp:use'],True,admin)
    assert store.authorized_transcript_actor(legacy_token=token) is None
    assert not store.audit_transcript_request(user_id=uid,surface='mcp',call_id=22,char_limit=6000)


def test_read_only_transcript_pagination_and_redaction():
    full='اپراتور: سلام عزیزم، فردا تماس بگیرید. '*300+' 09121234567 hello@example.com'
    chunks=[]
    offset=0
    for _ in range(15):
        piece=full[offset:offset+6000]
        result=transcript_for_ai({
            'id':44,'transcription':piece,'total_chars':len(full)
        },offset=offset)
        assert result['call_id']==44
        assert len(result['text'])<=6000
        assert result['next_offset']==offset+len(piece)
        assert result['has_more'] is (offset+len(piece)<len(full))
        chunks.append(result)
        offset=result['next_offset']
        if not result['has_more']:
            break
    assert offset==len(full)
    assert chunks[-1]['has_more'] is False
    assert 'hello@example.com' not in chunks[-1]['text']
    assert '09121234567' not in chunks[-1]['text']


def test_transcript_query_uses_substring_and_no_personal_columns(monkeypatch):
    class Conn:
        def __init__(self):
            self.query=None
            self.args=None
        def execute(self,q,params):
            self.query=q
            self.args=params
            return self
        def fetchone(self):
            return {'id':9,'transcription':'synthetic','total_chars':100}
    from contextlib import contextmanager
    connection=Conn()
    @contextmanager
    def mock_connect():
        yield connection
    monkeypatch.setattr(database,'connect',mock_connect)
    row=database.transcript_excerpt(9,100,6000)
    assert row['id']==9
    assert connection.args==(6001,100,9)
    assert 'SUBSTRING(' in connection.query.upper()
    assert '"customername"' not in connection.query
    assert '"customertell"' not in connection.query


def test_audit_events_are_metadata_only_and_aggregated(tmp_path):
    store,_=new_store(tmp_path)
    store.record_activity(user_id=None,surface='api',action='GET /api/v1/calls',
                          http_status=200,duration_ms=15)
    store.record_activity(user_id=None,surface='mcp',action='MCP tools/call:get_call_metrics',
                          http_status=403,duration_ms=29)
    report=store.activity_report(days=7)
    assert report['total']==2
    assert report['errors']==1
    assert set(x['name'] for x in report['surfaces'])=={'api','mcp'}
    assert len(report['recent'])==2
    assert 'token' not in report['recent'][0]
    assert 'body' not in report['recent'][0]
    with pytest.raises(ValueError):
        store.record_activity(user_id=1,surface='other',action='GET /secret',
                              http_status=200,duration_ms=0)
