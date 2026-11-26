# Opt-in WorkOS multi-user onboarding

This release is additive and defaults to the existing pinned-administrator login. Do not enable WorkOS public signup until the new image has passed the full CI suite and an isolated browser test. The current production issuer, API key, client ID, administrator subject, UID, email, existing MCP grants and OAuth callback remain unchanged.

## Authorization model

- Verified WorkOS subject is the identity; never match by email or inherit a local account. The pinned administrator requires the exact existing subject and verified email.
- First verified sign-in creates an active native identity with explicit empty capabilities, empty reporting fields and empty panel permissions. No reporting or MCP access is granted merely by signing in.
- New accounts see the Persian access-pending page and can submit an optional access-request note. The owner sees the request in the user directory and can filter pending accounts. No email notification is sent.
- Only the existing pinned owner can edit native accounts; owner grants are immutable in this editor. User/token/OAuth security management remains owner-only. System status, activity metadata, API documentation, connection guide and operator assignment management are individually delegable. Operator management additionally requires call access and the operator field.
- Reporting capabilities and individual fields are checked independently. MCP app grants remain a subset of the current user grants. Saving native access revokes current sessions, tokens and app grants while preserving the identity. The member signs in again and reapproves any desired apps.
- Historical local accounts remain disabled. Do not reactivate or link them by email. Native identities cannot be manually rebound via the OAuth UI.
- No inline OAuth consent callback has been added; the existing manual app approval flow remains.

## Release gate

1. Verify exact head CI and image publication; keep previous image and a freshly verified auth database backup. Use the guarded web-only release controller. Deploy with multi-user mode still disabled.
2. Verify owner login, current ChatGPT access and unchanged reporting page. Test the new mode with a disposable SQLite database and synthetic provider identity; test CSRF, rejected privilege escalation, disabled accounts and forged field selections.
3. Only after checks succeed, set PANADAN_AUTHKIT_MULTI_USER=true in the private application environment. The production validator requires native AuthKit mode. Recreate only the web service via the guarded controller, retaining issuer and all existing WorkOS settings.
4. Confirm the owner can still sign in. Then explicitly enable WorkOS AuthKit signups (email verification must remain required). Test with a separate verified test email: no data, no panels, no MCP; request access; owner grants a small subset; test re-login and revoke. Test an existing native member survives a web restart with multi-user mode enabled.
5. If unsafe or failing, disable WorkOS signups first. Disable multi-user flag and return to the pinned-owner mode. This intentionally disables non-owner local accounts; do not expect automatic restoration of their active statuses on re-enabling. Restore only from independently reviewed recovery material if necessary.

The WorkOS environment signup setting is NOT changed by this commit. Do not use production customer data in tests.
