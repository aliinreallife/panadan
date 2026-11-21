'use client';
import { useCallback, useEffect, useRef } from 'react';
import { StytchB2B, useStytchMemberSession } from '@stytch/nextjs/b2b';
import { AuthFlowType, B2BProducts, StytchEventType } from '@stytch/vanilla-js/b2b';
import { consumeAuthorizationReturnTo } from '@/lib/oauthRequest';

const config = {
  authFlowType: AuthFlowType.Discovery,
  products: [B2BProducts.emailOtp],
  sessionOptions: { sessionDurationMinutes: 60 },
};

export default function LoginPage() {
  const { session, isInitialized } = useStytchMemberSession();
  // Stytch may emit AuthenticateFlowComplete and update session in the
  // same render. Only ONE of those events may consume the OAuth return URL;
  // the previous double redirect sent authenticated users to "/" instead.
  const redirectStarted = useRef(false);
  const finishLogin = useCallback(() => {
    if (redirectStarted.current) return;
    redirectStarted.current = true;
    const destination = consumeAuthorizationReturnTo(
      window.sessionStorage, window.localStorage,
    );
    window.location.replace(destination);
  }, []);

  useEffect(() => {
    if (isInitialized && session) finishLogin();
  }, [isInitialized, session, finishLogin]);

  return (
    <section className="content">
      <div className="flow-progress" aria-label="Step 1 of 2">
        <span className="current">1. Sign in</span><span className="flow-dot" />
        <span>2. Approve access</span>
      </div>
      <div className="eyebrow">SECURE ACCOUNT CONNECTION</div>
      <h1>Sign in with your work email.</h1>
      <p className="subhead">Enter the email your Panadan administrator approved. We'll send you a one-time code.</p>
      <div className="stytch-widget">
        <StytchB2B config={config} callbacks={{
          onEvent: (event) => {
            if (event.type === StytchEventType.AuthenticateFlowComplete) finishLogin();
          },
        }} />
      </div>
      <p className="session-note">After sign-in, you'll review access and return to ChatGPT automatically.</p>
    </section>
  );
}
