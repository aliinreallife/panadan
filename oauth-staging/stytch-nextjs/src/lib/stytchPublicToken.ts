/** Confirm basic Test public-token syntax before handing it to the Stytch SDK. */
export function isValidStytchTestPublicToken(value: string): boolean {
  return /^public-token-test-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(value);
}
