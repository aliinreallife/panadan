import type { NextConfig } from 'next';

const config: NextConfig = {
  // The Stytch authorization component can initiate an authorization request
  // on mount. Avoid React's development-only StrictMode double mounting.
  reactStrictMode: false,
};

export default config;
