'use client';
import { useEffect, useRef } from 'react';
import { useStytchMemberSession } from '@stytch/nextjs/b2b';
import { readAuthorizationReturnTo } from '@/lib/oauthRequest';

/**
 * Stytch's OTP callback can independently navigate to the application root.
 * If this happens after login, resume the validated, short-lived OAuth request
 * rather than displaying the landing page and abandoning ChatGPT's flow.
 */
export function ResumePendingAuthorization() {
  const { session, isInitialized } = useStytchMemberSession();
  const redirectStarted = useRef(false);

  useEffect(() => {
    if (!isInitialized || !session || redirectStarted.current) return;
    const destination = readAuthorizationReturnTo(
      window.sessionStorage, window.localStorage,
    );
    if (destination === '/') return;
    redirectStarted.current = true;
    window.location.replace(destination);
  }, [isInitialized, session]);

  return null;
}
