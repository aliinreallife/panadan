# In-flow MCP permission consent — design and release gate

Status: proposed authentication architecture; existing production native AuthKit stays active. The connected-apps dashboard has its own UI improvements, which do not implement this flow.

## User experience
ChatGPT Connect → WorkOS login (skip with valid session) → Panadan permission review → approve selected fields or deny → OAuth returns to the originating client. The dashboard remains for later edits and revocation. Never require users to paste a client ID or manually return to ChatGPT during initial consent.

Use a dedicated RTL page with the authenticated app identity, simple scope explanations, optional detailed column controls, and explicit approval/denial. No data access is granted by login alone. Sensitive transcript access is off by default, read-only, and accurately describes best-effort redaction.

## Provider constraint and staged implementation
Native WorkOS Connect currently returns to the OAuth client after its own consent, without a documented arbitrary Panadan consent-page hook. Panadan's local per-client approval is currently intentionally separate. WorkOS Standalone Connect documents external_auth_id and dynamic enum user_consent_options whose selections become signed access-token claims. The external login URI applies across an environment; enabling it on the existing environment previously broke hosted browser sign-in. The provider also issues external IDs as subjects in Standalone mode. Do not re-enable it on the production environment as a shortcut.

Investigate in an isolated WorkOS environment and synthetic Panadan instance first. Validate a supported upstream login approach that cannot recurse through the external-login URI. Prove provider continuation, client identity, exact audience, subject mapping, consent claims, denial and refresh behavior. Determine whether a selected local consent receipt can be carried by the supported enum claim and bound to the exact signed client and OAuth transaction; do not trust a client_id or return URL provided by the browser. If WorkOS cannot support these requirements, use a standards-compliant authorization server with WorkOS as upstream identity provider, rather than inventing an OAuth redirect or issuing tokens from ad hoc code.

## Security invariants
- Bind pending approval to a short-lived, single-use server-side OAuth transaction and verified browser identity; validate CSRF, state, PKCE, issuer, client and exact registered redirect.
- Never create an account or expand grants based on a model request or unverified client ID. Require deliberate user consent; intersect selection with current user and client policy.
- Do not expose data until the approval is completed and associated with the verified signed client. Missing/unknown claims and denied or expired transactions fail closed.
- A reconnect must not restore a revoked client or overwrite narrowed grants silently. No automatic grant of transcript access.
- Keep provider tokens and authorization codes out of logs. Never redirect to arbitrary user-controlled URLs.
- Test both positive and negative paths, replay, CSRF, cross-client swaps, cross-user swaps, token refresh, revocation, session expiration and cancel. Test actual browser return into ChatGPT and immediate synthetic read-only tool access. Existing production connection and current approvals must remain intact until a staged cutover is proven.

References: https://workos.com/docs/authkit/connect/standalone ; https://workos.com/docs/reference/workos-connect/standalone ; https://workos.com/docs/authkit/connect/token-claims
