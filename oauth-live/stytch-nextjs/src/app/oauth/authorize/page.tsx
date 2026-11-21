'use client';
import { useEffect, useState } from 'react';
import { B2BIdentityProvider, useStytchMemberSession } from '@stytch/nextjs/b2b';
import { captureAuthorizationSearch, clearAuthorizationReturnTo, validateAuthorizationParams } from '@/lib/oauthRequest';

export default function AuthorizePage() {
  const { session, isInitialized } = useStytchMemberSession();
  const [error, setError] = useState<string | null>(null);
  const [validated, setValidated] = useState(false);
  const [requestReady, setRequestReady] = useState(false);

  // Capture the original OAuth request immediately. Waiting for Stytch's
  // async session initialization can lose the request during login redirects.
  useEffect(() => {
    const query = window.location.search;
    const issue = validateAuthorizationParams(query);
    if (issue) { setError(issue); return; }
    const saved = captureAuthorizationSearch(
      query, window.sessionStorage, window.localStorage,
    );
    if (!saved) {
      setError('Unable to preserve OAuth authorization request');
      return;
    }
    setRequestReady(true);
  }, []);

  useEffect(() => {
    if (!requestReady || !isInitialized) return;
    if (!session) {
      window.location.replace('/login');
      return;
    }
    // The authenticated member can now review the original request.
    clearAuthorizationReturnTo(window.sessionStorage, window.localStorage);
    setValidated(true);
  }, [requestReady, isInitialized, session]);

  if (error) return (
    <section className="content">
      <div className="error-message" role="alert">
        <div className="eyebrow">CONNECTION LINK INVALID</div>
        <h1>Start again from ChatGPT.</h1>
        <p>This connection link is incomplete or no longer valid. Return to ChatGPT, choose Connect again, and we'll pick up from there.</p>
      </div>
    </section>
  );
  if (!validated) return (
    <section className="content" role="status">
      <div className="loader">Preparing your secure connection…</div>
    </section>
  );

  return (
    <section className="content">
      <div className="flow-progress" aria-label="Step 2 of 2">
        <span>1. Sign in</span><span className="flow-dot" />
        <span className="current">2. Approve access</span>
      </div>
      <p className="eyebrow">YOUR PERMISSIONS, YOUR CHOICE</p>
      <h1>Review access to Panadan.</h1>
      <p className="subhead">Check which permissions this application is requesting. Continue only if you recognize it.</p>
      <div className="stytch-widget"><B2BIdentityProvider /></div>
      <p className="session-note">After approval, you'll return to ChatGPT automatically. Panadan's existing account and field restrictions still apply.</p>
    </section>
  );
}
