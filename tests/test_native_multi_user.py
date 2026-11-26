"""Opt-in multi-user WorkOS authorization tests. No real provider or report data."""
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit, parse_qs
from dataclasses import replace
import pytest
from server.security import Store
from server.authkit_login import AuthKitConfig, AuthKitError
from server.oauth_mcp import OAuthConfig, OAuthVerifier
import jwt
import time
from types import SimpleNamespace
from cryptography.hazmat.primitives.asymmetric import rsa

ISSUER='https://synthetic.authkit.app'
ORIGIN='https://panadan.invalid'
ADMIN='user_admin123'
EMAIL='owner@example.invalid'

def test_verified_identity_and_no_email_linking(tmp_path):
    cfg=AuthKitConfig(True,'client_test','sk_test_synthetic_key',EMAIL,ADMIN,ORIGIN,1,True)
    assert 'login_hint' not in parse_qs(urlsplit(cfg.begin()[0]).query)
    assert cfg.verified_identity({'id':'user_new123','email':'new@example.invalid','email_verified':True}) == ('user_new123','new@example.invalid')
    for subject,email,verified in [(ADMIN,'other@example.invalid',True),
        ('user_new123',EMAIL,True),('user_new123','new@example.invalid',False)]:
        with pytest.raises(AuthKitError):
            cfg.verified_identity({'id':subject,'email':email,'email_verified':verified})
    db=Store(str(tmp_path/'auth.sqlite'))
    db.bootstrap('admin','synthetic-password-long')
    old=db.create_user('old','synthetic-password-long','analyst')
    db.prepare_authkit_admin(1,ISSUER,ADMIN,multi_user=True)
    uid=db.provision_native_user(ISSUER,'user_new123','new@example.invalid')
    assert uid!=old and uid!=1
    assert db.user_access(uid)['capabilities']==set()
    assert db.user_access(uid)['fields']==set()
    assert db.user_access(old) is None
    assert db.native_account(uid,ISSUER)['panel_grants']==set()
    assert db.provision_native_user(ISSUER,'user_new123','new@example.invalid')==uid
    with pytest.raises(ValueError):
        db.provision_native_user(ISSUER,'user_attacker','new@example.invalid')
    assert db.actor_for_oauth(ISSUER,'user_attacker') is None
    assert not db.oauth_identity_has_mcp_access(ISSUER,'user_new123')
    with pytest.raises(ValueError):
        db.approve_mcp_client(uid,'client_test',['mcp:use','calls:read'],['id'])
    with pytest.raises(ValueError):
        db.update_native_user(uid,ISSUER,actor_id=uid,active=True,caps=['calls:read'],fields=['id'],panels=[])
    with pytest.raises(ValueError):
        db.update_native_user(uid,ISSUER,actor_id=1,active=True,caps=['users:manage'],fields=[],panels=[])
    db.update_native_user(uid,ISSUER,actor_id=1,active=True,caps=[],fields=[],panels=['system:read'])
    assert db.user_access(uid)['fields']==set()
    assert db.native_account(uid,ISSUER)['panel_grants']=={'system:read'}
    db.update_native_user(uid,ISSUER,actor_id=1,active=True,
        caps=['calls:read','mcp:use'],fields=['id'],panels=[])
    db.approve_mcp_client(uid,'client_test',['mcp:use','calls:read'],['id'])
    assert db.mcp_access(uid,oauth_client='client_test')['fields']=={'id'}
    with pytest.raises(ValueError):
        db.approve_mcp_client(uid,'client_test',['mcp:use','calls:read'],['id','CALLDATE'])
    db.prepare_authkit_admin(1,ISSUER,ADMIN,multi_user=True)
    assert db.user_access(uid)['fields']=={'id'}
    db.update_native_user(uid,ISSUER,actor_id=1,active=False,caps=[],fields=[],panels=[])
    assert db.user_access(uid) is None
    assert db.client_grants(uid,'client_test') is None
    with pytest.raises(ValueError):
        db.provision_native_user(ISSUER,'user_new123','new@example.invalid')

def test_multi_user_tokens_still_require_signed_client_and_exact_resource():
    cfg=OAuthConfig(mode='oauth',issuer=ISSUER,jwks_url=ISSUER+'/oauth2/jwks',resource=ORIGIN+'/mcp/',
        scope='openid',authkit_admin_subject=ADMIN,authkit_multi_user=True)
    verifier=OAuthVerifier(cfg)
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    verifier.jwks=SimpleNamespace(get_signing_key_from_jwt=lambda raw:SimpleNamespace(key=key.public_key()))
    now=int(time.time())
    base={'iss':ISSUER,'aud':cfg.resource,'sub':'user_member123','iat':now,'exp':now+300,
          'scope':'openid','sid':'session','jti':'token','client_id':'client_test'}
    def token(d):return jwt.encode(d,key,algorithm='RS256',headers={'kid':'test'})
    assert verifier.verify_details(token(base))['subject']=='user_member123'
    for changed in [{'sub':'panadan-user-1'},{'client_id':None},{'sub_profile':'ai_agent'},
                    {'aud':'https://other.invalid/mcp/'},{'scope':'email'}]:
        assert verifier.verify_details(token({**base,**changed})) is None

