from server.security import Store, permissions, has_capability
import pytest


def test_role_grants():
    assert 'users:manage' in permissions('admin')
    assert permissions('metrics') == {'metrics:read'}
    assert not has_capability({'role':'reader','grants':None},'calls:sensitive')
    assert 'users:manage' not in permissions('reader','["users:manage","calls:read"]')


def test_users_sessions_and_token_revocation(tmp_path):
    store=Store(str(tmp_path/'auth.sqlite'))
    store.bootstrap('admin','a-test-password-with-14chars')
    admin=store.verify_login('admin','a-test-password-with-14chars')
    assert admin
    analyst=store.create_user('analyst1','another-long-password', 'analyst', ['calls:read','metrics:read','mcp:use'])
    viewer=store.create_user('viewer1','another-long-password', 'metrics',['metrics:read'])
    assert store.verify_login('analyst1','another-long-password') == analyst
    raw,csrf=store.create_session(analyst)
    assert has_capability(store.session(raw),'mcp:use')
    _,token=store.create_token('analyst MCP','mcp:read',7,analyst)
    assert store.verify_token(token,'mcp:read')
    with pytest.raises(ValueError):store.create_token('viewer MCP','mcp:read',7,viewer)
    store.update_user(analyst,'reader',['calls:read'],True,admin)
    assert not store.session(raw)
    assert not store.verify_token(token,'mcp:read')
    store.update_user(viewer,'metrics',['metrics:read'],False,admin)
    assert store.verify_login('viewer1','another-long-password') is None
    with pytest.raises(ValueError):store.update_user(admin,'reader',None,True,admin)


def test_mcp_requires_any_reporting_capability(tmp_path):
    store=Store(str(tmp_path/'auth.sqlite'))
    store.bootstrap('admin','a-test-password-with-14chars')
    admin=store.verify_login('admin','a-test-password-with-14chars')
    with pytest.raises(ValueError,match='MCP requires'):
        store.create_user('baduser','another-long-password','reader',['mcp:use'])
    # A call-only AI connection must not be forced to get metric access.
    reader=store.create_user('reader1','another-long-password','reader',
                             ['calls:read','mcp:use'])
    metrics=store.create_user('metric1','another-long-password','metrics',
                              ['metrics:read','mcp:use'])
    _,calls_token=store.create_token('calls MCP','mcp:read',7,reader)
    _,metrics_token=store.create_token('metrics MCP','mcp:read',7,metrics)
    assert store.verify_token(calls_token,'mcp:read')
    assert store.verify_token(metrics_token,'mcp:read')
    assert store.mcp_access(reader,legacy_token=calls_token)['capabilities'] == {
        'calls:read','mcp:use'}
    assert store.mcp_access(metrics,legacy_token=metrics_token)['capabilities'] == {
        'metrics:read','mcp:use'}
    store.update_user(reader,'reader',['calls:read'],True,admin)
    assert not store.verify_token(calls_token,'mcp:read')


def test_legacy_inconsistent_grants_fail_closed():
    from server.security import validate_user_grants
    assert 'mcp:use' not in permissions('reader','["mcp:use"]')
    assert 'mcp:use' in permissions('reader','["calls:read","mcp:use"]')
    assert 'mcp:use' in permissions('metrics','["metrics:read","mcp:use"]')
    with pytest.raises(ValueError):
        validate_user_grants('reader',['mcp:use'])


def test_metrics_only_api_token_cannot_read_calls(tmp_path):
    store=Store(str(tmp_path/'auth.sqlite'))
    store.bootstrap('admin','a-test-password-with-14chars')
    uid=store.create_user('statsuser','another-long-password','metrics',['metrics:read'])
    _,token=store.create_token('metrics','api:read',30,uid)
    assert store.verify_token(token,'api:read',capability='metrics:read')
    assert not store.verify_token(token,'api:read',capability='calls:read')
    assert not store.verify_token(token,'api:sensitive',capability='calls:sensitive')
