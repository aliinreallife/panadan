'use client';
import { useEffect, useRef } from 'react';
import { useStytchMemberSession } from '@stytch/nextjs/b2b';
import { captureAuthorizationSearch, readAuthorizationReturnTo } from '@/lib/oauthRequest';

/**
 * Stytch's OTP callback can independently navigate to the application root.
 * If this happens after login, resume the validated, short-lived OAuth request
 * rather than displaying the landing page and abandoning ChatGPT's flow.
 */
export function ResumePendingAuthorization() {
  const { session, isInitialized } = useStytchMemberSession();
  const redirectStarted = useRef(false);

  useEffect(() => {
    if (redirectStarted.current) return;
    // Also recover a misrouted authorization request delivered to '/'.
    // Never turn an arbitrary query string into a redirect destination.
    const incoming = captureAuthorizationSearch(
      window.location.search, window.sessionStorage, window.localStorage,
    );
    if (incoming) {
      redirectStarted.current = true;
      window.location.replace(incoming);
      return;
    }
    if (!isInitialized || !session) return;
    const destination = readAuthorizationReturnTo(
      window.sessionStorage, window.localStorage,
    );
    if (destination === '/') return;
    redirectStarted.current = true;
    window.location.replace(destination);
  }, [isInitialized, session]);

  return null;
}
