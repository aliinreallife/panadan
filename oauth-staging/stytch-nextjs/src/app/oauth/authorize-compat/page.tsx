'use client';

import { useEffect, useRef, useState } from 'react';
import { useStytchB2BClient, useStytchMemberSession } from '@stytch/nextjs/b2b';
import { RETURN_TO_KEY, validateAuthorizationParams } from '@/lib/flow';
import { canonicalStytchTestRedirect } from '@/lib/stytchTestIssuerCompat';

type OAuthRequest = {
  client_id: string;
  redirect_uri: string;
  response_type: string;
  scopes: string[];
  state: string;
  code_challenge: string;
  prompt?: string;
  nonce?: string;
};
type Preflight = {
  clientName: string;
  grantable: string[];
  nonGrantable: string[];
  consentRequired: boolean;
};

function readRequest(): OAuthRequest {
  const params = new URLSearchParams(window.location.search);
  const validation = validateAuthorizationParams(window.location.search);
  if (validation) throw new Error('invalid_request');
  const one = (key: string) => params.getAll(key).length === 1 ? params.get(key) : null;
  const state = one('state');
  if (!state || state.length > 512 || !/^[\x21-\x7e]+$/.test(state)) throw new Error('invalid_state');
  if (params.getAll('nonce').length > 1 || params.getAll('prompt').length > 1) throw new Error('duplicate_parameter');
  return {
    client_id: one('client_id')!,
    redirect_uri: one('redirect_uri')!,
    response_type: 'code',
    scopes: one('scope')!.split(/\s+/).filter(Boolean),
    state,
    code_challenge: one('code_challenge')!,
    ...(one('nonce') ? { nonce: one('nonce')! } : {}),
    ...(one('prompt') ? { prompt: one('prompt')! } : {}),
  };
}

export default function StytchTestIssuerCompatibility() {
  const stytch = useStytchB2BClient();
  const { session, isInitialized } = useStytchMemberSession();
  const [request, setRequest] = useState<OAuthRequest | null>(null);
  const [preflight, setPreflight] = useState<Preflight | null>(null);
  const [status, setStatus] = useState('Checking Test member session and OAuth request…');
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);
  const submitted = useRef(false);

  useEffect(() => {
    if (!isInitialized || started.current) return;
    started.current = true;

    // This is intentionally an experimental Test-only flow. No previews or
    // other Vercel deployments may emit modified authorization responses.
    const origin = window.location.origin;
    if (!['https://panadan-stytch-oauth-staging.vercel.app', 'http://127.0.0.1:3000', 'http://localhost:3000'].includes(origin)) {
      setError('This compatibility experiment is restricted to the Stytch Test authorization host.');
      return;
    }

    let req: OAuthRequest;
    try { req = readRequest(); }
    catch {
      setError('Invalid authorization request. Start a new OAuth session in your MCP client.');
      return;
    }

    if (!session) {
      sessionStorage.setItem(RETURN_TO_KEY, '/oauth/authorize-compat' + window.location.search);
      window.location.replace('/login');
      return;
    }

    setRequest(req);
    setStatus('Validating client and consent with Stytch Test…');

    stytch.idp.oauthAuthorizeStart({
      client_id: req.client_id,
      redirect_uri: req.redirect_uri,
      response_type: req.response_type,
      scopes: req.scopes,
      ...(req.prompt ? { prompt: req.prompt } : {}),
    }).then(async response => {
      const grantable = response.scope_results.filter(x => x.is_grantable).map(x => x.scope);
      const nonGrantable = response.scope_results.filter(x => !x.is_grantable).map(x => x.scope);
      if (!grantable.includes('panadan:mcp:read')) {
        setError('Stytch Test did not grant the required MCP read scope.');
        return;
      }
      setPreflight({
        clientName: response.client.client_name || 'MCP OAuth client',
        grantable, nonGrantable, consentRequired: response.consent_required,
      });
      setStatus('Stytch Test client authorization validated.');
      if (!response.consent_required) {
        await finish(req, false);
      }
    }).catch(() => setError('Stytch Test denied or could not validate this client and redirect URI.'));
  // The SDK client and member initialization are stable after load.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isInitialized, session, stytch]);

  async function finish(req: OAuthRequest, consentGranted: boolean) {
    if (submitted.current) return;
    submitted.current = true;
    setStatus('Completing authorization at Stytch Test…');
    try {
      const result = await stytch.idp.oauthAuthorizeSubmit({
        client_id: req.client_id,
        redirect_uri: req.redirect_uri,
        response_type: req.response_type,
        scopes: req.scopes,
        state: req.state,
        code_challenge: req.code_challenge,
        consent_granted: consentGranted,
        ...(req.nonce ? { nonce: req.nonce } : {}),
        ...(req.prompt ? { prompt: req.prompt } : {}),
      });
      // From the Stytch SDK's authenticated authorize-submit response ONLY.
      // Fail closed on unexpected issuer, state, code, or callback destination.
      const safeRedirect = canonicalStytchTestRedirect(req.redirect_uri, req.state, result);
      window.location.assign(safeRedirect);
    } catch {
      submitted.current = false;
      setError('Test authorization could not be completed safely. No OAuth redirect was issued.');
    }
  }

  return (
    <section className="content">
      <div className="eyebrow">Stytch Test · MCP issuer compatibility</div>
      <h1>Authorize synthetic MCP access</h1>
      <p className="muted">
        Experimental Test-only consent flow to align Stytch's authorization response
        with its discovered HTTPS issuer. PKCE and MCP JWT verification remain enforced.
      </p>
      {error ? <p role="alert">{error}</p> : <p role="status">{status}</p>}
      {!error && request && preflight && preflight.consentRequired && (
        <section className="session-state">
          <h2>{preflight.clientName} requests access</h2>
          <p>Requested permissions eligible for Test consent:</p>
          <ul>{preflight.grantable.map(scope => <li key={scope}><code>{scope}</code></li>)}</ul>
          {preflight.nonGrantable.length > 0 &&
            <p className="muted">Unavailable scopes are not granted: {preflight.nonGrantable.join(', ')}</p>}
          <div style={{display:'flex',gap:12,marginTop:18}}>
            <button className="primary" type="button" onClick={() => finish(request, true)}>
              Allow Test MCP access
            </button>
            <button type="button" onClick={() => setError('Access declined. Return to your MCP client and restart authorization.')}>
              Deny
            </button>
          </div>
        </section>
      )}
      <p className="muted">Only the configured Stytch Test issuer and exact, preflight-approved callback are permitted.</p>
    </section>
  );
}
