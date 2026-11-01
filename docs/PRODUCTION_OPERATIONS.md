# Panadan production operations — verified 2026-11-01

> **Status:** Live HTTPS dashboard is operational. This document records observed results from a controlled VPS deployment, not claims that the full disaster-recovery or OAuth rollout is finished. All paths below are operator-maintained private-host paths; never commit their contents if they contain secrets.

## Deployment topology

```text
Internet HTTPS:443
  Plane's existing Caddy reverse proxy (plane-app-proxy-1)
    - plane.panafor.com -> original Plane services (including /intake.html)
    - dan.panafor.com -> Nginx gateway on panadan-edge (internal network)
      panadan-edge-gateway-gateway-1
        -> panadan-ingress (internal network)
          -> panadan-vpn-1, alias panadan-upstream
            -> panadan-web-1, network namespace shared with VPN
            -> Odoo PostgreSQL 192.168.3.9 via tun0, SELECT-only app queries
```

- Plane continues owning ports 80/443. Caddy `/data` and `/config` are the original persistent volumes; the production Caddyfile is a read-only bind mount. The proxy is managed by its original Compose project **plus a local override**; never recreate Plane Web to apply Panadan networking.
- `panadan-edge` is an internal network (Caddy `172.24.0.2`, gateway `172.24.0.3` as verified). Caddy also retains its original `plane-app_default` network. The gateway has **no host-published ports**. The separate private `panadan-ingress` links gateway to Panadan VPN's shared network namespace.
- Panadan VPN route to source PostgreSQL was checked as `192.168.3.9 via 10.8.0.1 dev tun0`. The auth and permissions store is a **separate local SQLite** persistent Docker volume, not the reporting PostgreSQL.
- Production uses prebuilt pinned local web image `panadan-web:cac4b36`. Do not assume registry `:main` tags or a fresh host have matching binaries.

## Verified deployment and smoke tests (2026-11-01)

| Check | Observed |
| --- | --- |
| `https://dan.panafor.com/healthz` | HTTP 200, valid TLS |
| `https://dan.panafor.com/login` | HTTP 200, valid TLS |
| Real dashboard login and call data | Operator confirmed works |
| `PANADAN_COOKIE_SECURE` | `true` |
| `PANADAN_PUBLIC_ORIGIN` | `https://dan.panafor.com` |
| `https://plane.panafor.com/` | HTTP 200 after proxy recreation |
| `https://plane.panafor.com/intake.html` | HTTP 200 after proxy recreation |
| VPN | Docker health `healthy`; source route via `tun0` |
| Caddy TLS | Let's Encrypt issued valid cert for dan; /data and /config persisted |
| Caddy -> gateway -> Panadan | /healthz returned JSON `{"status":"ok"}` |
| Rate limiting | Synthetic clients: first hit HTTP 429 after 7 malformed logins, second distinct Docker client received 422, even with forged forwarding headers; **does not prove all real-world NAT/IP scenarios** |

Caddy initially served a temporary HTTPS staging 503 page until the domain certificate was issued successfully. The final reload directed Caddy to the private gateway. A controlled `docker compose up -d --no-deps --no-build --pull never proxy` with the saved Plane override recreated **only** `plane-app-proxy-1` and preserved both Plane and Panadan endpoints. The original Caddyfile was backed up separately before cutover.

## Current private Compose files (on VPS; migration into Git is unfinished)

```text
/home/panafor/panadan/
  compose.prod.yaml
  .env.app                       # secret; do not commit
  .env.db                        # secret; do not commit
  vpn/client.ovpn                # secret; do not commit
  data/ingress/compose.panadan.yaml
  data/ingress/compose.web.release.yaml
  data/ingress/compose.web.https.yaml
  data/ingress/compose.gateway.yaml
  data/ingress/compose.plane.yaml
  data/ingress/Caddyfile
  data/ingress/nginx.conf
  data/ingress/rollback/Caddyfile.live
  data/auth-backups/             # sensitive; never commit
  prodctl.sh                     # currently VPS-local
/home/panafor/plane-selfhost/plane-app/
  docker-compose.yaml
  plane.env
```

