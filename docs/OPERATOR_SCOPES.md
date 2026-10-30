# Operator directory and future scoped permissions

Panadan's read-only reporting view currently exposes operator **display names**
under `vw_danix_base_info_users_name`, but no verified operator ID,
organizational team or destination relationship.

## Delivered

- Distinct operator discovery and exact-name filters for call lists and metrics.
- Operator profile at `/dashboard/operator?name=...` with its own call list,
  statistics, dates and read-only call details.
- `/dashboard/operators` directory with editable local **team** and
  **destination** assignments for administrators. Example destinations include
  `مشهد` and `غرب آسیا`, and teams can be entered separately.
- Operator, team and destination filters in the dashboard, REST and MCP tools,
  using the same parameterized READ ONLY SQL.
- Missing operators and unassigned team/destination labels consistently
  appear as `نامشخص`. That filter includes null/blank operator records and
  the names not mapped in the local directory.
- Team/destination mappings are in Panadan's separate local SQLite auth store;
  no records or fields are modified in the source PostgreSQL database.

## Not yet an authorization boundary

**The new team and destination fields are only filters and metadata.**
They do not currently reduce what an existing Panadan account, REST token or
AI tool can read. Do not assign team-restricted accounts yet or claim that
these metadata labels secure customer records.

Filtering one page does not secure other pages. Before introducing permissions
such as `operator:read`, `destination:read` or `team:read`, the same
fail-closed scope checks must run on **all** reporting surfaces:

1. Browser dashboard list and operator profile, detail by ID, all aggregate
   statistics, and distinct list/filter options.
2. REST list, detail including sensitive mode, metrics and status endpoints.
3. Remote MCP and WebMCP list, individual call summaries, stats and transcript
   reads (including every paginated chunk).
4. Audit and export surfaces, background jobs and any new tools, with tests
   for cross-team direct-ID access, unknown operator, revoked permissions,
   unmapped call, and mixed-team aggregates.

For reliable security the source view should provide a **stable operator ID**:
display names can change or be duplicated. Validate that ID with the source
owner before building operator-specific data authorization. The current
name-based directory is suitable for UI filtering, **not** authoritative RBAC.

Suggested future model:

- `operators` (stable source ID, display name, active state).
- `destinations` and `teams` managed locally (not source-db writes).
- `operator_memberships` (operator ID, team/destination; many-to-many if needed).
- `user_scopes` (account, explicitly allowed operator IDs, teams and
  destinations), default deny for restricted users.
- A single server-side query scope builder for both SQL filters and by-ID
  assertions, applied consistently on every endpoint and agent tool.
- Empty, blank and unassigned values should **never** be implicitly granted
  to a restricted user. Unknown membership is shown as `نامشخص` and
  requires explicit authorization, not an automatic wildcard.

When implementing these changes, migrate safely, invalidate active user
sessions/tokens after changing scope assignments, and keep the actual source
PostgreSQL role read-only.
