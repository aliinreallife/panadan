# Read-only reporting boundary / سیاست دسترسی فقط خواندنی

The **source reporting database** and Panadan's separate **local SQLite
authentication database** have different access policies.

| Interface | Source reporting DB | Panadan auth SQLite |
| --- | --- | --- |
| Dashboard | Fixed SELECT-only reporting queries | Session/login/user management may write |
| REST API | Fixed SELECT-only reporting queries | Access-token last-used accounting may write |
| MCP (manual bearer or OAuth) | Four fixed SELECT-only, non-sensitive tools | Token usage or OAuth account lookups may write/read |
| Admin panel | Never writes to the source reporting DB | Admin can create/suspend users, revoke connections |

The data connection in `server/database.py` specifies
`default_transaction_read_only=on` and explicitly begins every operation
with `SET TRANSACTION READ ONLY`. Queries use allowlisted columns and parameter
bindings; no arbitrary SQL editor or write-capable HTTP endpoint exists.
Read-only transaction enforcement does **not** replace least-privilege database grants.

## Check the actual PostgreSQL account (no changes to the database)

Run from WSL with your private VPN and `.env.db` already configured:

```bash
cd "$HOME/panadan"
./panadan.sh audit-db
```

The command starts the local VPN/relay, then performs read-only catalog checks
using the configured `PGUSER`. It never reads a customer call or changes a
database object, grant, role or record.

- Exit **0 / PASS**: the reporting transaction is read-only, the required
  view is readable, and no **detected** permanent-object create/write grants
  exist in non-system schemas.
- Exit **1 / FAIL**: there is a reported write privilege, unexpectedly missing
  read permission, or a transaction not marked read-only.
- Exit **2**: could not finish checking (VPN, config or catalog error); this is
  **not** a PASS.

The audit detects effective permissions, including those granted through
`PUBLIC` or inherited roles. It checks CREATE on schemas/database, and
INSERT/UPDATE/DELETE/TRUNCATE on non-system relations, rather than only
checking the reporting view.

Temporary-table creation is reported as an **advisory** because TEMP is often
granted to PUBLIC by default. An audit PASS does not prove the account has no
other non-data privileges: for example, DBA review of SECURITY DEFINER
functions, sequences, role memberships, extensions, other databases, and the
runtime application's environment is still necessary.

## What to do if the audit finds CREATE

A previous inspection noted that the existing reporting login could
`CREATE` objects in the `public` schema. This is **not verified for the
current server** until `./panadan.sh audit-db` is run.

**Recommended approach: use a separate dedicated least-privilege role**
instead of changing the grants of a shared reporting role.

The database administrator can create a login whose only intended data
access is SELECT on `public.vw_danix_call_info_report` and CONNECT to the
required database, with no schema CREATE or data modification grants.

The following is a **starting point for DBA review, not an automated
migration**. Replace placeholders and check existing PUBLIC grants and role
membership before making changes:

```sql
-- Run as an appropriately authorized DBA in the target database.
CREATE ROLE panadan_reader LOGIN NOINHERIT PASSWORD '<new-secret-from-vault>';
GRANT CONNECT ON DATABASE odoo TO panadan_reader;
GRANT USAGE ON SCHEMA public TO panadan_reader;
GRANT SELECT ON TABLE public.vw_danix_call_info_report TO panadan_reader;
ALTER ROLE panadan_reader IN DATABASE odoo SET default_transaction_read_only = on;
```

New roles may inherit broad **PUBLIC** privileges regardless of NOINHERIT.
A DBA must inspect actual grants and resolve unwanted PUBLIC or
database-owner rights. Avoid blanket `REVOKE` on shared roles, schemas or
PUBLIC without understanding production dependencies.

Only after the DBA verifies the dedicated role, replace `PGUSER` and
`PGPASSWORD` in your ignored `.env.db`, then run the audit again.
**Never commit database credentials, role passwords or query results
containing customer data.**

## Regression protection

CI runs `tests/test_readonly_audit.py`, which checks that all reporting
functions use explicit READ ONLY transactions and only SELECT statements,
the REST reporting routes expose GET rather than data-writing methods,
the MCP tool list remains the known read-only allowlist, and the privilege
audit fails on simulated write grants.

This does not cover live permissions until the local audit is executed.
