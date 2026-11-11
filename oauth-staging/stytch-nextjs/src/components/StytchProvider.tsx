'use client';

import { useState, type ReactNode } from 'react';
import { StytchB2BProvider } from '@stytch/nextjs/b2b';
import { createStytchB2BUIClient } from '@stytch/nextjs/b2b/ui';

export function StytchProvider({ children }: { children: ReactNode }) {
  const [client] = useState(() => {
    const publicToken = process.env.NEXT_PUBLIC_STYTCH_PUBLIC_TOKEN || '';
    // Never fall back to Live, or fabricate a working authentication session.
    if (!publicToken.startsWith('public-token-test-')) return null;
    return createStytchB2BUIClient(publicToken);
  });

  if (!client) {
    return (
      <div className="setup-message" role="alert">
        <h1>Stytch Test configuration required</h1>
        <p>Set NEXT_PUBLIC_STYTCH_PUBLIC_TOKEN to your Stytch B2B Test Public Token in .env.local.</p>
        <p>Do not use the Stytch Secret Key or a Live environment token.</p>
      </div>
    );
  }
  return <StytchB2BProvider stytch={client}>{children}</StytchB2BProvider>;
}
