'use client';
import { useState, type FormEvent } from 'react';
import Link from 'next/link';

const KEY = 'panadan_stytch_pkce_test_v1';
function randomBase64Url() {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replaceAll('+', '-').replaceAll('/', '_').replaceAll('=', '');
}

export default function TestClient() {
  const [clientId, setClientId] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function start(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const id = clientId.trim();
    if (!/^[A-Za-z0-9._~-]{8,256}$/.test(id)) {
      setError('Enter your Stytch Test Connected App Client ID.');
      return;
    }
    setBusy(true);
    try {
      const verifier = randomBase64Url();
      const state = randomBase64Url();
      const bytes = new TextEncoder().encode(verifier);
      const hash = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
      let binary = '';
      for (const byte of hash) binary += String.fromCharCode(byte);
      const challenge = btoa(binary).replaceAll('+', '-').replaceAll('/', '_').replaceAll('=', '');
      const redirectUri = window.location.origin + '/oauth/test-callback';
      sessionStorage.setItem(KEY, JSON.stringify({ state, clientId: id, redirectUri, verifier, createdAt: Date.now() }));
      const url = new URL('/oauth/authorize', window.location.origin);
      url.searchParams.set('response_type', 'code');
      url.searchParams.set('client_id', id);
      url.searchParams.set('redirect_uri', redirectUri);
      url.searchParams.set('scope', 'openid panadan:mcp:read');
      url.searchParams.set('code_challenge', challenge);
      url.searchParams.set('code_challenge_method', 'S256');
      url.searchParams.set('state', state);
      window.location.assign(url.toString());
    } catch {
      setBusy(false);
      setError('Unable to generate a browser PKCE request. Use localhost or 127.0.0.1.');
    }
  }

  return (
    <section className="content">
      <div className="eyebrow">Local PKCE OAuth test</div>
      <h1>Test Stytch Connected Apps consent</h1>
      <p>Register a <strong>Third Party Public</strong> client under Stytch <strong>Test → Connected Apps → Clients</strong>.</p>
      <p>Its registered callback must exactly match your current browser origin plus <code>/oauth/test-callback</code>.</p>
      <form onSubmit={start} style={{display:'grid',gap:12,marginTop:24}}>
        <label htmlFor="test-client-id">Stytch Test Connected App Client ID</label>
        <input id="test-client-id" autoComplete="off" spellCheck={false} value={clientId}
          onChange={e=>setClientId(e.target.value)}
          placeholder="connected-app-test-..."
          style={{padding:12,border:'1px solid #a5b5ac',borderRadius:8}} />
        {error && <p role="alert">{error}</p>}
        <button type="submit" disabled={busy} className="primary" style={{border:0,cursor:'pointer'}}>
          {busy?'Starting…':'Start Authorization Code + PKCE'}
        </button>
      </form>
      <p className="muted">The one-time code verifier and state are stored only in this browser tab. No tokens are displayed or saved.</p>
      <Link href="/">Back to staging home</Link>
    </section>
  );
}
