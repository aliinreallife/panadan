'use client';

import Link from 'next/link';
import { useStytchMemberSession } from '@stytch/nextjs/b2b';

/** Render the home and the session state inside one client boundary. */
export default function HomePage() {
  const { session, isInitialized } = useStytchMemberSession();

  return (
    <section className="content">
      <div className="eyebrow">Connected Apps / Test</div>
      <h1>Secure authorization for Panadan</h1>
      <p>This isolated application handles Stytch B2B test-member authentication and OAuth consent.</p>
      <p>Start an actual authorization request from a supported MCP client to see the consent screen.</p>
      {!isInitialized ? (
        <p role="status">Checking Stytch member session…</p>
      ) : session ? (
        <div className="session-state session-state--active" role="status">
          <strong>Stytch Test member signed in</strong>
          <p>Your browser has an active Stytch member session. You're ready to test a real Connected Apps authorization request.</p>
          <p className="muted">This does not mean an OAuth client has consent or that Panadan MCP accepts Stytch access tokens yet.</p>
        </div>
      ) : (
        <div className="session-state" role="status">
          <strong>Not signed in</strong>
          <p>No Stytch Test member session is active in this browser.</p>
          <Link className="primary" href="/login">Sign in with Stytch Test</Link>
        </div>
      )}
      <p><Link href="/oauth/test-client">Test authorization and consent with a local PKCE client</Link></p>
      <p className="muted">No customer data, Panadan production database or Legacy MCP tokens are used here.</p>
    </section>
  );
}
