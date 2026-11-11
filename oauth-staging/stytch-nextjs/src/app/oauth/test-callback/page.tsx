'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';

const KEY = 'panadan_stytch_pkce_test_v1';

export default function TestCallback() {
  const [status, setStatus] = useState('Checking OAuth callback…');
  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    const returnedError = query.get('error');
    const code = query.get('code');
    const state = query.get('state');
    let stored: { state?: string; clientId?: string; createdAt?: number; redirectUri?: string } | null = null;
    try {
      const raw = sessionStorage.getItem(KEY);
      stored = raw ? JSON.parse(raw) : null;
    } catch { /* Invalid stored transaction */ }
    sessionStorage.removeItem(KEY);
    window.history.replaceState(null, '', window.location.pathname);
    if (returnedError) {
      setStatus('Stytch rejected or cancelled authorization: ' + returnedError.slice(0, 100));
    } else if (!stored || typeof stored.createdAt !== 'number' || Date.now() - stored.createdAt > 10*60*1000
      || stored.createdAt > Date.now()
      || !code || !state || stored.state !== state
      || stored.redirectUri !== window.location.origin + window.location.pathname) {
      setStatus('Callback rejected: missing code, incorrect state, or expired local PKCE request.');
    } else {
      setStatus('Authorization code received. State matched the original browser PKCE request.');
    }
  }, []);

  return (
    <section className="content">
      <div className="eyebrow">Stytch Test OAuth callback</div>
      <h1>Authorization result</h1>
      <p role="status">{status}</p>
      <p className="muted">This smoke test verifies a code and state only. It does not exchange the code, verify an access-token JWT, or grant access to Panadan MCP.</p>
      <Link href="/oauth/test-client">Start another authorization test</Link>
    </section>
  );
}