def test_multi_user_browser_and_panel_boundaries(tmp_path):
    env={k:v for k,v in os.environ.items() if not k.startswith(('PANADAN_','WORKOS_'))}
    script="import runpy,sys; from pathlib import Path; runpy.run_path(sys.argv[1])['_exercise'](Path(sys.argv[2]))"
    result=subprocess.run([sys.executable,'-c',script,str(Path(__file__).resolve()),str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],env=env,capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr

def _exercise(tmp_path):
    from fastapi.testclient import TestClient
    from contextlib import asynccontextmanager
    from unittest.mock import patch
    os.environ.update({
        'PANADAN_AUTH_DB':str(tmp_path/'auth.sqlite'),'PANADAN_AUTH_BACKEND':'sqlite',
        'PANADAN_PUBLIC_ORIGIN':ORIGIN,'PANADAN_COOKIE_SECURE':'true',
        'PANADAN_WEB_AUTH_MODE':'authkit','PANADAN_AUTHKIT_MULTI_USER':'true',
        'PANADAN_MCP_AUTH_MODE':'oauth','PANADAN_OAUTH_ISSUER':ISSUER,
        'PANADAN_OAUTH_JWKS_URL':ISSUER+'/oauth2/jwks','PANADAN_OAUTH_RESOURCE':ORIGIN+'/mcp/',
        'PANADAN_OAUTH_SCOPE':'openid','WORKOS_CLIENT_ID':'client_test',
        'WORKOS_API_KEY':'sk_test_synthetic_key','PANADAN_AUTHKIT_ADMIN_EMAIL':EMAIL,
        'PANADAN_AUTHKIT_ADMIN_SUBJECT':ADMIN,'PANADAN_AUTHKIT_ADMIN_UID':'1'})
    import server.main as main
    main.store.bootstrap('admin','synthetic-password-long')
    main.store.prepare_authkit_admin(1,ISSUER,ADMIN,multi_user=True)
    @asynccontextmanager
    async def isolated(_):yield
    main.app.router.lifespan_context=isolated
    def exchange(self,code,verifier):
        return self.verified_identity({'id':ADMIN if code=='admin' else 'user_member123',
            'email':EMAIL if code=='admin' else 'member@example.invalid','email_verified':True})
    def signin(client,code):
        r=client.get('/auth/workos/start',follow_redirects=False)
        state=parse_qs(urlsplit(r.headers['location']).query)['state'][0]
        r=client.get('/auth/workos/callback',params={'state':state,'code':code},follow_redirects=False)
        assert r.headers['location']=='/dashboard',r.text
        return main.store.session(client.cookies.get(main.COOKIE_NAME),auth_source='authkit')
    with patch.object(AuthKitConfig,'exchange',exchange):
      with TestClient(main.app,base_url=ORIGIN) as member, TestClient(main.app,base_url=ORIGIN) as owner:
        m=signin(member,'member'); a=signin(owner,'admin')
        uid=m['user_id']; assert uid!=a['user_id']
        page=member.get('/dashboard')
        assert page.status_code==200 and 'account-access-card' in page.text
        for path in ['/dashboard/data','/dashboard/metrics','/dashboard/system','/dashboard/activity',
                     '/dashboard/users','/dashboard/tokens','/dashboard/oauth','/dashboard/api',
                     '/dashboard/connect','/dashboard/mcp-apps']:
            assert member.get(path).status_code==403,path
        assert member.post(f'/dashboard/users/{uid}/native-access',data={'csrf':m['csrf'],
            'is_active':'true','panels':'system:read'}).status_code==403
        users=owner.get('/dashboard/users')
        assert users.status_code==200 and 'member@example.invalid' in users.text and '/native-access' in users.text
        r=owner.post(f'/dashboard/users/{uid}/native-access',data={'csrf':a['csrf'],
            'is_active':'true','panels':'system:read'},follow_redirects=False)
        assert r.status_code==303,r.text
        assert member.get('/dashboard/system').status_code==401
        m=signin(member,'member')
        assert member.get('/dashboard/system').status_code==200
        assert member.get('/dashboard/data').status_code==403
        assert member.get('/dashboard/users').status_code==403
        assert main.store.user_access(uid)['fields']==set()
        r=owner.post(f'/dashboard/users/{uid}/native-access',data={'csrf':a['csrf'],
            'is_active':'true','grants':'users:manage'},follow_redirects=False)
        assert r.status_code==400
        assert owner.get('/dashboard/users').status_code==200
