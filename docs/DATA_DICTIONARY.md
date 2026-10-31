# Source reporting data dictionary and verification

**Source:** `odoo.public.vw_danix_call_info_report` (one authorized reporting view).
Do not assume similarly named Odoo tables are readable: the `report_user` role
could read just this view in the 2026-10-31 privilege inspection.

## Confirmed vs pending

| Fields | Current use / claim | Confidence and action |
| --- | --- | --- |
| `id` | Reporting row/call lookup key | Used in API, confirm uniqueness across view/source migrations |
| `CALLDATE` | Filtered/reported call date | Source semantics and timezone not verified |
| `create_date` | Report record creation time; UI/API convert UTC-naive to Tehran | **Strongly supported UTC-naive interpretation**: 297/297 clock comparisons align after UTC→Tehran conversion; source owner has not yet confirmed the storage contract |
| `voice_length` | Duration of recorded audio, in **seconds** | **Confirmed by product owner**; shown as human-readable duration |
| `call_time` | Integer; 893/900 non-null in initial audit and 297/300 in follow-up | **Very strong evidence for seconds since Tehran midnight**: all 297 comparable records have UTC→Tehran-adjusted creation timestamps 0–60 minutes later (usually ~2 minutes). Still await upstream definition before changing presentation |
| `tellnum` | Double precision; 900/900 initial sample and 300/300 follow-up populated | **Not a customer phone number in sampled records**: all 300 follow-up values are whole positive 1–4-digit numbers, none matches the customer's last 10 digits. Likely internal extension/line/code, exact semantics still unknown. **Never use as click-to-call** |
| `customertell` | Customer telephone text | **Sensitive**; click-to-call in authorized details only, not `tellnum` |
| `customername`, `call_id` | Customer name and source call identifier | **Sensitive**; never emit from data audits |
| `tellside` | Call direction/side | Enumerations and mapping unverified; do not guess incoming/outgoing labels |
| `tellstate` | Call type values such as `FirstToch`, `FollowUp` | Localized labels are presentation-only; verify category semantics |
| `aicallinfostate` | AI/report status (including `SoldOut`) | `SoldOut` means **source reported** sold, not financially confirmed |
| `possibility_of_sale_ai` | AI-estimated likelihood-of-sale score | 0–100 observed in sample, but **not calibrated probability**; NULL is missing, not zero |
| `deal_value` | Possible deal value | 3,000 earlier sampled records and all 900 new sampled records contained zero; currency, meaning and completeness **unverified**. Not confirmed revenue |
| `invoiced_target` | Possible invoicing target | 0/900 populated in three new sampled slices; ignore until confirmed |
| `vw_danix_base_info_users` | Candidate numeric operator identity | All 900 sampled rows had an ID; 0 ID/pipeline mismatches and no within-slice ID/name collisions. Cross-period ID/name stability and ownership still require confirmation |
| `pipeline_expert_id` | Candidate CRM pipeline expert identity | Matched numeric operator ID in 3,000 samples; do not assume always equal |
| `vw_danix_base_info_users_name` | Operator display name | UI filter only; unstable/duplicate names must not be used as security scope |
| `vw_danix_base_info_users_userinfo` | Additional operator information | Unknown and potentially sensitive; do not expose by default |
| `team_id`, `crm_team_name`, `crm_team_user_id`, `crm_team_user_name` | Team/CRM association | Several sampled team fields empty; no source-backed membership is proven |
| `stage_id`, `vw_followup_stage_name` | CRM/follow-up stage | Sampled values absent; verify before showing |
| `how_to_know_id`, `vw_how_to_know_name` | Possible customer-acquisition source | Sampled name empty; source semantics unknown |
| `currency_id`, `vw_res_currency_name`, `vw_res_currency_full_name` | Potential currency metadata | Don't infer a unit for `deal_value` until validated |
| `outcome`, `summary`, `ai_recommendation`, `tell_state_desc`, `transcription` | AI/call free text | Sensitive; don't export or include in audit results |
| `REFRECIDAICALLINFO` | Source-system reference | Meaning unverified, use only for future source debugging after approval |

## Verified aggregate sample results — 2026-10-31

The VPN-connected operator provided successful `audit-fields` output for three
**disjoint samples of 300 rows** at ID-order offsets `0`, `1000`,
and `5000`, covering `CALLDATE` dates from 2026-10-15 through
2026-10-31. This is a **900-row sample, not a full-history census**.
It confirmed 36 column names/types.

