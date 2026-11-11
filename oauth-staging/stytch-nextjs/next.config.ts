import type { NextConfig } from 'next';
import path from 'node:path';

const config: NextConfig = {
  // The Stytch authorization component can initiate an authorization request
  // on mount. Avoid React's development-only StrictMode double mounting.
  reactStrictMode: false,
  // Prevent a parent home-directory lockfile from becoming this app's root.
  outputFileTracingRoot: path.resolve(__dirname),
};

export default config;
