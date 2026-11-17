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

    // Preserve the unmodified OAuth PKCE, redirect_uri, state, and resource
    // parameters across email OTP and organization selection. Never place
    // token codes in localStorage, logs or the UI.
    if (!session) {
      sessionStorage.setItem(RETURN_TO_KEY, '/oauth/authorize' + window.location.search);
      window.location.replace('/login');
      return;
    }
    setValidated(true);
  }, [isInitialized, session]);

  if (error) return (
    <section className="content" role="alert">
      <h1>Invalid authorization request</h1>
      <p>{error}</p>
      <p className="muted">Restart the connection from ChatGPT. Do not paste an OAuth code here.</p>
    </section>
  );
  if (!validated) return <p role="status">Validating the Live OAuth request…</p>;

  // Stytch handles trusted client registration, consent, authorization code
  // issuance and redirects. Do not use the experimental Test issuer rewrite.
  return (
    <section className="content">
      <div className="eyebrow">Production consent</div>
      <h1>Authorize Panadan access</h1>
      <p>Review the permissions that the connected application is requesting.</p>
      <B2BIdentityProvider />
    </section>
  );
}
