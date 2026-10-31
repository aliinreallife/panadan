# Source reporting data dictionary and verification

**Source:** `odoo.public.vw_danix_call_info_report` (one authorized reporting view).
Do not assume similarly named Odoo tables are readable: the `report_user` role
could read just this view in the 2026-10-31 privilege inspection.

## Confirmed vs pending

| Fields | Current use / claim | Confidence and action |
| --- | --- | --- |
| `id` | Reporting row/call lookup key | Used in API, confirm uniqueness across view/source migrations |
| `CALLDATE` | Filtered/reported call date | Source semantics and timezone not verified |
| `create_date` | Report record creation time; converted from assumed UTC in filters/UI | **Timezone is an assumption**; validate with source owner before claiming times are correct |
| `voice_length` | Duration of recorded audio, in **seconds** | **Confirmed by product owner**; shown as human-readable duration |
| `call_time` | Integer; 993/1000 populated in one sample | **Unknown** (duration, HHMM, HHMMSS, seconds since midnight, epoch, etc.); do not display as date/time yet |
| `tellnum` | Float; 1000/1000 populated in one sample | **Unknown**; may lose leading zeros; never use for dialing/identity without validation |
| `customertell` | Customer telephone text | **Sensitive**; click-to-call in authorized details only, not `tellnum` |
| `customername`, `call_id` | Customer name and source call identifier | **Sensitive**; never emit from data audits |
| `tellside` | Call direction/side | Enumerations and mapping unverified; do not guess incoming/outgoing labels |
| `tellstate` | Call type values such as `FirstToch`, `FollowUp` | Localized labels are presentation-only; verify category semantics |
| `aicallinfostate` | AI/report status (including `SoldOut`) | `SoldOut` means **source reported** sold, not financially confirmed |
| `possibility_of_sale_ai` | AI-estimated likelihood-of-sale score | 0–100 observed in sample, but **not calibrated probability**; NULL is missing, not zero |
| `deal_value` | Possible deal value | 3000 sampled records zero; currency, meaning, and completeness **unverified**; not actual revenue |
| `invoiced_target` | Possible invoicing target | 0/1000 populated in a sample; ignore until confirmed |
| `vw_danix_base_info_users` | Candidate numeric operator identity | 3,000 sampled rows had a value; source stability not yet verified |
| `pipeline_expert_id` | Candidate CRM pipeline expert identity | Matched numeric operator ID in 3,000 samples; do not assume always equal |
| `vw_danix_base_info_users_name` | Operator display name | UI filter only; unstable/duplicate names must not be used as security scope |
| `vw_danix_base_info_users_userinfo` | Additional operator information | Unknown and potentially sensitive; do not expose by default |
| `team_id`, `crm_team_name`, `crm_team_user_id`, `crm_team_user_name` | Team/CRM association | Several sampled team fields empty; no source-backed membership is proven |
| `stage_id`, `vw_followup_stage_name` | CRM/follow-up stage | Sampled values absent; verify before showing |
| `how_to_know_id`, `vw_how_to_know_name` | Possible customer-acquisition source | Sampled name empty; source semantics unknown |
| `currency_id`, `vw_res_currency_name`, `vw_res_currency_full_name` | Potential currency metadata | Don't infer a unit for `deal_value` until validated |
| `outcome`, `summary`, `ai_recommendation`, `tell_state_desc`, `transcription` | AI/call free text | Sensitive; don't export or include in audit results |
| `REFRECIDAICALLINFO` | Source-system reference | Meaning unverified, use only for future source debugging after approval |

## Privacy-safe data audit

In WSL, with Panadan's private VPN and existing environment already configured:

```bash
cd ~/panadan
./panadan.sh audit-fields --limit 300 --offsets 0,1000,5000
```

The command starts the existing VPN/relay, then queries **only the reporting
view** with the same `database.connect()` explicit READ ONLY transaction.
There is no write, data migration, new DB grant, raw SQL endpoint, or change
to live API payloads. It does not print customer names, customer phone
numbers, call IDs, transcripts, raw status values, or operator names.

It returns column **names/types** and aggregate statistics from three bounded
slices ordered by numeric `id`. Offsets may be changed with `--offsets`;
limit is capped at 1000 and at most three offsets are allowed to reduce VPN
load. This is a **sample, not historical exhaustive verification**. If a
query hits the existing 12-second statement timeout, retry
`--limit 100 --offsets 0`.

Useful results include:

- `call_time_min/max`, counts compatible with HHMM/HHMMSS/epoch/seconds-since-midnight, and comparisons to `voice_length`. **These are plausibility tests, not a definition.**
- `dates_match_as_naive` vs `dates_match_if_utc_to_tehran`. These test the current timestamp assumption, not whether `CALLDATE` is necessarily a creation date.
- `customer_phone_nonempty`, `tellnum_safe_integer_range` and `phone_values_match_after_losing_leading_zero`. An approximate, ASCII-only comparison; country codes, formatting and numeric conversions can affect results. It never returns a raw number.
- `operator_ids_with_multiple_names`, `operator_names_shared_by_multiple_ids` and `operator_pipeline_id_mismatch` for safely assessing operator ID use.
- Counts of missing CRM/team/source fields, number of AI scores, zero/positive deal values, and distinct counts of call types/directions/statuses. **No financial interpretation is assumed.**

JSON output can be shared for review. Keep raw customer data and database
secrets out of issues, PRs, CI, and chats.

## Release gates

1. **Source semantics:** verify `call_time`, `tellnum`, `tellside`, `tellstate`, `CALLDATE`, and `create_date` with the reporting-view owner; only then change display labels, conversion or time filtering.
2. **Operator identity:** verify numeric ID stability and whether team/stage information is actually populated across meaningful time periods. Until then, team/destination assignments stay local and **filters are not security**.
3. **Authorization:** before team/operator RBAC, default-deny unmapped records and enforce the same scope on dashboard list/detail-by-ID, REST, MCP, WebMCP, transcript excerpts and aggregates. Require cross-team bypass tests.
4. **DB account:** a source privilege audit detected effective `CREATE` on `public` inherited from `PUBLIC`. The application is read-only, but a DBA must remediate least privilege after dependency review. Do **not** automatically REVOKE production grants.
5. **Deployment:** verify live MCP identity/permission propagation, OAuth consent/TLS configuration, Doran input behavior, and the device dialer with non-production test calls.