Use the existing VPS-local `sudo ./prodctl.sh check` and `sudo ./prodctl.sh status` to inspect safely. The `web` and `proxy` subcommands **recreate** containers and must not be used as health checks. The in-repository `./panadan.sh up/down` does **not** replace the VPS-local production controller. As of merged PRs #67/#73, it **refuses bare up/down when hardened private HTTPS overlay files are detected**; that guard is not a substitute for the correct production Compose overlays and an approved controller. **Do not use bare commands to update this deployment.** Keep #56 open until a disposable fresh-host rehearsal proves the full topology. See #56 for migrating the configuration to reproducible, reviewed, secret-free files.

Safe non-mutating checks:

```bash
curl -fsS https://dan.panafor.com/healthz
curl -sS -o /dev/null -w 'Plane: %{http_code}\n' https://plane.panafor.com/
curl -sS -o /dev/null -w 'Intake: %{http_code}\n' https://plane.panafor.com/intake.html
sudo docker inspect panadan-vpn-1 --format '{{.State.Health.Status}}'
cd /home/panafor/panadan && sudo ./prodctl.sh check && sudo ./prodctl.sh status
```

### Rollback boundaries

- For a **Panadan routing issue** while Caddy is still running, reload the tested HTTPS staging Caddyfile (if it still exists inside the container) or a verified original file. This changes live routes but does **not** require rebuilding Plane Web.
- For a **Plane proxy recreate failure**, use the original Plane Compose with `--env-file plane.env`, `--no-deps --no-build --pull never proxy` as a *last-resort* controlled rollback. It restores original Plane-only routes and temporarily removes Panadan. Verify `/intake.html` and Plane afterward. Expect a brief public-proxy interruption.
- Never run broad `docker compose down`, `prune`, host reboot or system upgrades on the shared server as part of Panadan rollback.
- Always check Caddy TLS `/data`, `/config`, current in-image/override Caddyfile, and source `intake.html` backup before proxy or Plane Web updates. Plane's `intake.html` currently resides in a container filesystem and is **not** made persistent merely by persisting Caddy: #62.

## SQLite auth backup evidence and limitations

- SQLite Online Backup API produced `data/auth-backups/auth-20261101T114330Z.sqlite` (**86,016 bytes**). `PRAGMA integrity_check` returned `ok`; production service did not stop.
- The backup was encrypted with `age` public-key encryption, copied over SSH to the operator's WSL machine as `auth-20261101T114330Z.sqlite.age`, and successfully decrypted to a checksum stream. The operator has **not yet shown an equality comparison with the original VPS plaintext SHA-256**, so mark bitwise equality *pending*.
- This is a **manual off-VPS copy**, not a scheduled, monitored, second independent off-site store. An in-memory restore or full alternate-host application recovery should be explicitly tested before claiming comprehensive recovery.
- Never commit account DB, plaintext backup, decryption private key, token records, OAuth credentials, VPN files or customer data. Private recovery material belongs in independent encrypted storage.
- Source Odoo PostgreSQL remains an external system and is **not** included in this account-backup snapshot. Full stack recovery requires VPN, ingress, images, secrets/keys, Caddy TLS handling, and tested restore procedures: #55 and #63.

## Independent Panadan PostgreSQL backup (not an auth cutover)

The operator independently age-encrypted and copied a Panadan-owned PG18
`pg_dump -Fc` to WSL. The decrypted stream's SHA-256 matched the original
VPS dump, and the disposable isolated PG18 restore passed: seven existing
`panadan_ingest` tables, zero registered sources, followed by an additive
`panadan_auth` schema and restricted-role rehearsal. This backup predates
production PostgreSQL auth data. It **does not** establish automated PG
backup, alerting, safe retention, off-site key escrow, SQLite account
restore, or a complete production recovery. See #55 and #63.

Merged PR #73 makes PostgreSQL auth infrastructure preparation opt-in via
`sudo bash ./panadan.sh owned-pg plan` (read-only preflight), `apply`
(explicit acknowledgments and real infrastructure changes) and `verify`.
No VPS application, runtime authentication migration or new production
network attachment has been performed by this repository merge. Read
[the one-command operator guide](ONE_COMMAND_OWNED_PG_SETUP.md) before any
future authorized apply.

