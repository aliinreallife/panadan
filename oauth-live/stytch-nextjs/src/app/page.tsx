export default function StartPage() {
  return (
    <section className="content">
      <div className="hero-symbol" aria-hidden="true">✓</div>
      <p className="eyebrow">PANADAN CONNECTED APPS</p>
      <h1>Connect Panadan to your AI assistant.</h1>
      <p className="lede">
        A secure way to work with the reports you are already allowed to access.
        You stay in control of the connection.
      </p>
      <div className="steps-heading">How it works</div>
      <ol className="steps" aria-label="Connection steps">
        <li>
          <span className="step-number">1</span>
          <div><strong>Start in ChatGPT</strong><span>Open Panadan in ChatGPT and choose Connect.</span></div>
        </li>
        <li>
          <span className="step-number">2</span>
          <div><strong>Confirm your identity</strong><span>Sign in with your approved work email.</span></div>
        </li>
        <li>
          <span className="step-number">3</span>
          <div><strong>Approve access</strong><span>Review permissions. You'll return to ChatGPT automatically.</span></div>
        </li>
      </ol>
      <div className="info-note">
        <span className="note-icon" aria-hidden="true">i</span>
        <p>Already here? Start the connection in ChatGPT first. Opening this page alone does not connect your account.</p>
      </div>
      <p className="small-print">Signing in never grants access to reports by itself. Your existing Panadan permissions still apply.</p>
    </section>
  );
}
