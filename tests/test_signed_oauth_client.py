"""Signed-token client identity handling, with cryptographic tests elsewhere."""
import time
from types import SimpleNamespace

from server import oauth_mcp


def test_client_identity_must_come_from_signed_verified_claims(monkeypatch):
    verifier = object.__new__(oauth_mcp.OAuthVerifier)
    verifier.config = SimpleNamespace(
        issuer='https://trusted.test', resource='https://panadan.test/mcp/',
        scope='panadan:mcp:read', max_ttl_seconds=3600)
    verifier.jwks = SimpleNamespace(
        get_signing_key_from_jwt=lambda _raw: SimpleNamespace(key='synthetic-key'))
    monkeypatch.setattr(oauth_mcp.jwt, 'get_unverified_header',
                        lambda _raw: {'alg':'RS256','kid':'test-key'})

    now = int(time.time())
    claims = {
        'sub':'user-123', 'iat':now - 60, 'exp':now + 300,
        'scope':'panadan:mcp:read', 'token_use':'access',
        'azp':'trusted-client-123', 'client_id':'trusted-client-123'
    }
    monkeypatch.setattr(oauth_mcp.jwt,'decode',lambda *args,**kwargs: claims.copy())
    details = verifier.verify_details('a.b.c')
    assert details == {'subject':'user-123','client_id':'trusted-client-123'}
    assert verifier.verify('a.b.c') == 'user-123'

    claims['client_id']='different-client'
    assert verifier.verify_details('a.b.c') is None
    claims.pop('client_id')
    assert verifier.verify_details('a.b.c')['client_id'] == 'trusted-client-123'

    claims.pop('azp')
    assert verifier.verify_details('a.b.c')['client_id'] is None
    # A missing client identity must fail later at client-specific delegation;
    # it cannot match another client by display name or request argument.


def test_bad_or_unverified_token_rejected_without_jwks_lookup():
    verifier = object.__new__(oauth_mcp.OAuthVerifier)
    assert verifier.verify_details('not.a.jwt.with.too.many.parts') is None
    assert verifier.verify_details('') is None
