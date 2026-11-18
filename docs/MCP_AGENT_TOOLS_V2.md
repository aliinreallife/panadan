# Panadan MCP tools — read-only agent guide

**Status:** opt-in implementation in a GitHub review branch, not a production deployment.
The existing source is the fixed read-only reporting view
`public.vw_danix_call_info_report`. OAuth cutover is separate (draft PR #106).
A successful Stytch Test synthetic plugin is **not** permission for real calls.

## Tool catalog and recommended usage

| Tool | Agent task | Permission and sensitive-data boundary |
| --- | --- | --- |
| `get_my_access` | Start here: find effective fields, capabilities and suggested tools | Caller-only account/application projection |
| `explain_access` | Explain why a named field is missing; give consent/admin next action | Known field catalog only |
| `list_recent_calls` | Fetch a bounded list of permitted call fields, with optional date/state/operator filters | `calls:read`, field-based filters; max 100 rows and offset 10000 |
| `get_call_summary` | Details for one known positive call ID | `calls:read` and delegated `id`; excludes sensitive details |
| `get_call_metrics` | Snapshot of delegated aggregate KPIs | `metrics:read`, and filter fields if used |
| `compare_call_metrics` **new** | Compare two equal-length date windows | `metrics:read` + `CALLDATE`; 1–366 days per period; outputs only delegated KPI keys |
| `get_daily_call_counts` **new** | Build a daily volume chart across a short date range | `metrics:read` + delegated `id` and `CALLDATE`; max 31 days, only per-day COUNT |
| `get_available_states` | Find actual status values before filtering | delegated `aicallinfostate` and calls/metrics capability |
| `get_redacted_call_transcript` | Audited best-effort excerpt when explicitly authorized | `calls:transcript:read` + `calls:read`, `id`, `transcription`; disclosure is not anonymization |

The MCP protocol's tool listing advertises schema and read-only
annotations for all tools except the **audited** transcript tool, which
does write a *local audit event*, though its source query stays read-only.

**Do not infer row-level isolation:** operator/team/destination selectors
are filters, not tenancy restrictions. The production source currently
needs a separate row-authorization design before general staff onboarding.
All reporting access stays scoped to effective Panadan user/app field grants.

## AI-user examples

- “What can you access?” → `get_my_access`. Only suggest tools it returned.
- “How many calls this week?” → `get_call_metrics` with valid `after`
  and `before` only if `CALLDATE` is delegated.
- “Compared with last week?” → `compare_call_metrics` using equal
  calendar-day lengths. If baseline zero, report percentage as undefined.
- “Show daily call volume this month” → `get_daily_call_counts` with a
  requested span of at most 31 days and both `id` and `CALLDATE` delegated.
- “Summarize the last 10 calls” → `list_recent_calls` with `limit=10`.
  Only paraphrase fields actually returned; do not invent a transcript.
- “Why can't you show customer phone numbers?” → `explain_access`
  with `field=customertell`.

## Error contract

All invalid date/page arguments return a self-contained tool response:
```json
{"error": "invalid_argument", "field": "after", "hint": "Use an ISO calendar date in YYYY-MM-DD format."}
```
Denied operations still return `permission_denied` before source SQL is
constructed. Bad inputs do not get silently clamped; use valid bounds.
Field/projection errors never include report values, secrets, SQL or JWTs.

Date filters use **source `CALLDATE`**, not the user's browser timezone.
The daily trend contains all calendar dates in its interval with zeros
where no matching rows exist; it never emits identifiable call records.
Period comparisons include signed absolute differences and percentages
(percentage is null when the denominator is zero).

## Compatibility and release

- Existing MCP names, positional arguments and response shapes remain
  intact; `get_my_access` adds a `suggested_tools` field.
- Two new tools require additional data-source reads. They must pass the
  synthetic CI suite, SDK tool discovery, per-request permissions,
  HTTP bearer revocation, and controlled pre-release review.
- No Odoo schema changes, SELECT privileges, non-read-only SQL, JWT
  changes, staging/Test identity reuse or production rollout is included.
- Do **not** merge/deploy this new tool surface to the real reporting
  server until it has had the same VPS release, backup/rollback and
  row-access policy review as other reporting features.
