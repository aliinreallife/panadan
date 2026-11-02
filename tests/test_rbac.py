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


def test_mcp_requires_calls_and_metrics(tmp_path):
    store=Store(str(tmp_path/'auth.sqlite'))
    store.bootstrap('admin','a-test-password-with-14chars')
    admin=store.verify_login('admin','a-test-password-with-14chars')
    for invalid in (['mcp:use'], ['calls:read','mcp:use'],
                    ['metrics:read','mcp:use']):
        with pytest.raises(ValueError,match='MCP requires'):
            store.create_user('baduser','another-long-password','reader',invalid)
    reader=store.create_user('reader1','another-long-password','reader',['calls:read'])
    for invalid in (['mcp:use'], ['metrics:read','mcp:use']):
        with pytest.raises(ValueError,match='MCP requires'):
            store.update_user(reader,'reader',invalid,True,admin)
    # Refused changes do not revoke unrelated sessions or alter grants.
    assert store.verify_login('reader1','another-long-password') == reader
    assert store.list_users()[-1]['grants'] == '["calls:read"]'
    with pytest.raises(ValueError):store.create_token('bad','mcp:read',30,reader)


def test_legacy_inconsistent_grants_fail_closed():
    # Historical rows or direct DB edits may contain MCP without its
    # prerequisites. Never advertise mcp:use as effective authorization.
    from server.security import validate_user_grants
    for caps in ('["mcp:use"]', '["calls:read","mcp:use"]',
                 '["metrics:read","mcp:use"]'):
        effective=permissions('reader',caps)
        assert 'mcp:use' not in effective
    assert {'mcp:use','calls:read','metrics:read'} <= permissions(
        'reader','["mcp:use","calls:read","metrics:read"]'
    )
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
