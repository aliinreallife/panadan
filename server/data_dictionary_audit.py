"""Privacy-safe, read-only source-view audit. No call rows or identifiers leave PostgreSQL.

Run through the VPN relay: ./panadan.sh audit-fields
Only aggregate counts, min/max metadata, and known source column names are printed.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import database

COLUMN_SQL = """
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = %s AND table_name = %s
ORDER BY ordinal_position
"""

# This fixed query only touches the allowlisted reporting view. The inner
# MATERIALIZED CTE bounds work to a chosen slice of IDs; output is aggregate
# metrics only. No transcript, customer name, call_id, or phone value is printed.
SAMPLE_SQL = """
WITH sampled AS MATERIALIZED (
    SELECT
        "CALLDATE" AS call_date, create_date, call_time, voice_length,
        tellnum, customertell, tellside, tellstate, aicallinfostate,
        possibility_of_sale_ai AS score, deal_value, invoiced_target,
        vw_danix_base_info_users AS operator_id,
        vw_danix_base_info_users_name AS operator_name,
        pipeline_expert_id, team_id, stage_id, crm_team_name,
        crm_team_user_id, vw_how_to_know_name, vw_followup_stage_name
    FROM public.vw_danix_call_info_report
    ORDER BY id DESC
    LIMIT %s OFFSET %s
),
operator_names AS (
    SELECT operator_id,
           COUNT(DISTINCT NULLIF(BTRIM(operator_name), '')) AS names_count
    FROM sampled
    WHERE operator_id IS NOT NULL
    GROUP BY operator_id
),
name_owners AS (
    SELECT operator_name, COUNT(DISTINCT operator_id) AS ids_count
    FROM sampled
    WHERE operator_name IS NOT NULL AND BTRIM(operator_name) <> ''
    GROUP BY operator_name
)
SELECT
    COUNT(*) AS rows_sampled,
    MIN(call_date) AS earliest_call_date,
    MAX(call_date) AS latest_call_date,
    COUNT(call_date) AS call_dates_present,
    COUNT(create_date) AS create_dates_present,
    COUNT(*) FILTER (WHERE create_date::date = call_date) AS dates_match_as_naive,
    COUNT(*) FILTER (
        WHERE ((create_date AT TIME ZONE 'UTC') AT TIME ZONE 'Asia/Tehran')::date = call_date
    ) AS dates_match_if_utc_to_tehran,
    COUNT(call_time) AS call_time_present,
    MIN(call_time) AS call_time_min,
    MAX(call_time) AS call_time_max,
    COUNT(DISTINCT call_time) AS call_time_unique,
    COUNT(*) FILTER (WHERE call_time < 0) AS call_time_negative,
    COUNT(*) FILTER (WHERE call_time BETWEEN 0 AND 2359
                           AND MOD(call_time, 100) < 60) AS call_time_possible_hhmm,
    COUNT(*) FILTER (WHERE call_time BETWEEN 0 AND 235959
                           AND call_time / 10000 < 24
                           AND MOD(call_time / 100, 100) < 60
                           AND MOD(call_time, 100) < 60) AS call_time_possible_hhmmss,
    COUNT(*) FILTER (WHERE call_time BETWEEN 946684800 AND 2147483647) AS call_time_possible_epoch,
    COUNT(*) FILTER (WHERE call_time BETWEEN 0 AND 86399) AS call_time_possible_day_seconds,
    COUNT(*) FILTER (WHERE call_time IS NOT NULL AND voice_length IS NOT NULL
                           AND ABS(call_time - voice_length) <= 1) AS call_time_matches_audio_seconds,
    COUNT(voice_length) AS voice_length_present,
    COUNT(tellnum) AS tellnum_present,
    COUNT(*) FILTER (WHERE tellnum IS NOT NULL AND tellnum = TRUNC(tellnum)
                           AND tellnum BETWEEN 0 AND 999999999999999) AS tellnum_safe_integer_range,
    COUNT(*) FILTER (WHERE customertell IS NOT NULL
                           AND BTRIM(customertell) <> '') AS customer_phone_nonempty,
    COUNT(*) FILTER (WHERE customertell ~ '^[0-9 +().-]{7,30}$') AS customer_phone_ascii_like,
    COUNT(*) FILTER (
        WHERE customertell ~ '^[0-9 +().-]{7,30}$'
          AND LTRIM(REGEXP_REPLACE(customertell, '[^0-9]', '', 'g'), '0') =
              CASE WHEN tellnum BETWEEN 0 AND 999999999999999
                         AND tellnum = TRUNC(tellnum)
                   THEN tellnum::bigint::text ELSE NULL END
    ) AS phone_values_match_after_losing_leading_zero,
    COUNT(tellside) AS tellside_present,
    COUNT(DISTINCT tellside) AS tellside_unique,
    COUNT(tellstate) AS tellstate_present,
    COUNT(DISTINCT tellstate) AS tellstate_unique,
    COUNT(aicallinfostate) AS ai_state_present,
    COUNT(DISTINCT aicallinfostate) AS ai_state_unique,
    COUNT(*) FILTER (WHERE aicallinfostate = 'SoldOut') AS soldout_status_count,
    COUNT(score) AS ai_score_present,
    MIN(score) AS ai_score_min,
    MAX(score) AS ai_score_max,
    COUNT(*) FILTER (WHERE score = 100) AS ai_score_100,
    COUNT(*) FILTER (WHERE score < 0 OR score > 100) AS ai_score_out_of_0_100,
    COUNT(DISTINCT score) AS ai_score_unique,
    COUNT(operator_id) AS operator_id_present,
    COUNT(DISTINCT operator_id) AS operator_ids,
    COUNT(*) FILTER (WHERE operator_id IS DISTINCT FROM pipeline_expert_id)
        AS operator_pipeline_id_mismatch,
    COUNT(*) FILTER (WHERE operator_name IS NULL OR BTRIM(operator_name) = '')
        AS operator_names_missing,
    (SELECT COUNT(*) FROM operator_names WHERE names_count > 1)
        AS operator_ids_with_multiple_names,
    (SELECT COUNT(*) FROM name_owners WHERE ids_count > 1)
        AS operator_names_shared_by_multiple_ids,
    COUNT(team_id) AS team_id_present,
    COUNT(crm_team_name) AS crm_team_name_present,
    COUNT(crm_team_user_id) AS crm_team_user_id_present,
    COUNT(stage_id) AS stage_id_present,
    COUNT(vw_how_to_know_name) AS acquisition_name_present,
    COUNT(vw_followup_stage_name) AS followup_stage_name_present,
    COUNT(invoiced_target) AS invoiced_target_present,
    COUNT(deal_value) AS deal_value_present,
    COUNT(*) FILTER (WHERE deal_value = 0) AS deal_value_zero,
    COUNT(*) FILTER (WHERE deal_value > 0) AS deal_value_positive
