# Production backups: SQLite auth and owned PostgreSQL (opt-in, 2026-11-01)

The deployment has already produced an online SQLite snapshot, verified it using
`PRAGMA integrity_check`, and copied an `age`-encrypted copy to an independent
WSL workstation. This is **manual evidence only**; automated off-site backups
and full recovery **are not yet deployed/verified**.

Issue: [#55](https://github.com/aliinreallife/panadan/issues/55).

## What the new script does

`bash tools/backup-auth-offsite.sh` is an **opt-in** tool; it does not run
automatically after merging. It:

1. Opens a consistent SQLite Online Backup API snapshot from the running
   `panadan-web-1` container (no service stop, no raw file-copy of a live WAL database).
2. Copies the temporary snapshot to a root-only temporary directory on the host,
   checks SQLite integrity and nonempty schema.
3. Encrypts the snapshot with the operator-provided **public age recipient**,
   without loading the private decryption key on the VPS.
4. Uploads the ciphertext to an independently configured rclone remote, reads it
   back and compares ciphertext SHA-256. Only then retains a local encrypted copy.
5. Removes the container and host plaintext temporary snapshots on normal exit
   and failure, and prevents overlapping timer/manual runs with `flock`.

**Limitations:** transient plaintext exists on the VPS during snapshotting;
the script does not automatically rotate keys, prune old copies, confirm
application-level auth restore, or back up private VPN/IdP/TLS configuration.
Backups do not include the externally owned Odoo PostgreSQL source data.
A successful uploaded ciphertext does not prove that the off-site private key
will be available after a disaster; practice decryption/restore separately.

## Preflight, no database access

Install and securely configure Docker, Python 3, `age`, `rclone`, and `flock`
on the VPS. Use a **private** rclone configuration for an independent destination
(e.g. another provider/storage account, not a local mount or same VPS).
Grant the off-site credentials the minimum write/read required for copying,
reading back and listing objects. Avoid shared personal cloud root buckets.

Generate an age keypair **on an independent trusted machine**, retain the private
key in two secure places outside the VPS, and copy **only the public `age1...` key**
to the backup configuration. The existing WSL age identity can be used after
secure independent escrow. Do not paste private material into tickets.

Create a root-only environment file (example paths; adjust as needed):

```bash
sudo install -d -m 700 /etc/panadan
sudoedit /etc/panadan/backup.env
sudo chmod 600 /etc/panadan/backup.env
```

Example file content (replace placeholders; never commit this file):

```ini
PANADAN_BACKUP_AGE_RECIPIENT=age1REPLACE_WITH_REAL_PUBLIC_KEY
PANADAN_BACKUP_RCLONE_DEST=offsite:panadan/auth
PANADAN_PLATFORM_BACKUP_RCLONE_DEST=offsite:panadan/owned-postgres
RCLONE_CONFIG=/etc/panadan/rclone.conf
```

**Before testing:** Configure an actual `offsite:` rclone remote, create the
target prefix if the provider requires it, and verify root can list it. The
`/etc/panadan/backup.env` file must only be sourced from a trusted,
root-owned file; no environment values may come from untrusted input.

Manual *read-only remote* preflight, run on VPS **as root**:

```bash
cd /home/panafor/panadan
sudo bash -c '
  set -euo pipefail
  set -a; source /etc/panadan/backup.env; set +a
  bash tools/backup-auth-offsite.sh --check
'
```

Do not proceed unless it succeeds; the backup script fails closed if
remote listing, recipient, container, or prerequisites fail.

Manual initial encrypted off-site transfer:

```bash
cd /home/panafor/panadan
sudo bash -c '
  set -euo pipefail
  set -a; source /etc/panadan/backup.env; set +a
  bash tools/backup-auth-offsite.sh
'
```

No secrets or transcripts should appear in the successful output. Verify the
result on the **independent** machine with its private age key; decrypt to a
transient secure test location and use SQLite integrity/checks, never overwrite
live `/data/auth.sqlite`. Compare source SHA-256 to decrypted SHA-256
against the *same* snapshot if validating the original manual backup.

## Independent SQLite auth restore verification (web release gate)

The **2026-11-02 web-only production release** must not be treated as safe
solely because `prodctl-production.sh plan/check` and HTTP smoke tests pass.
The existing source auth database remains SQLite, and the operator's
previously copied encrypted off-VPS backup has not yet been independently
restored. Before acknowledging `--ack-restored-backup`, prove at least one
recent **off-VPS** account backup can be decrypted with the escrowed private
identity and restored in isolation.

On a trusted **WSL/Linux recovery machine, not the VPS**, retrieve the
already-copied encrypted SQLite auth snapshot and separately stored age
private identity. Never send those files or their contents to GitHub, CI,
chat, or the server. Run this from a checkout with the latest release checks:

```bash
cd ~/panadan
git pull --ff-only
bash tools/verify-offsite-auth-restore.sh \
  '/actual/off-vps/path/auth-YYYYMMDDTHHMMSSZ.sqlite.age' \
  '/actual/off-vps/path/private-age-identity.txt'
```

Substitute real local paths. This is **not** the PostgreSQL restore helper.
The script requires `age`, `python3`, a writable memory-backed
`/dev/shm`, and a real encrypted snapshot; it never creates new users,
contacts the VPS, uses Docker, changes live accounts or reads customer
records. It decrypts **only into tmpfs**, confirms SQLite integrity, core
authentication tables and the presence of an active hashed administrator,
copies the snapshot into another disposable SQLite database using SQLite's
backup API, and verifies restored integrity/schema and equal row counts for
all tables. A trap erases temporary decrypted and restored files on exit.
It prints only PASS/FAIL and generic information, no credentials, usernames,
token hashes, detailed errors or row contents.

This verifies only the supplied artifact. **Before rolling out**, verify
it is recent enough for your accepted account-data loss window; a stale
Nov 1 snapshot may not reflect subsequent user/role/token changes. Ideally
take another SQLite **Online Backup API** snapshot before release, encrypt it,
copy it off-VPS and repeat this independent restore on the fresh artifact.
Do not use `cp` directly against the live SQLite WAL file. The WSL restore
drill does not verify successful login with the actual production password,
ongoing automation/retention, full Plane/VPN/PG disaster recovery or escrow
redundancy. No backup, restore or auth migration step is implied by a merge.

## Optional daily systemd schedule (only after successful manual restore drill)

Install a service and timer explicitly during a maintenance review. Versioned
examples are in `deploy/systemd/panadan-auth-backup.service` and
`deploy/systemd/panadan-auth-backup.timer`. Check and adjust their paths for
your server first. After manual backup and restore verification, copy them with:

```bash
sudo install -m 644 deploy/systemd/panadan-auth-backup.service /etc/systemd/system/
sudo install -m 644 deploy/systemd/panadan-auth-backup.timer /etc/systemd/system/
sudo systemd-analyze verify /etc/systemd/system/panadan-auth-backup.service /etc/systemd/system/panadan-auth-backup.timer
```

Then review the exact unit contents; the following snippets show their
expected configuration. Installing files does not start a timer.

`/etc/systemd/system/panadan-auth-backup.service`:

```ini
[Unit]
Description=Panadan encrypted off-site auth SQLite backup
Wants=docker.service
After=docker.service network-online.target

[Service]
Type=oneshot
User=root
EnvironmentFile=/etc/panadan/backup.env
WorkingDirectory=/home/panafor/panadan
ExecStartPre=/usr/bin/bash /home/panafor/panadan/tools/backup-auth-offsite.sh --check
ExecStart=/usr/bin/bash /home/panafor/panadan/tools/backup-auth-offsite.sh
TimeoutStartSec=30min
NoNewPrivileges=true
```

`/etc/systemd/system/panadan-auth-backup.timer`:

```ini
[Unit]
Description=Daily Panadan encrypted off-site auth backup

[Timer]
OnCalendar=*-*-* 03:15:00 UTC
Persistent=true
RandomizedDelaySec=15m
Unit=panadan-auth-backup.service

[Install]
WantedBy=timers.target
```

Review with `systemd-analyze verify`, then explicitly enable with
`sudo systemctl daemon-reload` and
`sudo systemctl enable --now panadan-auth-backup.timer`.
No schedule is installed by the code in this PR.

Alert independently when the timer/service fails or the latest remote object is
older than the agreed RPO. Keep `journalctl -u panadan-auth-backup.service`
metadata-only. Define remote retention (e.g. daily 14 / weekly 8 / monthly 6)
**after** confirming the provider supports immutable versioning / retention,
the off-site store is isolated, and a full restore test works. Never delete the
last good copy; deletion/retention automation is a separate reviewed change.

## Owned PostgreSQL 18 encrypted off-site backups (new opt-in code)

**Use a different off-site prefix from SQLite.** PostgreSQL and SQLite contain
different datasets; backing up only one of them does not protect Panadan
accounts before/after the future #70 cutover.

`tools/backup-platform-offsite.sh` is a separate safe entry point for the
**Panadan-owned** `panadan-platform` Compose project. It never starts/stops
containers, changes networks, connects to the external Odoo source, or reads
the live SQLite database. Its steps are:

1. Refuse malformed, symlinked, or overly permissive `.env.platform`;
   validate Compose's existing DB container is running PostgreSQL major 18,
   database `panadan` owned by `panadan_owner`, with all seven ingest
   foundation tables.
2. Check independent rclone destination availability; in `--check` mode
   **stop here** without creating backups or writing to the database.
3. Stream `pg_dump -Fc` from the running owned DB into a protected temporary
   directory; verify its TOC via `pg_restore --list`. The full dump includes
   any existing `panadan_auth` tables; it is not restricted to `panadan_ingest`.
4. Encrypt that temporary archive with the PUBLIC age recipient, upload with
   immutable randomly named object keys, read remote bytes back, and compare
   SHA-256. Retain a local mode-600 **encrypted-only** copy after verification.
   Remove temporary plaintext on success and failure.

`pg_restore --list` is **only an archive TOC check**; it cannot prove data
integrity or a successful recovery. The true recovery gate is decrypting the
off-VPS object with the independent private key and performing a disconnected
PG18 restore, checking expected schemas, account records and permissions.
There are now **two deliberately separate** local restore helpers:

- `tools/verify-offsite-platform-restore.sh` validates the specific
  historical pre-auth, zero-source PostgreSQL snapshot, optionally rehearsing
  the auth migration. It must **not** be used for populated auth snapshots.
- `tools/verify-populated-platform-restore.sh` is the new
  **offline, disposable** restore verifier for backups containing the
  `panadan_auth` schema and at least one account. It restores
  a supplied archive into a PostgreSQL 18.6 container with `--network none`, an
  ephemeral size-limited tmpfs, no host volumes or ports. It checks all seven
  ingestion and eight auth tables, validated auth constraints, the presence
  of accounts and the restricted runtime role permissions. It reads no raw
  accounts into logs and discards the temporary database.

Run the populated verifier **on a trusted independent recovery workstation**,
not the live VPS. Retrieve the backup from off-site storage using your
normal trusted channel and supply the independently escrowed age identity:

```bash
bash tools/verify-populated-platform-restore.sh \
  /secure/backup/panadan-YYYYMMDD.dump.age \
  /secure/keys/age-identity.txt \
  database/permissions/003_auth_runtime_role.sql
```

The pinned PostgreSQL image must already be locally available. With adequate
host RAM, set `PANADAN_RESTORE_TMPFS_MIB` (128–8192) only if the default
1024 MiB temporary database is too small. This command is intentionally
**read-only toward your source systems**, but it creates/deletes an isolated
test Docker container on the recovery computer.

A PASS confirms a real SQL restore, expected schema/constraints, account
presence, and permissions of a **temporary role** reconstructed from the
supplied grants. It does NOT establish that application login, OAuth recovery,
all audit rows, backup-key escrow, off-site timers, network configuration,
or whole-system disaster recovery will work. Do not run it on an archive
without auth data or infer that this alone completes issue #55/#70.

Configure an independent physically off-VPS rclone backend. A string such as
`offsite:...` does **not** prove the backend is geographically/administratively
independent. The root-only `/etc/panadan/backup.env` must include
`PANADAN_BACKUP_AGE_RECIPIENT`, `PANADAN_PLATFORM_BACKUP_RCLONE_DEST`, and
the private rclone config location. The PRIVATE age identity must remain off
the VPS. The separate DB Compose credentials stay in the ignored
`.env.platform` file (mode 600); never source Odoo credentials.

On the VPS, use a trusted repository checkout:

```bash
cd /home/panafor/panadan

# Read-only checks. No copy or database state change.
sudo bash -c '
  set -euo pipefail
  set -a; source /etc/panadan/backup.env; set +a
  bash tools/backup-platform-offsite.sh --check
'

# Real encrypted off-site upload: opt in only after remote/key review.
sudo bash -c '
  set -euo pipefail
  set -a; source /etc/panadan/backup.env; set +a
  bash tools/backup-platform-offsite.sh
'
```

A matching **disabled-by-default** systemd service/timer is in
`deploy/systemd/panadan-platform-backup.{service,timer}` (03:55 UTC + jitter).
Review paths and validate with `systemd-analyze verify` before installing
anything. Do **not** enable it until a real encrypted PG backup has
independently passed a full isolated restore with the off-site key. Then
configure external failed/missed-job alerts, offsite freshness checks,
retention/immutability, independent recovery-key escrow and quarterly drills.
Do not interpret merely merging this code as working automated backups.

## Read-only off-site freshness check (not an alerting service)

The optional `tools/check_backup_freshness.py` validates the **presence and age
of encrypted backup object names** on the two independent rclone prefixes.
It requires an operator-approved threshold; it does not invent an RPO. It
never decrypts, modifies, prunes or downloads the archive bytes.

After configuring the private root-only `/etc/panadan/backup.env` and
both rclone remote destinations, run:

```bash
cd /home/panafor/panadan
sudo bash -c '
  set -euo pipefail
  set -a; source /etc/panadan/backup.env; set +a
  python3 tools/check_backup_freshness.py --store both --max-age-hours 36
'
```

**36 hours is only an example:** replace it with an explicitly approved
maximum age for both stores. Use `--store sqlite` or `--store platform` to check
one backup system during a staged rollout. This command lists only rclone
object metadata with known generated filename patterns and rejects backups
with implausible timestamps, malformed filenames or tiny encrypted objects.
It does not disclose cloud paths or object names in ordinary status output.

Exit code 0 means **the required remote contains a filename dated within
the configured window**. Exit code 1 means stale, missing or unreadable
metadata; code 2 means invalid configuration. A filename/size check cannot
prove independent storage, ciphertext integrity, decryption-key availability,
or actual PostgreSQL/SQLite application recoverability.

To operationalize this check later, schedule it **outside** the existing
backup job, deliver failure/late-run alerts to an independently configured
monitoring service, test delivery and missed-execution detection, then
document the approved RPO, escalation owner, and recovery procedure. Merely
merging the checker does not enable any timer, alert or off-site backup.

## Disaster recovery checklist

- Confirm you can decrypt an off-site copy with the independent private key.
- Recover the auth database into a new, disconnected volume; run SQLite integrity
  check and synthetic/authorized app login and permissions regression checks.
- Securely provision private VPN/DB config and approved image digests from
  separate escrow; restore network, Nginx, Caddy and TLS with a reviewed plan.
- Verify source PostgreSQL route and least-privilege reads; never modify Odoo
  data or restore this SQLite over a running container.
- Document RPO/RTO and run quarterly independent recovery drills.