## Plane custom intake preservation gate (#62)

The publicly accessible `https://plane.panafor.com/intake.html` is currently
**not persistent** across a Plane Web container recreation: its original HTML
lives inside that container, outside the checked-in Panadan repository.
The presence of a Caddy `/data` or `/config` volume does not protect it.

A read-only inspection command is available:

```bash
# Inspect only the live public HTTPS response (prints SHA-256, not HTML).
bash tools/check-plane-intake.sh fingerprint

# Compare the exact public HTML against a trusted, independently saved
# copy of the ORIGINAL intake.html, before and after a future controlled upgrade.
bash tools/check-plane-intake.sh verify /secure/path/original-intake.html
```

The verify mode **fails** on redirects, unavailable HTTPS, empty responses, or
any byte change. It does not read, modify, or restart Plane, proxy, or Docker.
A passing hash checks only the HTML bytes: it does not verify CSS/JS dependencies,
proxy configuration or form submission behavior. A **fingerprint is not a
backup**. First preserve the authoritative original file and its dependencies
through an approved operator backup procedure, and record its hash outside
the running container. Do not save private tokens, user data or secrets in Git.

Before ANY future Plane Web rebuild, review the backed-up file and select a
persistent delivery path (a read-only bind mount or a dedicated Caddy static
path), verify the existing Plane routing contract and rehearse rollback on
a disposable environment. Do not infer an in-container original path or mount
configuration without inspecting the live deployment. No rebuild, persistence
change or production deployment has been performed by this check; #62 remains
open until a verified post-rebuild test passes.

## MCP and OAuth: current limitations

The public HTTPS dashboard is live, **not** equivalent to completed ChatGPT/Claude OAuth. The server currently defaults to `PANADAN_MCP_AUTH_MODE=legacy`; legacy credentials are admin-issued revocable `mcp:read` bearer tokens. In that mode, OAuth protected-resource metadata is intentionally absent. The MCP mount is `/mcp/`.

Panadan already contains a resource-server-only OAuth mode with RSA/JWKS access-JWT verification, protected-resource metadata and local issuer+`sub` identity bindings; **it does not provide authorization-code login, consent, PKCE, client registration or refresh issuance**. Those require a compatible *external authorization server*. User-observed ChatGPT error (2026-11-01): `Couldn't discover OAuth settings. Check the server URL or enter settings manually`. Do not weaken security or blindly switch modes to make discovery succeed.

Track the remaining steps through #57 (IdP), #58 (discovery/proxy), #23 (live authorization and transcript matrix), #59 (metadata and profile), #64 (client interoperability). See [MCP clients](MCP_CLIENTS.md).

See [the disaster-recovery sequence](DISASTER_RECOVERY.md) for an ordered, **not yet drill-proven** off-host restore, secret escrow checklist, shared Plane rollback boundaries, and go/no-go tests. The source-controlled runbook does not replace a real restore exercise (#63).

## Prioritized remaining work

1. **P0:** #55 automatic age-encrypted off-site backups, checksums, restore drill, alarms; #56 reproducible production deployment and safe entrypoints.
2. **P0:** #57 choose/configure OAuth authorization server; #58 implement/verify discoverability and end-to-end security at the public MCP endpoint.
3. **P1:** #23 + #64 ChatGPT/Claude/Codex live client tests, token scopes and transcript authorization; #59 scoped tool metadata / verified profile.
4. **P1:** #60 secure reliable Odoo `updated_at` marker (including joined edits); then #61 serial initial backfill + new rows + changed-old-row pilot **without** copying unapproved fields or switching reads.
5. **P1:** #62 protect Plane's `intake.html`, #63 complete disaster-recovery runbook and monitoring.
6. **Existing blockers:** #22 inherited source reporting schema CREATE grant requires DBA sign-off, #21 scoped operator-ID RBAC, #20 unresolved source column semantics, #24 live RTL QA, #44 CI infrastructure failures.

**Do not claim completed:** OAuth discovery, API/MCP remote client verification, automated off-site backup, full restore, source server least-privilege account, or live source-update synchronization.