FROM sampled
"""

def audit(*, limit: int = 300, offsets: tuple[int, ...] = (0, 1000, 5000)) -> dict:
    """Return metadata and bounded aggregate metrics; never raw source records."""
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    if not offsets or len(offsets) > 3 or any(type(o) is not int or o < 0 or o > 50000 for o in offsets):
        raise ValueError("provide one to three offsets between 0 and 50000")
    with database.connect() as conn:
        columns = conn.execute(COLUMN_SQL, ("public", "vw_danix_call_info_report")).fetchall()
    if not columns:
        raise RuntimeError("reporting view metadata unavailable")
    results = []
    for offset in offsets:
        # Separate short read-only transaction for each bounded slice. Failed
        # slices never cause raw exception messages to be printed.
        with database.connect() as conn:
            row = conn.execute(SAMPLE_SQL, (limit, offset)).fetchone()
        results.append({"offset": offset, **dict(row)})
    return {
        "source": database.VIEW,
        "sampling": "ORDER BY id DESC; ID order is not necessarily chronological",
        "limit_per_offset": limit,
        "columns": [{"name": r["column_name"], "type": r["data_type"]} for r in columns],
        "samples": results,
        "cautions": [
            "Aggregates describe samples only, not the entire database.",
            "Possible timestamp/duration matches are hypotheses, not field definitions.",
            "create_date timezone is not verified with the source owner.",
            "tellnum is floating point; match counts may miss formatting/country codes.",
            "No customer names, phone values, call IDs, or transcripts are output.",
            "Operator mappings and team labels are NOT authorization boundaries."
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=300, help="1-1000 rows per slice")
    parser.add_argument("--offsets", default="0,1000,5000",
                        help="comma-separated ID-order offsets (up to 3)")
    args = parser.parse_args(argv)
    try:
        offsets = tuple(int(x) for x in args.offsets.split(","))
        result = audit(limit=args.limit, offsets=offsets)
    except (ValueError, RuntimeError) as exc:
        # Validation failures are authored locally; DB errors below are masked.
        if isinstance(exc, ValueError):
            print("Invalid audit options", file=sys.stderr)
        else:
            print("Audit unavailable: view metadata missing", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Audit failed: {type(exc).__name__} SQLSTATE={getattr(exc, 'sqlstate', None) or 'unknown'}",
              file=sys.stderr)
        print("If the failure is connection-related, run ./panadan.sh diagnose-db to",
              "check the local relay, VPN route and PostgreSQL readiness separately.",
              file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
