import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/browser',
  fullyParallel: true,
  retries: 1,
  timeout: 30_000,
  use: {
    baseURL: 'http://127.0.0.1:3000',
    trace: 'retain-on-failure',
    ...devices['Desktop Chrome'],
  },
  webServer: {
    command: 'npm run dev',
    port: 3000,
    timeout: 120_000,
    reuseExistingServer: false,
    env: {
      NEXT_PUBLIC_STYTCH_PUBLIC_TOKEN: process.env.NEXT_PUBLIC_STYTCH_PUBLIC_TOKEN
        || 'public-token-test-123e4567-e89b-12d3-a456-426614174000',
    },
  },
});
