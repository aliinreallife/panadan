'use client';
import { useEffect } from 'react';
import { StytchB2B, useStytchMemberSession } from '@stytch/nextjs/b2b';
import { AuthFlowType, B2BProducts, StytchEventType } from '@stytch/vanilla-js/b2b';
import { RETURN_TO_KEY, safeReturnTo } from '@/lib/oauthRequest';

const config = {
  authFlowType: AuthFlowType.Discovery,
  products: [B2BProducts.emailOtp],
  sessionOptions: { sessionDurationMinutes: 60 },
};

function finishLogin() {
  const destination = safeReturnTo(sessionStorage.getItem(RETURN_TO_KEY));
  sessionStorage.removeItem(RETURN_TO_KEY);
  window.location.replace(destination);
}

export default function LoginPage() {
  const { session, isInitialized } = useStytchMemberSession();
  useEffect(() => {
    if (isInitialized && session) finishLogin();
  }, [isInitialized, session]);

  return (
    <section className="content">
      <div className="eyebrow">Stytch Live organization sign-in</div>
      <h1>Sign in to Panadan</h1>
      <p>Use an approved Stytch Live organization member account.</p>
      <div className="stytch-widget">
        <StytchB2B config={config} callbacks={{
          onEvent: (event) => {
            if (event.type === StytchEventType.AuthenticateFlowComplete) finishLogin();
          },
        }} />
      </div>
      <p className="muted">This login does not replace your existing Panadan dashboard account.</p>
    </section>
  );
}