| Metric | 900-row observation | Consequence |
| --- | --- | --- |
| `call_time` | 893 populated; all 893 in 0–86,399, range 28,457–67,116; 0 resemble audio duration | Seconds since midnight is plausible; test against actual timestamps before declaring it |
| `CALLDATE` vs `create_date` | 899/900 same dates under **both** naive and UTC→Tehran comparisons | No usable evidence for choosing timezone; the source owner must verify |
| `tellnum` vs `customertell` | Both populated 900/900; **0/900** basic normalized matches; 886 customer phone strings ASCII-formatted | Treat as different/unverified until meaning and digits are validated, never auto-dial `tellnum` |
| AI likelihood score | 741/900 present (82.3%); 0 out-of-range; 9 exactly 100 | Missing ≠ zero; 100 does not guarantee a sale |
| `SoldOut` source status | 112/900 | Source-reported status, not evidence of paid invoices |
| Operator IDs | 900/900 present; `pipeline_expert_id` mismatch 0/900; within each sample no ID/name conflicts | Good candidate numeric key; **not yet an authorization key** without cross-sample verification |
| `team_id`, `stage_id`, CRM team/user name, acquisition name, follow-up name, `invoiced_target` | Each 0/900 present | Keep excluded from UI and avoid deriving team-based access |
| `deal_value` | 900/900 populated; all **zero** | Keep financially unverified; never calculate revenue from this field |

The current audit compared `customertell` to `tellnum` after removing
ASCII punctuation and leading zeros. The zero match rate **does not establish
what `tellnum` stores**, nor rule out country-code or extension formats.
No customer identifiers were output.

### Targeted next pass — compare clocks and numeric field shape

```bash
cd ~/panadan
./panadan.sh audit-semantics --limit 300 --offsets 0,1000,5000
```

`audit-semantics` runs short fixed SQL SELECTs under the same explicit
READ ONLY transaction. It returns only counts, coarse digit-length groups
for `tellnum`, and clock-difference statistics. It **never prints**
call IDs, individual phone values, names, transcripts or timestamps.

- `naive_clock_*` tests `CALLDATE + call_time seconds` against `create_date` in its recorded timezone.
- `tehran_clock_*` tests `CALLDATE + call_time seconds` against `create_date` **assuming the latter is UTC and converting to Tehran**.
- `*_median_lag_seconds` shows whether the source record creation typically lags the hypothesized call clock. Either measure can be skewed by asynchronous processing; it is not a guaranteed source timestamp.
- `tellnum_digits_*` and `tellnum_matches_customer_last_ten_digits` are **aggregated** format checks only, not proof of caller identity or phone ownership.

Only if these comparisons are convincing **and** the source owner confirms
the semantics should the UI render `call_time` as a time-of-day. The raw value
must remain unchanged in the DB, and the timezone must be explicit.

## Targeted semantic audit results — 2026-10-31

The second audit successfully completed with **three additional 100-row
samples** at offsets `0,1000,5000`, after two earlier runs with
`--limit 300` failed with `ConnectionTimeout`. Connection timeouts do
**not** prove that a SQL query exceeded the statement timeout; the observed
smaller run succeeded, but the underlying intermittent transport issue
should be tracked separately.

| Check | Offset 0 | Offset 1000 | Offset 5000 | Combined |
| --- | ---: | ---: | ---: | ---: |
| Calls sampled | 100 | 100 | 100 | **300** |
| Valid seconds-of-day clock candidates | 98 | 99 | 100 | **297** |
| Tehran-adjusted creation within 5 minutes of call clock | 84 | 86 | 79 | **249/297 (83.8%)** |
| Tehran-adjusted creation 0–60 minutes after call clock | 98 | 99 | 100 | **297/297** |
| Without timezone adjustment, creation within 5 minutes | 0 | 0 | 0 | **0/297** |
| Median Tehran-adjusted creation lag (seconds) | +133 | +110 | +134 | ~2 minutes in each slice |
| Median unadjusted lag (seconds) | −12,467 | −12,490 | −12,466 | ~−3 h 28 min in each slice |
| `tellnum` is a whole positive 1–4-digit number | 100 | 100 | 100 | **300/300** |
| `tellnum` matches last 10 digits of `customertell` | 0 | 0 | 0 | **0/300** |

**Interpretation:** The consistent 12,600-second (3 h 30 min) shift,
near-zero-adjusted lag, and 100% within-hour alignment strongly support
`call_time` as a **Tehran-local clock represented in seconds after
midnight**, and `create_date` as a **UTC-naive recording/creation
timestamp**. This *correlation* is not yet a formal schema contract:
insertion/processing time can differ from call start/end, and the
reporting-view owner should clarify what event `call_time` denotes.

`tellnum` is not a customer mobile number in these sampled records.
Its 1–4-digit shape is **consistent with an internal extension, channel or
line code**, not proof of a specific source meaning. Keep using the
permission-protected `customertell` for click-to-call and don't
repurpose `tellnum` for identity or filtering.

**Release gate:** Do not silently change timezone conversion or show
`call_time` as a definitive call-start timestamp until the reporting
view's owner confirms its event meaning and timezone. Numeric operator
IDs still need historical verification before row-level RBAC.

Recommended low-impact run if repeating the audit:

```bash
./panadan.sh audit-semantics --limit 100 --offsets 0,1000,5000
```

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
