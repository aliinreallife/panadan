'use client';

import Link from 'next/link';
import { useStytchMemberSession } from '@stytch/nextjs/b2b';

/** Test-only browser session indicator, not proof of a completed OAuth grant. */
export function AuthStatus() {
  const { session, isInitialized } = useStytchMemberSession();

  if (!isInitialized) return <p role="status">Checking Stytch member session…</p>;

  if (!session) return (
    <div className="session-state" role="status">
      <strong>Not signed in</strong>
      <p>No Stytch Test member session is active in this browser.</p>
      <Link className="primary" href="/login">Sign in with Stytch Test</Link>
    </div>
  );

  return (
    <div className="session-state session-state--active" role="status">
      <strong>Stytch Test member signed in</strong>
      <p>Your browser has an active Stytch member session. You're ready to test a real Connected Apps authorization request.</p>
      <p className="muted">This does not mean an OAuth client has consent or that Panadan MCP accepts Stytch access tokens yet.</p>
    </div>
  );
}
