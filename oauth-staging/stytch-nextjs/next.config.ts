import type { NextConfig } from 'next';
import path from 'node:path';

const config: NextConfig = {
  reactStrictMode: false,
  outputFileTracingRoot: path.resolve(__dirname),
  turbopack: { root: path.resolve(__dirname) },
  // OAuth authorization codes arrive in callback query strings. Do not
  // print those URLs in the local Next.js development terminal.
  logging: { incomingRequests: false },
  async headers() {
    return [{
      source: '/oauth/test-callback',
      headers: [
        { key: 'Referrer-Policy', value: 'no-referrer' },
        { key: 'Cache-Control', value: 'no-store' },
      ],
    }];
  },
};

export default config;
