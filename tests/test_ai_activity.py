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
    assert connection.args==(5489,1124,9)
    assert row['_window_start']==5488
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


def test_sensitive_tokens_split_over_transcript_page_edges_are_masked():
    """Return pages separately; neither page may leak a partial identifier."""
    from server.transcript_ai import transcript_for_ai

    boundary = 6000
    sources = [
        'A' * (boundary - 5) + '09121234567' + ' Z',
        'A' * (boundary - 8) + 'person@example.com' + ' Z',
        'A' * (boundary - 6) + 'https://private.example.org/account/secret' + ' Z',
        'A' * (boundary - 5) + 'IR123456789012345678901234' + ' Z',
    ]
    for full in sources:
        pages = []
        for offset in (0, boundary):
            window_start = max(0, offset - 512)
            window = full[window_start:offset+6000+512]
            result = transcript_for_ai({
                'id':123, 'transcription': window,
                '_window_start':window_start,
                'total_chars':len(full)
            },offset=offset)
            pages.append(result['text'])
            assert result['next_offset']==min(len(full),offset+6000)
        combined=''.join(pages)
        for secret in ('09121234567','person@example.com',
                       'https://private.example.org/account/secret',
                       'IR123456789012345678901234'):
            assert secret not in combined
        # The beginning and end of a private token must not remain in either page.
        assert combined.count('█') >= 11
        assert len(combined) == len(full)


def test_empty_or_end_of_transcript_pages_have_safe_navigation():
    from server.transcript_ai import transcript_for_ai
    result=transcript_for_ai({
        'id':1,'transcription':'','_window_start':100,'total_chars':100
    },offset=100)
    assert result['text']==''
    assert result['next_offset']==100
    assert not result['has_more']


def test_offset_beyond_end_returns_empty_final_page():
    from server.transcript_ai import transcript_for_ai
    result=transcript_for_ai({
        'id':1,'transcription':'','_window_start':9488,
        'total_chars':80
    },offset=10000)
    assert result['text']==''
    assert result['next_offset']==10000
    assert result['has_more'] is False
