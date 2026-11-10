import time
from server.security import Store, password_hash, password_check


def test_password_hash_and_verify():
    h = password_hash('a-long-secret-of-20-characters')
    assert password_check('a-long-secret-of-20-characters',h)
    assert not password_check('wrong',h)
    assert 'a-long-secret' not in h


def test_sessions_and_scoped_tokens(tmp_path):
    st=Store(str(tmp_path/'auth.sqlite'))
    st.bootstrap('admin','example-very-long-bootstrap-password')
    uid=st.verify_login('admin','example-very-long-bootstrap-password')
    assert uid
    assert st.verify_login('admin','not-password') is None
    raw,csrf=st.create_session(uid)
    assert st.session(raw)['csrf']==csrf
    st.logout(raw)
    assert st.session(raw) is None
    tid,tok=st.create_token('client','mcp:read',7)
    assert st.verify_token(tok,'mcp:read')
    assert not st.verify_token(tok,'api:read')
    assert not st.verify_token('invalid','mcp:read')
    st.revoke(tid)
    assert not st.verify_token(tok,'mcp:read')
    _,api=st.create_token('read','api:read',7)
    assert st.verify_token(api,'api:read')
    assert not st.verify_token(api,'api:sensitive')
    _,sens=st.create_token('restricted','api:sensitive',7)
    assert st.verify_token(sens,'api:read')
    assert st.verify_token(sens,'api:sensitive')


def test_bootstrap_does_not_reset_admin(tmp_path):
    st=Store(str(tmp_path/'auth.sqlite'))
    st.bootstrap('admin','an-initial-long-password')
    st.bootstrap('admin','a-different-long-password')
    assert st.verify_login('admin','an-initial-long-password')
    assert not st.verify_login('admin','a-different-long-password')



def test_verified_numeric_operator_scopes_require_admin_attestation(tmp_path):
    import pytest
    st = Store(str(tmp_path / 'scopes.sqlite'))
    st.bootstrap('admin', 'example-very-long-bootstrap-password')
    admin = st.verify_login('admin', 'example-very-long-bootstrap-password')
    user_a = st.create_user('operator_reader_a', 'reader-a-long-password', 'reader')
    user_b = st.create_user('operator_reader_b', 'reader-b-long-password', 'reader')
    assert st.verified_operator_ids(admin) == []  # No admin wildcard
    assert st.verified_operator_ids(user_a) == []

    with pytest.raises(ValueError, match='verified source identity'):
        st.authorize_operator_scope(
            admin_id=admin, user_id=user_a, operator_id=11)
    with pytest.raises(PermissionError, match='administrator'):
        st.authorize_operator_scope(
            admin_id=user_a, user_id=user_a, operator_id=11,
            source_identity_verified=True)
    with pytest.raises(ValueError, match='operator ID'):
        st.authorize_operator_scope(
            admin_id=admin, user_id=user_a, operator_id=True,
            source_identity_verified=True)
    with pytest.raises(ValueError, match='operator ID'):
        st.authorize_operator_scope(
            admin_id=admin, user_id=user_a, operator_id=0,
            source_identity_verified=True)

    st.authorize_operator_scope(
        admin_id=admin, user_id=user_a, operator_id=11,
        source_identity_verified=True)
    st.authorize_operator_scope(
        admin_id=admin, user_id=user_a, operator_id=12,
        source_identity_verified=True)
    st.authorize_operator_scope(
        admin_id=admin, user_id=user_b, operator_id=22,
        source_identity_verified=True)
    assert st.verified_operator_ids(user_a) == [11, 12]
    assert st.verified_operator_ids(user_b) == [22]
    assert st.verified_operator_ids(admin) == []

    with pytest.raises(PermissionError, match='administrator'):
        st.revoke_operator_scope(
            admin_id=user_b, user_id=user_a, operator_id=11)
    st.revoke_operator_scope(admin_id=admin, user_id=user_a, operator_id=11)
    assert st.verified_operator_ids(user_a) == [12]

    # An existing account role/capability change erases all approvals.
    st.update_user(user_b, 'reader', None, True, admin)
    assert st.verified_operator_ids(user_b) == []
    st.update_user(user_a, 'reader', None, False, admin)
    assert st.verified_operator_ids(user_a) == []
    with pytest.raises(PermissionError, match='target'):
        st.authorize_operator_scope(
            admin_id=admin, user_id=user_a, operator_id=11,
            source_identity_verified=True)
    with st.db() as c:
        audit = c.execute(
            "SELECT target_user_id,operator_id,action FROM operator_scope_audit "
            "ORDER BY event_id"
        ).fetchall()
    assert [row['action'] for row in audit] == [
        'grant', 'grant', 'grant', 'revoke', 'reset', 'reset']
    assert [(row['target_user_id'], row['operator_id']) for row in audit[-2:]] == [
        (user_b, 22), (user_a, 12)]

