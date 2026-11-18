'use client';
import { useState, type ReactNode } from 'react';
import { StytchB2BProvider } from '@stytch/nextjs/b2b';
import { createStytchB2BUIClient } from '@stytch/nextjs/b2b/ui';
import { isValidLivePublicToken } from '@/lib/liveToken';

export function StytchProvider({ children }: { children: ReactNode }) {
  const [client] = useState(() => {
    const token = process.env.NEXT_PUBLIC_STYTCH_PUBLIC_TOKEN || '';
    if (!isValidLivePublicToken(token)) return null;
    return createStytchB2BUIClient(token);
  });
  if (!client) {
    return (
      <section className="content">
        <div className="hero-symbol" aria-hidden="true">!</div>
        <p className="eyebrow">CONNECTION SETUP</p>
        <h1>Panadan connections are not available yet.</h1>
        <p className="lede">Your Panadan administrator is finishing the secure sign-in setup.</p>
        <div className="info-note"><span className="note-icon" aria-hidden="true">i</span>
          <p>If you are the administrator, add the Stytch Production Public Token to the Live authorization project's environment settings and redeploy it.</p>
        </div>
        <p className="small-print">No report data is exposed while setup is incomplete.</p>
      </section>
    );
  }
  return <StytchB2BProvider stytch={client}>{children}</StytchB2BProvider>;
}
