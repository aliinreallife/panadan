import Link from 'next/link';

export default function HomePage() {
  return (
    <section className="content">
      <div className="eyebrow">Connected Apps / Test</div>
      <h1>Secure authorization for Panadan</h1>
      <p>This isolated application handles Stytch B2B test-member authentication and OAuth consent.</p>
      <p>Start an actual authorization request from a supported MCP client to see the consent screen.</p>
      <div className="actions"><Link className="primary" href="/login">Sign in with Stytch Test</Link></div>
      <p className="muted">No customer data, Panadan production database or Legacy MCP tokens are used here.</p>
    </section>
  );
}
