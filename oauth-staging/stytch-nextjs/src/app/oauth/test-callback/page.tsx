'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { hasCanonicalAuthorizationResponseIssuer } from '@/lib/stytchTestIssuerCompat';

const KEY = 'panadan_stytch_pkce_test_v1';
type Transaction = {
  state: string;
  verifier: string;
  clientId: string;
  redirectUri: string;
  createdAt: number;
};
type Inspection = {
  status: string;
  mcp_probe?: {status: 'accepted' | 'rejected' | 'unexpected' | 'unavailable'; http_status: number | null; verified_by_resource: boolean} | null;
  detail?: string;
  provider_http_status?: number;
  provider_error_type?: string | null;
  oauth_error?: string | null;
  provider_request_id?: string | null;
  provider_response_kind?: string;
  access_token_format?: string;
  token_type?: string;
  expires_in?: number;
  refresh_token_returned?: boolean;
  jwt?: Record<string, unknown>;
};

export default function TestCallback() {
  const [status, setStatus] = useState('Checking OAuth callback…');
  const [pending, setPending] = useState<{ transaction: Transaction; code: string } | null>(null);
  const [inspection, setInspection] = useState<Inspection | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    const returnedError = query.get('error');
    const code = query.get('code');
    const state = query.get('state');
    let stored: Transaction | null = null;
    try {
      const raw = sessionStorage.getItem(KEY);
      stored = raw ? JSON.parse(raw) as Transaction : null;
    } catch { /* Invalid stored transaction */ }
    sessionStorage.removeItem(KEY);
    // Drop the one-time code from browser history immediately.
    window.history.replaceState(null, '', window.location.pathname);
    if (returnedError) {
      setStatus('Stytch rejected or cancelled authorization: ' + returnedError.slice(0, 100));
    } else if (!stored || typeof stored.createdAt !== 'number'
      || stored.createdAt > Date.now() || Date.now() - stored.createdAt > 10 * 60 * 1000
      || typeof stored.verifier !== 'string' || !/^[A-Za-z0-9_-]{43,128}$/.test(stored.verifier)
      || typeof stored.clientId !== 'string'
      || query.getAll('code').length !== 1 || query.getAll('state').length !== 1
      || !hasCanonicalAuthorizationResponseIssuer(query)
      || !code || typeof state !== 'string' || stored.state !== state
      || stored.redirectUri !== window.location.origin + window.location.pathname) {
      setStatus('Callback rejected: invalid issuer (RFC 9207), code, state, or expired local PKCE request.');
    } else {
      setPending({ transaction: stored, code });
      setStatus('Authorization code received. State matched the original browser PKCE request.');
    }
  }, []);

  async function exchangeOnce(testSyntheticMcp: boolean) {
    if (!pending || busy) return;
    const { transaction, code } = pending;
    setPending(null);
    setBusy(true);
    try {
      const response = await fetch('/api/oauth/test-token-inspect', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code,
          code_verifier: transaction.verifier,
          client_id: transaction.clientId,
          redirect_uri: transaction.redirectUri,
          probe_mcp: testSyntheticMcp,
        }),
        cache: 'no-store',
      });
      const result = await response.json() as Inspection;
      setInspection(result);
      setStatus(response.ok ? 'Stytch Test token exchange completed.' : 'Token exchange failed: ' + (result.detail || 'Unknown error'));
    } catch {
      setStatus('Token exchange request failed. Check the Test staging server and retry with a new authorization.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="content">
      <div className="eyebrow">Stytch Test OAuth callback</div>
      <h1>Authorization result</h1>
      <p role="status">{status}</p>
      {pending && !busy && (
        <div style={{display:'flex',flexWrap:'wrap',gap:12}}>
          <button type="button" className="primary" style={{border:0,cursor:'pointer'}}
            onClick={()=>exchangeOnce(true)}>Exchange code &amp; test synthetic MCP</button>
          <button type="button" style={{cursor:'pointer',padding:'10px 14px'}}
            onClick={()=>exchangeOnce(false)}>Inspect token only</button>
        </div>
      )}
      {busy && <p role="status">Contacting the Stytch Test token endpoint…</p>}
      {inspection?.status === 'error' && (
        <section className="session-state" role="status">
          <h2>Sanitized provider diagnostic</h2>
          <pre style={{overflowWrap:'anywhere',whiteSpace:'pre-wrap'}}>{JSON.stringify({
            provider_http_status: inspection.provider_http_status,
            provider_error_type: inspection.provider_error_type,
            oauth_error: inspection.oauth_error,
            provider_request_id: inspection.provider_request_id,
            provider_response_kind: inspection.provider_response_kind,
          }, null, 2)}</pre>
          <p className="muted">Only error identifiers are shown. No provider message, authorization code, PKCE verifier or token is displayed.</p>
        </section>
      )}
      {inspection?.status === 'ok' && (
        <section className="session-state">
          <h2>Sanitized token metadata</h2>
          <p>This JWT payload is decoded, <strong>not cryptographically verified</strong>.
            It cannot authorize MCP access until Panadan validates the signed token.</p>
          <pre style={{overflowWrap:'anywhere',whiteSpace:'pre-wrap'}}>
            {JSON.stringify({
              token_type: inspection.token_type,
              expires_in: inspection.expires_in,
              access_token_format: inspection.access_token_format,
              refresh_token_returned: inspection.refresh_token_returned,
              jwt: inspection.jwt,
            }, null, 2)}
          </pre>
          <p className="muted">No access token, refresh token, authorization code or PKCE verifier is returned or displayed.</p>
        </section>
      )}
      {inspection?.status === 'ok' && inspection.mcp_probe && (
        <section className="session-state" role="status">
          <h2>Live staging MCP verification</h2>
          <p><strong>{inspection.mcp_probe.status === 'accepted'
            ? 'Accepted: Stytch JWT verified and synthetic MCP tool executed.'
            : inspection.mcp_probe.status === 'rejected'
              ? 'Rejected: MCP denied this token or member/client binding.'
              : 'Not verified: staging MCP did not provide the expected synthetic result.'}</strong></p>
          <p>HTTP status: {inspection.mcp_probe.http_status ?? 'unavailable'}</p>
          <p className="muted">Only the fixed Test MCP endpoint is contacted server-to-server. No token, claims, user identifier, or tool response is returned by this probe.</p>
        </section>
      )}
      <p className="muted">Test-only OAuth code exchange. The optional MCP probe verifies the signed token on a separate, synthetic-only staging service. It does not contact production Panadan or customer data.</p>
      <Link href="/oauth/test-client">Start another authorization test</Link>
    </section>
  );
}
