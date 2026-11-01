# Dedicated network for Panadan's owned authentication PostgreSQL

> **Design and preflight only (2026-11-01).** These Docker Compose overlay files
> do not connect, restart, migrate or provision any live container by themselves.
> This is a separate change from draft PR #71, which adds the PostgreSQL auth
> schema/importer and staging PgStore. Existing SQLite remains the authority.

## Verified VPS facts

The operator ran `./panadan.sh platform-db check` and `roles-check`:

```text
pg_major=18
schema_present=true
tables=7
source_count=0
active_sources=0
Role privilege verification: PASS (writer restricted, reader safe-view-only).
```

The distinct network memberships were:

| Docker container | Existing networks |
| --- | --- |
| `panadan-platform-db-1` | `panadan-platform_default=172.22.0.2` |
| `panadan-vpn-1` | `panadan-ingress=172.23.0.2`, `panadan_default=172.21.0.2` |

The `panadan-web-1` container uses `network_mode: service:vpn`, so
the **VPN container**, not Web, is the correct network endpoint for reaching
Panadan-owned PostgreSQL. The Nginx gateway and Plane Caddy are intentionally
**not** members of the proposed database network.

The two verified roles are only `panadan_ingest_writer` and
`panadan_report_reader`; **they do not verify or provision an auth runtime
role**. As of these checks, the `panadan_auth` schema in draft PR #71
has **not been confirmed installed on the VPS**. Do not try to use the owner
credentials from `.env.platform` as web runtime credentials.

## Planned topology

```text
                 existing panadan_default + panadan-ingress
                 (VPN routes and HTTPS unchanged)
                      |
                panadan-vpn-1
                 + panadan-web-1 (network_mode: service:vpn)
                      |
              panadan-auth-db (new INTERNAL bridge)
                      |
             panadan-platform-db-1 (alias panadan-auth-postgres:5432)
                      |
              existing panadan-platform_default
                      |
             127.0.0.1:15433 on VPS (existing loopback)
```

Only the new network is shared across Compose projects. No source Odoo
`192.168.3.9` routes, data, roles or VPN configurations are changed.
Keep the PostgreSQL host port bound to `127.0.0.1`, not `0.0.0.0`.

Docker documentation supports externally managed cross-Compose networks and
using `internal: true` to limit direct external connectivity:
https://docs.docker.com/compose/how-tos/networking/ .

## Overlay files (reviewable, inert until explicitly applied)

- `deploy/compose.auth-network.platform.yaml`: preserves the standalone
  PostgreSQL project's `default` network, adds `auth_db` with stable DNS
  alias `panadan-auth-postgres`. Keeps the DB volume/healthcheck/loopback
  port from `compose.platform.yaml`.
- `deploy/compose.auth-network.panadan.yaml`: adds only the `vpn`
  service to `auth_db`, and retains its `default`. Compose merges
  the existing local `data/ingress/compose.panadan.yaml` ingress
  network; verify the *effective merged config* retains `ingress` before
  attempting any future compose up. **Do not give web a `networks` field**
  alongside its `network_mode: service:vpn`.

Both reference a deliberately external network named `panadan-auth-db`.
Operators must create it as internal (e.g. `docker network create --internal
--driver bridge panadan-auth-db`) **only after** an approved change review
and backup. Docker Compose cannot assert that a preexisting external network
is internal; this must be verified at runtime with `docker network inspect`.

## Current safe, read-only inspection (do this first)

```bash
cd ~/panadan
sudo ./panadan.sh platform-db check
sudo ./panadan.sh platform-db roles-check
sudo docker inspect panadan-platform-db-1 panadan-vpn-1 \
  --format '{{.Name}} {{range $n,$v := .NetworkSettings.Networks}}{{$n}} {{end}}'
sudo docker inspect panadan-vpn-1 --format '{{.State.Health.Status}}'
sudo docker exec panadan-vpn-1 ip -4 route get 192.168.3.9
curl -fsS https://dan.panafor.com/healthz
curl -fsS -o /dev/null https://plane.panafor.com/intake.html
```

The next checks validate the proposed effective configuration **without
deploying anything**. They require the two overlay files from this PR.
The existing private ingress overlay must be kept in the invocation:

```bash
cd ~/panadan
sudo docker compose --env-file .env.platform \
  -f compose.platform.yaml \
  -f deploy/compose.auth-network.platform.yaml \
  config --quiet

sudo docker compose --env-file .env.app \
  -f compose.prod.yaml \
  -f data/ingress/compose.panadan.yaml \
  -f data/ingress/compose.web.release.yaml \
  -f data/ingress/compose.web.https.yaml \
  -f deploy/compose.auth-network.panadan.yaml \
  config --quiet
```

