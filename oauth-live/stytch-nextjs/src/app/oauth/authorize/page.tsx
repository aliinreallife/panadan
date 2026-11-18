'use client';
import { useEffect, useState } from 'react';
import { B2BIdentityProvider, useStytchMemberSession } from '@stytch/nextjs/b2b';
import { RETURN_TO_KEY, validateAuthorizationParams } from '@/lib/oauthRequest';

export default function AuthorizePage() {
  const { session, isInitialized } = useStytchMemberSession();
  const [error, setError] = useState<string | null>(null);
  const [validated, setValidated] = useState(false);

  useEffect(() => {
    if (!isInitialized) return;
    const issue = validateAuthorizationParams(window.location.search);
    if (issue) { setError(issue); return; }

    // Keep the exact OAuth request through sign-in. Never store or print
    // authorization codes or access tokens. The native Stytch component
    // remains the only code issuer and consent authority.
    if (!session) {
      sessionStorage.setItem(RETURN_TO_KEY, '/oauth/authorize' + window.location.search);
      window.location.replace('/login');
      return;
    }
    setValidated(true);
  }, [isInitialized, session]);

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
