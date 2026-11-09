# Odoo incremental mirror: simple staging setup and recovery

This guide describes the **existing** Panadan PostgreSQL 18.6 staging mirror,
not a new installation from an empty VPS. The mirror is currently isolated from
the production dashboard, API, and MCP.

## What runs

- **Scheduler:** \`panadan-mirror-incremental.timer\` (systemd calendar
  \`OnCalendar=*:0/5\`, \`Persistent=true\`).
- **Job:** \`panadan-mirror-incremental.service\` (one-shot).
- **Target:** loopback-only \`panadan-mirror-staging-pg18\`,
  \`127.0.0.1:55432\`.
- **Source:** read-only Odoo reporting view through \`panadan-vpn-1\`.
- **Discovery:** \`create_date OR write_date\` timestamp windows only.
  The joined view's \`id\` orders same-time candidates; it is **not** a
  monotonically increasing new-call watermark.
- **Payload:** all 37 fields, and every joined-row variant, **only** for
  selected candidate IDs. No scheduled full-view parity/reconciliation.
- **Checkpoints:** \`created_or_modified_v1\` (timestamp windows);
  \`view_reconciliation_v1\` remains the completed original baseline.
- **Page limits:** 80 call IDs/page, max 10 pages/job; safe cursor advance
  in the same transaction as each import. The timer continues on later runs.
- **Reliability:** source is disabled between page imports; shared
  \`continuation.lock\` excludes concurrent page importers. A complete
  call group is transferred over a private pipe, not persisted as plaintext
  in transfer logs.
- **Disk guard:** at least 6 GiB free at each page; if disk is below the
  guard, no further ingestion is attempted.
- **Backups:** no new backup/restore requirement for incremental cycles,
  as explicitly requested. Preexisting archives are not deleted.

## Fast daily checks

\`\`\`bash
bash ~/panadan-mirror-runner/tools/check-odoo-mirror-incremental-status.sh status

systemctl status panadan-mirror-incremental.timer --no-pager

sudo journalctl -u panadan-mirror-incremental.service --since "1 hour ago" \
  --no-pager -o cat |
  grep -E 'STAGING INCREMENTAL:|PASS:|FAIL:|STOP:|INCREMENTAL FAILED:|Finished|Failed' |
  tail -n 40
\`\`\`

A completed catch-up window has **no \`window\` object** in the incremental
checkpoint. A healthy routine sync has \`source_enabled=false\` between
runs, a recently advanced \`completed_through\` timestamp, a healthy timer
and no repeated service failure messages. A fixed record count can be normal
when all candidates are unchanged; judge progress by the checkpoint and
successful run timestamps, not only the record count.

## When the VPS reboots

The systemd timer is enabled and designed to start after reboot.
\`Persistent=true\` can trigger a missed calendar execution, but it is
**the database timestamp checkpoint**, not systemd, that lets the importer
resume data it missed. The first run still requires the Docker daemon,
the staging PostgreSQL container and \`panadan-vpn-1\` to be available.
The service's \`After=network-online.target docker.service\` does not
automatically start missing Docker containers.

If the VPN or PostgreSQL containers fail to come back, automatic runs fail
safely until those services return. Check:

\`\`\`bash
sudo docker ps --filter name=panadan-vpn-1 \
  --filter name=panadan-mirror-staging-pg18
sudo docker inspect panadan-vpn-1 \
  --format '{{.State.Health.Status}}'
sudo systemctl status panadan-mirror-incremental.timer --no-pager
sudo systemctl status panadan-mirror-incremental.service --no-pager
\`\`\`

## What happens when the VPN is lost?

- Before transfer, the runner refuses to proceed unless the VPN health
  status is \`healthy\`.
- A source read failure inside a cycle ends that invocation unsuccessfully,
  preserves already committed pages/checkpoints and attempts to disable
  staging source ingestion. The next scheduled run retries; it does not
  rewind to the beginning or delete local records.
- Docker health alone is not proof that Odoo PostgreSQL is reachable. An
  authentication, DNS, firewall or Odoo database failure can still cause
  failed jobs. Inspect VPN logs separately without copying credentials.
- A long-lasting failure does **not** currently send alerts or automatically
  repair the VPN. Review failed runs and database freshness.

The service has a \`TimeoutStartSec=15min\` deadline. Restarting a running
service by hand is not needed for ordinary network recovery.

## Offline for multiple days?

The worker freezes and resumes bounded timestamp windows from its last
**completed** checkpoint, retaining a 15-minute overlap and 60-second
settling delay. Each run handles at most 800 candidate call IDs; a large
backlog may need many five-minute runs. This is expected, not a reason to
manually reset the cursor.

**Current limitation:** A planned window exceeding 30 days fails closed.
An outage close to 30 days may hit the guard because the 15-minute overlap
also counts. For such an outage, do **not** delete/reseed the checkpoint or
skip timestamps. Have an operator review a bounded historical replay change
and validate it before resuming. The system does not yet implement automatic
chaining of historic windows beyond this limit.

No timestamp system can detect a change that leaves both \`write_date\` and
\`create_date\` unchanged, or a newly visible join with old markers. IDs from
joined views are not proven stable. Accepted limitations; no scheduled
full-field audit is silently added.

## First installation on an already populated staging VPS

**Do not rerun** this create-only installer on a host where the timer and
service already exist. It intentionally refuses to overwrite existing units
or pinned releases.

Prerequisites: the verified complete staging mirror, independent authorized
read-only Odoo VPN connection, existing private \`~/.env.db\` configuration
used by the deployment, \`/home/panafor/panadan/.env.db\`, the restricted
private staging writer DSN, \`docker\`, \`systemd\`, working permissions,
at least 6 GiB free, and a reviewed clean checkout containing the approved
incremental implementation. The installer is deliberately **specific to
this Panadan VPS** and is not yet a turnkey fresh-server provisioner.

With a reviewed checkout in \`~/panadan-mirror-runner\`:

\`\`\`bash
bash -n ~/panadan-mirror-runner/tools/run-odoo-mirror-incremental-cycle.sh
bash -n ~/panadan-mirror-runner/tools/install-odoo-mirror-incremental-systemd.sh

# Optional, supervised single-cycle acceptance test before scheduling:
bash ~/panadan-mirror-runner/tools/run-odoo-mirror-incremental-cycle.sh cycle

# Explicit opt-in: this command smoke-tests the service and enables the timer.
bash ~/panadan-mirror-runner/tools/install-odoo-mirror-incremental-systemd.sh \
  install --ack-scheduled-sensitive-sync
\`\`\`

The installer copies the reviewed Git revision into a root-owned release
under \`/opt/panadan-mirror-incremental/releases/<sha>\`. The installed unit
executes that copy, not \`~/panadan-mirror-runner\`; updating Git alone does
**not** update the running service. Upgrades require a separate reviewed
migration/replacement plan, not another call to the create-only installer.

## Control commands

\`\`\`bash
# Execute one cycle right now. Existing timer remains enabled.
sudo systemctl start panadan-mirror-incremental.service

# Pause future cycles. Does not delete data or terminate active work by itself.
sudo systemctl disable --now panadan-mirror-incremental.timer

# Resume future cycles.
sudo systemctl enable --now panadan-mirror-incremental.timer

# Show logs, including any failures.
sudo journalctl -u panadan-mirror-incremental.service -n 100 --no-pager

# Last service result:
systemctl show -p ActiveState -p Result \
  panadan-mirror-incremental.service
\`\`\`

If a manual command fails, **do not reset timestamps**. Inspect logs,
the timestamp checkpoint, VPN health, Docker containers, available space,
and the staging source enablement flag. Re-enable the timer only after the
original failure is understood.

## Not yet included

This is **staging-only**. It does not change live dashboard/API/MCP reporting,
production authorization, or networking. It does not automatically alert on
sync lag, long VPN downtime, source identity changes or low disk space. The
operator has declined new mandatory backups. A disk/host failure can require
rebuilding the staging mirror.
