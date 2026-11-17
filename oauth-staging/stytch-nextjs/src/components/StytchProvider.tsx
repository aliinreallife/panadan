'use client';

import { useState, type ReactNode } from 'react';
import { StytchB2BProvider } from '@stytch/nextjs/b2b';
import { createStytchB2BUIClient } from '@stytch/nextjs/b2b/ui';
import { isValidStytchTestPublicToken } from '@/lib/stytchPublicToken';

export function StytchProvider({ children }: { children: ReactNode }) {
  const [client] = useState(() => {
    const publicToken = process.env.NEXT_PUBLIC_STYTCH_PUBLIC_TOKEN || '';
    // Never fall back to Live, or fabricate a working authentication session.
    if (!isValidStytchTestPublicToken(publicToken)) return null;
    return createStytchB2BUIClient(publicToken);
  });

  if (!client) {
    return (
      <div className="setup-message" role="alert">
        <h1>Stytch Test configuration required</h1>
        <p>Set NEXT_PUBLIC_STYTCH_PUBLIC_TOKEN in .env.local to the complete Public Token copied from Stytch Test → Project Overview → API Keys.</p>
        <p>It must have the form public-token-test- followed by a UUID. Replace the REPLACE_ME placeholder, then restart npm run dev.</p>
        <p>Do not use the Stytch Secret Key or a Live environment token.</p>
      </div>
    );
  }
  return <StytchB2BProvider stytch={client}>{children}</StytchB2BProvider>;
}
