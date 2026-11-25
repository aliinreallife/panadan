# Stytch preservation / Git rollback references

As of **2026-11-21**, two standalone archived references preserve the Stytch **Live** source components. Original Test/Staging work and pull requests remain in GitHub unchanged.

| Piece | Preserved branch | Source branch |
| --- | --- | --- |
| Stytch Live Next.js login + consent UI (including signed-out request recovery) | `archive/stytch-live-auth-ui-20261121` | `fix/stytch-live-oauth-prelogin-capture-20261121` |
| Stytch Live synthetic MCP server, JWT validation tests and policy | `archive/stytch-live-mcp-synthetic-20261121` | `feat/stytch-live-mcp-synthetic-20261118` |

Original staging UI/auth branch: `feat/stytch-b2b-oauth-staging-20261111` and `feat/stytch-connected-apps-test-auth-ui-20261110`. Existing PRs: #104, #107, #109, #110. Their code remains available; no automatic merge was performed.

### Inspect a snapshot

```bash
git fetch origin
git switch --detach origin/archive/stytch-live-auth-ui-20261121
# Browse/test only. Return to development with:
git switch main
```

To inspect the synthetic server instead, switch to `origin/archive/stytch-live-mcp-synthetic-20261121`. The **two branches represent separate deployable components**, not one combined commit; selectively restore their files/PRs through review if reverting to Stytch. Do not force-merge one over the other.

**Important:** Git snapshots preserve source code only. Stytch Production/Test projects, connected app registration, secrets, Vercel env variables, DNS, cloud deployments, and live auth data are *not* snapshotted by these branches. Keep existing service settings and secret backups in their appropriate secure systems. Do not check credential exports into the repository.

The new vendor-neutral work starts on `feat/panadan-oauth-existing-login-20261121` (based on existing decision docs, not any Stytch code branch). No Stytch resources were deleted, and no production Panadan authentication settings were changed.
