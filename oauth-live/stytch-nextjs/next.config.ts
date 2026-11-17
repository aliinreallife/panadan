import type { NextConfig } from 'next';
import path from 'node:path';

const config: NextConfig = {
  reactStrictMode: false,
  outputFileTracingRoot: path.resolve(__dirname),
  logging: { incomingRequests: false },
  async headers() {
    return [{
      source: '/oauth/:path*',
      headers: [
        { key: 'Referrer-Policy', value: 'no-referrer' },
        { key: 'Cache-Control', value: 'no-store' },
        { key: 'X-Content-Type-Options', value: 'nosniff' },
      ],
    }, {
      source: '/login',
      headers: [
        { key: 'Referrer-Policy', value: 'no-referrer' },
        { key: 'Cache-Control', value: 'no-store' },
      ],
    }];
  },
};
export default config;
