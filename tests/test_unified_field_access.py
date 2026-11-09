"""Synthetic security tests for live user field grants and MCP delegation."""
from __future__ import annotations

import json

import pytest

from server.field_permissions import (
    FIELD_SET, REPORT_FIELDS, capability_fields, effective_fields,
    explain_field, project_call, project_metrics, validate_fields,
)
from server.security import Store


def test_reporting_projection_exact_fields_no_hidden_metadata():
    granted = frozenset({'id', 'CALLDATE', 'aicallinfostate'})
    record = {'id': 17, 'CALLDATE': '2026-11-09',
              'aicallinfostate': 'Unchecked', 'customertell': 'DO-NOT-LEAK',
              'transcription': 'DO-NOT-LEAK', 'internal_key': 'DO-NOT-LEAK'}
    assert project_call(record, granted) == {
        'id': 17, 'CALLDATE': '2026-11-09',
        'aicallinfostate': 'Unchecked'}
    assert project_call(None, granted) is None
    assert project_metrics({
        'total': 42, 'sold_out': 17, 'avg_ai_score': 96,
        'avg_voice_length': 10.5, 'extra': 'DO-NOT-LEAK'
    }, granted) == {'total': 42, 'sold_out': 17}


def test_legacy_field_defaults_and_broken_grants_fail_closed():
    defaults = capability_fields({'calls:read'})
    assert 'id' in defaults and 'customername' not in defaults
    assert effective_fields({'calls:read'}, None) == defaults
    assert effective_fields({'calls:read'}, 'bad JSON') == frozenset()
    assert effective_fields({'calls:read'}, '{"id":true}') == frozenset()
    assert effective_fields({'calls:read'}, '["id","unknown"]') == frozenset()
    with pytest.raises(ValueError):
        validate_fields(['customertell'], {'calls:read'})
    with pytest.raises(ValueError):
        validate_fields(['id','id'], {'calls:read'})
    assert len(FIELD_SET) == len(REPORT_FIELDS)


def test_user_with_three_columns_and_revocable_legacy_mcp_token(tmp_path):
    store = Store(str(tmp_path / 'auth.sqlite'))
    store.bootstrap('admin', 'admin-password-very-long')
    user = store.create_user(
        'threefields', 'example-password-very-long', 'analyst',
        ['calls:read','metrics:read','mcp:use'],
        fields=['id','CALLDATE','aicallinfostate'],
    )
    rights = store.user_access(user)
    assert rights['fields'] == {'id','CALLDATE','aicallinfostate'}
    _, token = store.create_token('AI', 'mcp:read', 30, user)
    delegated = store.mcp_access(user, legacy_token=token)
    assert delegated['fields'] == rights['fields']
    assert delegated['capabilities'] == {'calls:read','metrics:read','mcp:use'}

    admin = store.verify_login('admin', 'admin-password-very-long')
    store.update_user(
        user, 'analyst', ['calls:read','metrics:read','mcp:use'],
        True, admin, fields=['id','aicallinfostate'],
    )
    assert store.user_access(user)['fields'] == {'id','aicallinfostate'}
    assert not store.verify_token(token, 'mcp:read')
    assert store.mcp_access(user, legacy_token=token) is None


def test_client_consent_defaults_can_be_narrowed_and_revoked(tmp_path):
    store = Store(str(tmp_path / 'auth.sqlite'))
    store.bootstrap('admin', 'admin-password-very-long')
    user = store.create_user(
        'clientowner','example-password-very-long','analyst',
        ['calls:read','metrics:read','mcp:use'],
        fields=['id','CALLDATE','aicallinfostate']
    )
    store.approve_mcp_client(user, 'verified-oauth-client',
                             ['mcp:use','calls:read'],
                             ['id','CALLDATE'])
    allowed = store.mcp_access(user, oauth_client='verified-oauth-client')
    assert allowed['fields'] == {'id','CALLDATE'}
    assert 'metrics:read' not in allowed['capabilities']
    assert store.mcp_access(user, oauth_client='another-client')['fields'] == set()
    assert store.mcp_access(user, oauth_client='another-client')['capabilities'] == set()
    with pytest.raises(ValueError):
        store.approve_mcp_client(user, 'verified-oauth-client',
                                 ['mcp:use','calls:read'],['customertell'])
    with pytest.raises(ValueError):
        store.approve_mcp_client(user, 'verified-oauth-client',
                                 ['mcp:use','metrics:read'],['CALLDATE'])

    store.revoke_mcp_client(user,'verified-oauth-client')
    assert store.mcp_access(user, oauth_client='verified-oauth-client')['fields'] == set()


def test_new_permissions_never_silently_expand_existing_oauth_grant(tmp_path):
    store = Store(str(tmp_path / 'auth.sqlite'))
    store.bootstrap('admin','admin-password-very-long')
    uid = store.create_user('limited','example-password-very-long','reader',
                            ['calls:read','mcp:use'], fields=['id','CALLDATE'])
    store.approve_mcp_client(uid,'verified-client',
                             ['mcp:use','calls:read'],['id'])
    assert store.mcp_access(uid,oauth_client='verified-client')['fields'] == {'id'}
    admin = store.verify_login('admin','admin-password-very-long')
    store.update_user(uid,'reader',['calls:read','mcp:use'],True,admin,
                      fields=['id','CALLDATE','tellstate'])
    # User still owns three fields, but app grant was invalidated and must
    # be explicitly reapproved; it cannot silently inherit new fields.
    assert store.user_access(uid)['fields'] == {'id','CALLDATE','tellstate'}
    assert store.mcp_access(uid,oauth_client='verified-client')['fields'] == set()


def test_permission_discovery_reason_codes_are_self_only():
    user = frozenset({'id','CALLDATE'})
    approved = frozenset({'id'})
    effective = user & approved
    assert explain_field('id',user,approved,effective)['reason'] == 'allowed'
    assert explain_field('CALLDATE',user,approved,effective)['reason'] == 'needs_user_consent'
    assert explain_field('customertell',user,approved,effective)['reason'] == 'needs_admin_grant'
    assert explain_field('not_a_field',user,approved,effective)['reason'] == 'unknown_or_unavailable'



def test_raw_transcripts_never_leak_through_general_call_json():
    from server.field_permissions import project_call, capability_fields
    caps = {"calls:read", "calls:sensitive", "calls:transcript:read"}
    assert "transcription" in capability_fields(caps)  # audited tool only
    full = {"id": 1, "transcription": "RAW-PERSONAL-SECRET",
            "summary": "safe summary", "customername": "Jane"}
    data = project_call(full, capability_fields(caps))
    assert "transcription" not in data
    assert "RAW-PERSONAL-SECRET" not in str(data)
    assert data["summary"] == "safe summary"
    assert "transcription" not in capability_fields(
        {"calls:read", "calls:sensitive"}
    )
