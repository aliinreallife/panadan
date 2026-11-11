'use client';

import { useEffect, useState } from 'react';
import { B2BIdentityProvider, useStytchMemberSession } from '@stytch/nextjs/b2b';
import { RETURN_TO_KEY, validateAuthorizationParams } from '@/lib/flow';

export default function AuthorizePage() {
  const { session, isInitialized } = useStytchMemberSession();
  const [error, setError] = useState<string | null>(null);
  const [validated, setValidated] = useState(false);

  useEffect(() => {
    if (!isInitialized) return;
    const issue = validateAuthorizationParams(window.location.search);
    if (issue) {
      setError(issue);
      return;
    }
    if (!session) {
      // Preserve only a same-origin authorization path and its query.
      sessionStorage.setItem(
        RETURN_TO_KEY,
        '/oauth/authorize' + window.location.search,
      );
      window.location.replace('/login');
      return;
    }
    setValidated(true);
  }, [isInitialized, session]);

  if (error) return (
    <section className="content" role="alert">
      <div className="eyebrow">Authorization request rejected</div>
      <h1>Invalid OAuth request</h1>
      <p>{error}</p>
      <p className="muted">Start a new request from your OAuth client; do not manually guess callback URLs.</p>
    </section>
  );

  if (!validated) return <p className="muted" role="status">Checking Stytch Test session and request…</p>;
  return (
    <section className="content">
      <div className="eyebrow">Connected Apps consent</div>
      <h1>Approve your MCP connection</h1>
      <p>Review the client and requested permissions below before approving.</p>
      <div className="stytch-widget"><B2BIdentityProvider /></div>
      <p className="muted">The Stytch provider issues authorization codes; this page does not issue or store access tokens.</p>
    </section>
  );
}