Review effective network maps (do **not** paste the full `config` output
into tickets: it contains interpolated secrets):

```bash
sudo docker compose --env-file .env.app -f compose.prod.yaml \
  -f data/ingress/compose.panadan.yaml \
  -f data/ingress/compose.web.release.yaml \
  -f data/ingress/compose.web.https.yaml \
  -f deploy/compose.auth-network.panadan.yaml \
  config --format json | python3 -c '
import json,sys
c=json.load(sys.stdin)
print("VPN networks:", sorted(c["services"]["vpn"]["networks"]))
print("Web network mode:", c["services"]["web"]["network_mode"])
print("External DB network:", c["networks"]["auth_db"]["name"])
'
```

Expected VPN networks: `auth_db`, `default`, and the existing ingress
network; Web mode: `service:vpn`. Never print environment variables.

## Read-only network audit helper

`tools/check_auth_db_network.py` audits current Docker state without
connecting or restarting containers. It checks that PostgreSQL and VPN are
healthy, original networks persist, PostgreSQL ports bind loopback only,
the proposed network is an internal bridge with **no Plane/gateway access**,
and the existing Odoo source route still uses `tun0`. It does not display
environment variables or customer data.

On the VPS, retrieve the checked-in script from this PR **without switching
your active production branch or overwriting local Compose files**:

```bash
cd ~/panadan
git fetch origin ops/private-auth-postgres-network
git show FETCH_HEAD:tools/check_auth_db_network.py > /tmp/panadan-check-auth-network.py

# Before attaching anything (read-only):
sudo python3 /tmp/panadan-check-auth-network.py --stage before
```

`--stage before` passes when the new network is absent or exists as an empty
internal bridge. If either container is already attached, the script refuses
the `before` stage; inspect state rather than trying to connect again.
After an explicitly approved network change, run the same script with
`--stage after`. Only the expected DB/VPN members and hostname alias pass.

**Neither command creates a network or connects a container.** They cannot
verify PostgreSQL TCP reachability; the separate ephemeral Python
`socket.create_connection` smoke test below checks that, after controlled
attachment. Keep the existing production services online throughout.

## Future staged connection procedure — NOT automatic

1. Confirm a verified, off-VPS PostgreSQL backup and a separate recovery
   key. Run current role and health checks. Never recreate, change or delete
   the existing PG volume or restart all Docker services.
2. Confirm `panadan-auth-db` does not already exist with different
   members/subnet, then create an **internal** bridge, and verify
   `docker network inspect panadan-auth-db --format '{{.Internal}}'`
   returns `true`.
3. In a controlled networking change, attach **only**
   `panadan-platform-db-1` with alias `panadan-auth-postgres`, then
   `panadan-vpn-1` to the new bridge (no restart or recreation).
   Check that original network attachments remain and the Odoo route
   still resolves via `tun0`.
4. Test **TCP only**, without a password or query to PostgreSQL. Use a
   disposable container in the *VPN network namespace* with the **already
   installed** Panadan web image; never pull an unpinned debugger image:

```bash
image="$(sudo docker inspect panadan-web-1 --format '{{.Config.Image}}')"
sudo docker run --rm --pull never \
  --network container:panadan-vpn-1 \
  --entrypoint python "$image" -c '
import socket
with socket.create_connection(("panadan-auth-postgres",5432),timeout=5):
    print("PASS: private PostgreSQL TCP is reachable from Panadan network namespace")
'
```

This deliberately does **not** verify PostgreSQL authentication,
`panadan_auth_runtime` grants, encrypted backups, or auth schema.
Those remain separate release blockers.

5. After verifying the runtime network and the **existing** public Plane
   and Panadan health, persist both connections using their respective
   Compose overrides in a separate, reviewed maintenance window. A
   `docker compose up` may recreate the VPN or DB container; that can
   temporarily interrupt Panadan/Odoo reads and must not be automated.
   Ensure existing production overlays remain included each time.

### Emergency network-only rollback

If adding the network causes the Odoo route, VPN or Panadan health to
change, disconnect only the new network endpoints:

```bash
sudo docker network disconnect panadan-auth-db panadan-vpn-1
sudo docker network disconnect panadan-auth-db panadan-platform-db-1
```

Verify original network membership, `tun0`, platform PostgreSQL health,
Panadan `/healthz`, Plane `/` and `/intake.html`. Do not remove the network
or alter old Compose files until all connections are verified stable.

**Other pending work:** #70 restricted auth DB role, versioned migration 003,
isolated SQLite snapshot import with full restored auth behavior; #55
encrypted off-site PostgreSQL `pg_dump -Fc` and restore; #57/#58 OAuth
issuer discovery / ChatGPT and Claude connection. Live production still
uses SQLite authentication and legacy MCP mode.
