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
      <section role="alert" className="content">
        <h1>Live authentication is not configured</h1>
        <p>This dedicated Live authorization application requires its own
        Stytch <strong>Production Public Token</strong>.</p>
        <p>No customer data can be authorized until configuration is complete.</p>
      </section>
    );
  }
  return <StytchB2BProvider stytch={client}>{children}</StytchB2BProvider>;
}
