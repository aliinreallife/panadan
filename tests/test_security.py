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
