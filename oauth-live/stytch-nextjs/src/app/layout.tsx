import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import { StytchProvider } from '@/components/StytchProvider';
import './globals.css';

export const metadata: Metadata = {
  title: 'Connect Panadan securely',
  description: 'Securely connect your approved Panadan account to your AI assistant',
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="shell">
          <header className="topbar">
            <div className="brand-lockup">
              <div className="mark" aria-hidden="true">P</div>
              <div className="brand-text">
                <strong>Panadan</strong>
                <small>Secure connection</small>
              </div>
            </div>
            <span className="security-label"><span className="security-dot" /> Protected</span>
          </header>
          <main className="panel">
            <StytchProvider>{children}</StytchProvider>
          </main>
          <footer>
            <span aria-hidden="true">✦</span> Your data stays protected by your Panadan permissions.
          </footer>
        </div>
      </body>
    </html>
  );
}
