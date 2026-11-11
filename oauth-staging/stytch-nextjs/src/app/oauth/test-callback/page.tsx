'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';

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
  detail?: string;
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
      || !code || typeof state !== 'string' || stored.state !== state
      || stored.redirectUri !== window.location.origin + window.location.pathname) {
      setStatus('Callback rejected: missing code, incorrect state, or expired local PKCE request.');
    } else {
      setPending({ transaction: stored, code });
      setStatus('Authorization code received. State matched the original browser PKCE request.');
    }
  }, []);

  async function exchangeOnce() {
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
        }),
        cache: 'no-store',
      });
      const result = await response.json() as Inspection;
      setInspection(result);
      setStatus(response.ok ? 'Stytch Test token exchange completed.' : 'Token exchange failed: ' + (result.detail || 'Unknown error'));
    } catch {
      setStatus('Token exchange request failed. Check the local server and retry with a new authorization.');
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
        <button type="button" className="primary" style={{border:0,cursor:'pointer'}}
          onClick={exchangeOnce}>Exchange code once &amp; inspect access token</button>
      )}
      {busy && <p role="status">Contacting the Stytch Test token endpoint…</p>}
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
      <p className="muted">This local-only test exchanges the code and shows selected decoded claims. It does not verify token signatures, prove resource authorization, or contact Panadan MCP.</p>
      <Link href="/oauth/test-client">Start another authorization test</Link>
    </section>
  );
}
