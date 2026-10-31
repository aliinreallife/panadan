"""Targeted, privacy-safe hypothesis checks for call clock and tellnum.

All database reads use server/database.py's READ ONLY connection. Only numeric
aggregate metrics leave PostgreSQL; no customer, operator, or call identifiers.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import database
from .data_dictionary_audit import parse_offsets


# Keep this a compact second pass: do not join related tables, return call rows,
# or use tellnum as a dialable number. SQL identifiers are fixed and allowlisted.
SEMANTICS_SQL = """
WITH sampled AS MATERIALIZED (
    SELECT "CALLDATE" AS call_date, create_date, call_time,
           tellnum, customertell
    FROM public.vw_danix_call_info_report
    ORDER BY id DESC
    LIMIT %s OFFSET %s
), classified AS (
    SELECT
        call_time, tellnum,
        CASE WHEN call_time BETWEEN 0 AND 86399
                  AND call_date IS NOT NULL AND create_date IS NOT NULL
            THEN EXTRACT(EPOCH FROM (
                create_date -
                (call_date::timestamp + call_time * INTERVAL '1 second')
            ))
            ELSE NULL
        END AS naive_clock_lag_seconds,
        CASE WHEN call_time BETWEEN 0 AND 86399
                  AND call_date IS NOT NULL AND create_date IS NOT NULL
            THEN EXTRACT(EPOCH FROM (
                ((create_date AT TIME ZONE 'UTC') AT TIME ZONE 'Asia/Tehran') -
                (call_date::timestamp + call_time * INTERVAL '1 second')
            ))
            ELSE NULL
        END AS tehran_clock_lag_seconds,
        CASE WHEN tellnum = TRUNC(tellnum)
                  AND tellnum BETWEEN 0 AND 999999999999999
            THEN TRUNC(tellnum)::bigint::text
            ELSE NULL
        END AS numeric_phone_candidate,
        CASE WHEN customertell ~ '^[0-9 +().-]{7,30}$'
            THEN REGEXP_REPLACE(customertell, '[^0-9]', '', 'g')
            ELSE NULL
        END AS customer_phone_digits
    FROM sampled
)
SELECT
    COUNT(*) AS sampled_rows,
    COUNT(call_time) AS call_time_present,
    COUNT(*) FILTER (WHERE call_time BETWEEN 0 AND 86399)
        AS valid_seconds_of_day,
    COUNT(naive_clock_lag_seconds) AS comparable_clock_rows,
    COUNT(*) FILTER (WHERE naive_clock_lag_seconds BETWEEN -300 AND 300)
        AS naive_clock_within_five_minutes,
    COUNT(*) FILTER (WHERE tehran_clock_lag_seconds BETWEEN -300 AND 300)
        AS tehran_clock_within_five_minutes,
    COUNT(*) FILTER (WHERE naive_clock_lag_seconds BETWEEN 0 AND 3600)
        AS naive_clock_creation_after_within_hour,
    COUNT(*) FILTER (WHERE tehran_clock_lag_seconds BETWEEN 0 AND 3600)
        AS tehran_clock_creation_after_within_hour,
    ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP
        (ORDER BY naive_clock_lag_seconds))::numeric, 0)
        AS naive_clock_median_lag_seconds,
    ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP
        (ORDER BY tehran_clock_lag_seconds))::numeric, 0)
        AS tehran_clock_median_lag_seconds,
    COUNT(tellnum) AS tellnum_present,
    COUNT(*) FILTER (WHERE tellnum IS NOT NULL
                           AND tellnum <> TRUNC(tellnum))
        AS tellnum_fractional,
    COUNT(*) FILTER (WHERE tellnum < 0) AS tellnum_negative,
    COUNT(*) FILTER (WHERE tellnum = 0) AS tellnum_zero,
    COUNT(numeric_phone_candidate) AS tellnum_numeric_candidates,
    COUNT(*) FILTER (WHERE LENGTH(numeric_phone_candidate) BETWEEN 1 AND 4)
        AS tellnum_digits_1_to_4,
    COUNT(*) FILTER (WHERE LENGTH(numeric_phone_candidate) BETWEEN 5 AND 8)
        AS tellnum_digits_5_to_8,
    COUNT(*) FILTER (WHERE LENGTH(numeric_phone_candidate) BETWEEN 9 AND 12)
        AS tellnum_digits_9_to_12,
    COUNT(*) FILTER (WHERE LENGTH(numeric_phone_candidate) BETWEEN 13 AND 15)
        AS tellnum_digits_13_to_15,
    COUNT(*) FILTER (
        WHERE LENGTH(numeric_phone_candidate) >= 10
          AND LENGTH(customer_phone_digits) >= 10
          AND RIGHT(numeric_phone_candidate, 10) = RIGHT(customer_phone_digits, 10)
    ) AS tellnum_matches_customer_last_ten_digits
FROM classified
"""


def audit(*, limit: int = 300, offsets: tuple[int, ...] = (0, 1000, 5000)) -> dict:
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    if not isinstance(offsets, tuple) or not offsets or len(offsets) > 3:
        raise ValueError("provide one to three offsets")
    if any(type(o) is not int or not 0 <= o <= 50000 for o in offsets):
        raise ValueError("offsets must be integers between 0 and 50000")
    samples = []
    for offset in offsets:
        with database.connect() as conn:
            row = conn.execute(SEMANTICS_SQL, (limit, offset)).fetchone()
        samples.append({"offset": offset, **dict(row)})
    return {
        "source": database.VIEW,
        "limit_per_offset": limit,
        "samples": samples,
        "cautions": [
            "Seconds-of-day and timezone correlations are hypotheses, not source definitions.",
            "Creation timestamps may lag call times because of ingestion or processing.",
            "Last-10-digit matches are comparisons, never proof of phone ownership.",
            "No raw call IDs, customer phone numbers, names, or transcripts are emitted.",
            "Samples are ordered by ID, not by call date."
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--offsets", default="0,1000,5000")
    args = parser.parse_args(argv)
    try:
        offsets = parse_offsets(args.offsets)
        result = audit(limit=args.limit, offsets=offsets)
    except ValueError:
        print("Invalid audit options", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Semantics audit failed: {type(exc).__name__} "
              f"SQLSTATE={getattr(exc, 'sqlstate', None) or 'unknown'}",
              file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
