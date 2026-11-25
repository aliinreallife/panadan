# Native WorkOS AuthKit production cutover

This supersedes the standalone bridge runbook for the native single-admin release. The current image must remain running until the candidate is built, CI passes and the read-only provider preflight succeeds. Never deploy a floating tag. No customer data is required for any acceptance test.

## Before release

- Confirm the candidate PR's exact head SHA, green CI, and candidate GHCR publish. The candidate workflow publishes only, never deploys.
- Confirm the WorkOS Production environment, exact verified administrator email, immutable user ID, default AuthKit client ID, email-code login enabled, public signup disabled, exact HTTPS callback registered, CIMD enabled and the canonical MCP resource. Do not assume a WorkOS dashboard-team administrator is also an AuthKit user.
- Keep the WorkOS API key already installed on the VPS; never paste it or a complete Compose config into logs.
- Use the current web container's own network and SQLite authority to check the provider and identity migration. Run from the checkout holding this file:

```bash
sudo docker exec -i \
  -e PANADAN_PREFLIGHT_UID=1 \
  -e PANADAN_PREFLIGHT_SUBJECT=YOUR_VERIFIED_WORKOS_USER_ID \
  -e PANADAN_PREFLIGHT_EMAIL=YOUR_VERIFIED_ADMIN_EMAIL \
  panadan-web-1 python - < tools/preflight-native-authkit.py
```

- A failed check stops the cutover. No passwords or tokens are printed. Record the old pinned image and verify it exists locally. Preserve the current operator configuration securely if you want to restore the old standalone mode. A no-fresh-backup acknowledgment is not a tested restore.
- Run the candidate's synthetic HTTP smoke with a disposable SQLite store, no published ports, no production mounts, no network, and a fake API key. Create the synthetic admin in that database before native startup. Native mode intentionally does not bootstrap an administrator from an empty database.
- Use the checked-in host controller and validator from the reviewed candidate commit; do not replace unrelated deployment files.

## Cutover configuration

Keep the existing canonical issuer/JWKS, exact resource and openid scope. Set these additional environment keys without printing the API key or full environment:

```ini
PANADAN_WEB_AUTH_MODE=authkit
PANADAN_WORKOS_STANDALONE_ENABLED=false
WORKOS_CLIENT_ID=YOUR_PRODUCTION_AUTHKIT_CLIENT_ID
PANADAN_AUTHKIT_ADMIN_EMAIL=YOUR_VERIFIED_ADMIN_EMAIL
PANADAN_AUTHKIT_ADMIN_SUBJECT=YOUR_VERIFIED_WORKOS_USER_ID
PANADAN_AUTHKIT_ADMIN_UID=1
```

SQLite remains authoritative for local permissions. The existing administrator is mapped by a pinned native user ID. Other users are deactivated, not deleted; their REST tokens and OAuth access become ineffective. The existing admin's REST tokens are intentionally preserved. Any previous standalone MCP client grants are cleared when the subject changes. Native and old local browser sessions use different tables and cookies. Old local password login cannot be used while native mode is active.

Set the WorkOS Connect external sign-in URI to blank at cutover (native hosted AuthKit, not Standalone Connect). Keep the registered browser redirect URI and resource. The two settings are distinct. WorkOS native Connect tokens must use the actual user ID as sub; do not accept old external IDs as an alternative in native mode.

Select the exact reviewed image in the private release overlay, then:

```bash
sudo bash tools/prodctl-production.sh check --allow-workos-oauth
sudo bash tools/prodctl-production.sh deploy-web --apply --expect-image "$IMG" --ack-restored-backup --allow-workos-oauth
```

If the operator explicitly chose to skip the fresh verified backup, use --ack-no-fresh-backup instead of --ack-restored-backup. Never assert a verified restore that did not occur.

## Acceptance (interactive)

1. Health and existing Plane/VPN smoke pass; unauthenticated REST and MCP remain 401.
2. Browser /login displays only WorkOS sign-in. /auth/workos/start returns an HTTPS authorization redirect and secure flow cookie; don't print the Location query string or cookie values.
3. Sign in as the pinned administrator via real WorkOS email code. Callback must create the native session; dashboard loads; logout invalidates the local session; subsequent sign-in works. Wrong account cannot access reports.
4. Connect ChatGPT using the canonical MCP URL, OAuth discovery and CIMD. Approve only the desired read-only capabilities/fields in /dashboard/mcp-apps. Verify tools/list and a synthetic or explicitly authorized non-sensitive tool call. Never dump production customer records for smoke.
5. Verify wrong/missing/expired token, unapproved client and old password POST fail closed. Keep the previous image available.

## Recovery

If browser access fails, do not retry container creation endlessly or alter VPN, database, ingress or Plane. Select the previous locally available pinned image and set PANADAN_WEB_AUTH_MODE=local, PANADAN_MCP_AUTH_MODE=legacy, PANADAN_WORKOS_STANDALONE_ENABLED=false. Use the guarded rollback-web command with the truthful backup acknowledgment. The old local administrator's password and original sessions schema remain compatible. WorkOS can remain on hosted sign-in; legacy mode does not depend on it. Previously deactivated other accounts and cleared per-client grants are not automatically restored. The original local administrator can recover the browser dashboard, but standalone OAuth is not automatically restored by image rollback. Restore that mode only after explicit subject and provider review.

Application access logs redact callback query strings. Inspect reverse-proxy access logging separately without printing any recorded OAuth code or cookie. A verified provider response and real interactive callback remain mandatory; passing CI cannot prove either.
