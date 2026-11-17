'use client';
import { useState, type FormEvent } from 'react';
import Link from 'next/link';
import { STAGING_CIMD_CLIENT_ID, STAGING_CIMD_REDIRECT_URI } from '@/lib/testCimdClient';

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
  const [clientMode, setClientMode] = useState<'manual' | 'cimd'>('manual');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function start(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const id = clientMode === 'cimd' ? STAGING_CIMD_CLIENT_ID : clientId.trim();
    if (clientMode === 'cimd' && window.location.origin + '/oauth/test-callback' !== STAGING_CIMD_REDIRECT_URI) {
      setError('CIMD tests are available only on the canonical hosted Stytch Test staging origin.');
      return;
    }
    if (clientMode === 'manual' && !/^connected-app-test-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(id)) {
      setError('Enter the existing Stytch Test Connected App Client ID.');
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
      if (clientMode === 'cimd') {
        // The authorization request includes the RFC 8707 resource indicator.
        // Whether Stytch's headless authorize SDK propagates it remains a
        // provider-level interoperability question; the MCP still pins aud.
        url.searchParams.set('resource', 'https://panadan-mcp-oauth-staging.vercel.app/mcp/');
      }
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
        <label htmlFor="test-client-mode">Test client registration</label>
        <select id="test-client-mode" value={clientMode} onChange={e => {setClientMode(e.target.value as 'manual' | 'cimd');setError('');}}
          style={{padding:12,border:'1px solid #a5b5ac',borderRadius:8}}>
          <option value="manual">Existing registered Test client (baseline)</option>
          <option value="cimd">CIMD: HTTPS metadata document (experimental)</option>
        </select>
        {clientMode === 'manual' ? (
          <>
            <label htmlFor="test-client-id">Stytch Test Connected App Client ID</label>
            <input id="test-client-id" autoComplete="off" spellCheck={false} value={clientId}
              onChange={e=>setClientId(e.target.value)}
              placeholder="connected-app-test-..."
              style={{padding:12,border:'1px solid #a5b5ac',borderRadius:8}} />
          </>
        ) : (
          <p className="muted">Test client ID: <code style={{overflowWrap:'anywhere'}}>{STAGING_CIMD_CLIENT_ID}</code>.
            Stytch Test will retrieve its public metadata and verify the callback URL.
            This experiment does not grant access to customer data.</p>
        )}
        {error && <p role="alert">{error}</p>}
        <button type="submit" disabled={busy} className="primary" style={{border:0,cursor:'pointer'}}>
          {busy?'Starting…':'Start Authorization Code + PKCE'}
        </button>
      </form>
      <p className="muted">The one-time code verifier and state are stored only in this browser tab. No tokens are displayed or saved. The CIMD experiment requests the canonical MCP resource; a 401 due to a missing token audience is a valid fail-closed finding.</p>
      <Link href="/">Back to staging home</Link>
    </section>
  );
}
