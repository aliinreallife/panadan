/** Reject any Test public token or missing Live SDK configuration. */
export function isValidLivePublicToken(value: string): boolean {
  return /^public-token-live-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(value);
}
