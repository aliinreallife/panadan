# Production backups: auth SQLite (work in progress, 2026-11-01)

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

## Disaster recovery checklist

- Confirm you can decrypt an off-site copy with the independent private key.
- Recover the auth database into a new, disconnected volume; run SQLite integrity
  check and synthetic/authorized app login and permissions regression checks.
- Securely provision private VPN/DB config and approved image digests from
  separate escrow; restore network, Nginx, Caddy and TLS with a reviewed plan.
- Verify source PostgreSQL route and least-privilege reads; never modify Odoo
  data or restore this SQLite over a running container.
- Document RPO/RTO and run quarterly independent recovery drills.
