'use client';

import { useEffect, useState } from 'react';
import { validateAuthorizationParams } from '@/lib/flow';

/**
 * Backwards-compatible alias for clients caching the previous authorize URL.
 *
 * All Stytch Test authorization requests must pass through the same
 * explicitly pinned issuer-compatibility boundary. Never render the old
 * B2BIdentityProvider widget here: it redirects directly using the legacy
 * Stytch Test authorization-response iss and fails RFC 9207 clients.
 *
 * Preserve the original query unmodified (state, PKCE, redirect_uri, and
 * resource indications) and move only to a SAME-ORIGIN path. The compat
 * route performs its own Test-only origin, request, and consent checks.
 */
export default function AuthorizePage() {
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const issue = validateAuthorizationParams(window.location.search);
    if (issue) {
      setError(issue);
      return;
    }
    window.location.replace('/oauth/authorize-compat' + window.location.search);
  }, []);

  if (error) return (
    <section className="content" role="alert">
      <div className="eyebrow">Authorization request rejected</div>
      <h1>Invalid OAuth request</h1>
      <p>{error}</p>
      <p className="muted">Start a new request from your OAuth client. Do not manually guess callback URLs.</p>
    </section>
  );

  return <p role="status" className="muted">Continuing to Stytch Test authorization…</p>;
}
