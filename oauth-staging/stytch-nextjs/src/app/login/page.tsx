'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { StytchB2B, useStytchMemberSession } from '@stytch/nextjs/b2b';
import { AuthFlowType, B2BProducts, StytchEventType } from '@stytch/vanilla-js/b2b';
import { RETURN_TO_KEY, safeReturnTo } from '@/lib/flow';

const config = {
  authFlowType: AuthFlowType.Discovery,
  products: [B2BProducts.emailOtp],
  sessionOptions: { sessionDurationMinutes: 60 },
};

function finishLogin() {
  const target = safeReturnTo(sessionStorage.getItem(RETURN_TO_KEY));
  sessionStorage.removeItem(RETURN_TO_KEY);
  window.location.replace(target);
}

export default function LoginPage() {
  const { session, isInitialized } = useStytchMemberSession();

  useEffect(() => {
    if (isInitialized && session) finishLogin();
  }, [isInitialized, session]);

  return (
    <section className="content">
      <div className="eyebrow">Test-member authentication</div>
      <h1>Sign in to Panadan Test</h1>
      <p>Use the email of an existing member of your Stytch Test organization.</p>
      <div className="stytch-widget">
        <StytchB2B
          config={config}
          callbacks={{
            onEvent: (event) => {
              if (event.type === StytchEventType.AuthenticateFlowComplete) finishLogin();
            },
          }}
        />
      </div>
      <p className="muted">Only your Stytch Test project is used. <Link href="/">Back to start</Link></p>
    </section>
  );
}
