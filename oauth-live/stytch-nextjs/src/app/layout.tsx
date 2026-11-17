import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import { StytchProvider } from '@/components/StytchProvider';
import './globals.css';

export const metadata: Metadata = {
  title: 'Panadan | Secure authorization',
  description: 'Authorize Panadan MCP clients through Stytch Live',
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="shell">
          <header className="topbar">
            <div className="mark" aria-hidden="true">P</div>
            <div><strong>Panadan</strong><small>Secure authorization</small></div>
          </header>
          <main className="panel">
            <StytchProvider>{children}</StytchProvider>
          </main>
          <footer>Only Stytch Live authorizes OAuth clients. Panadan enforces reporting permissions separately.</footer>
        </div>
      </body>
    </html>
  );
}
