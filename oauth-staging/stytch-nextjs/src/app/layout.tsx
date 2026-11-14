import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import { StytchProvider } from '@/components/StytchProvider';
import './globals.css';

export const metadata: Metadata = {
  title: 'Panadan OAuth Staging',
  description: 'Stytch B2B Test-only OAuth authorization and consent',
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="shell">
          <header className="topbar">
            <div className="mark">P</div>
            <div><strong>Panadan</strong><small>OAuth Test Environment</small></div>
            <span className="environment">STAGING ONLY</span>
          </header>
          <main className="panel">
            <StytchProvider>{children}</StytchProvider>
          </main>
          <footer>Independent Stytch authorization test • Production reporting stays unchanged</footer>
        </div>
      </body>
    </html>
  );
}
