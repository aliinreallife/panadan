export default function StartPage() {
  return (
    <section className="content">
      <div className="eyebrow">Panadan Connected Apps</div>
      <h1>Secure authorization for Panadan</h1>
      <p>This page handles Stytch Live sign-in and OAuth consent for authorized
      Panadan MCP clients.</p>
      <p>Start a connection from your supported MCP client to receive a real
      authorization request and review the requested permissions.</p>
      <p className="muted">Signing in here alone does not approve an AI client
      or grant access to Panadan reports.</p>
    </section>
  );
}
