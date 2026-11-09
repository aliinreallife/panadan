"""Shared, fail-closed field policy for existing Panadan reporting outputs.

Phase 1 supports ONLY the existing production reporting projection. The
37-column staging mirror has more fields; adding any of those requires an
independently reviewed and tested reporting read-path migration.

The UI is never the security boundary; each data-bearing surface must apply
this policy at the server. No SQL identifier is taken from an HTTP/MCP input.
"""
from __future__ import annotations

import json
from .database import PUBLIC_COLUMNS, DETAIL_COLUMNS, SENSITIVE_COLUMNS

REPORT_FIELDS = tuple(dict.fromkeys(
    PUBLIC_COLUMNS + DETAIL_COLUMNS + SENSITIVE_COLUMNS))
FIELD_SET = frozenset(REPORT_FIELDS)

# Known schema only. Restricted columns require explicit calls:sensitive,
# and raw transcription never becomes a normal MCP tool payload.
PRIVATE_FIELDS = frozenset(SENSITIVE_COLUMNS)
METRIC_DEPENDENCIES = {
    "total": frozenset({"id"}),
    "sold_out": frozenset({"aicallinfostate"}),
    "scored_calls": frozenset({"possibility_of_sale_ai"}),
    "avg_ai_score": frozenset({"possibility_of_sale_ai"}),
    "avg_voice_length": frozenset({"voice_length"}),
}
METRIC_FIELDS = frozenset().union(*METRIC_DEPENDENCIES.values())
REPORT_DESCRIPTIONS = {
    "id": ("شناسه تماس", "internal"),
    "CALLDATE": ("تاریخ تماس", "internal"),
    "tellstate": ("نوع تماس", "internal"),
    "tellside": ("جهت تماس", "internal"),
    "aicallinfostate": ("وضعیت هوش مصنوعی", "internal"),
    "voice_length": ("مدت صوت", "internal"),
    "possibility_of_sale_ai": ("امتیاز احتمال فروش", "confidential"),
    "deal_value": ("ارزش معامله", "confidential"),
    "vw_danix_base_info_users_name": ("کارشناس", "internal"),
    "call_time": ("ساعت تماس", "internal"),
    "call_id": ("شناسه خارجی تماس", "confidential"),
    "customername": ("نام مشتری", "confidential"),
    "customertell": ("شماره مشتری", "confidential"),
    "outcome": ("نتیجه تماس", "confidential"),
    "ai_recommendation": ("پیشنهاد هوش مصنوعی", "confidential"),
    "summary": ("خلاصه تماس", "confidential"),
    "transcription": ("متن خام مکالمه", "confidential"),
    "tell_state_desc": ("شرح وضعیت تماس", "confidential"),
    "create_date": ("زمان ثبت", "confidential"),
}
# Current capabilities have established defaults. Explicit field choices can
# REDUCE them, never expand them.
def capability_fields(caps: set[str] | frozenset[str]) -> frozenset[str]:
    result = set()
    if "calls:read" in caps:
        result.update(PUBLIC_COLUMNS + DETAIL_COLUMNS)
    if "calls:read" in caps and "calls:sensitive" in caps:
        result.update(SENSITIVE_COLUMNS)
    if "calls:read" in caps and "calls:transcript:read" in caps:
        result.add("transcription")  # redacted transcript tool only; never raw MCP
    if "metrics:read" in caps:
        result.update(METRIC_FIELDS)
    return frozenset(result & FIELD_SET)


def validate_fields(fields: list[str], caps: set[str] | frozenset[str]) -> tuple[str, ...]:
    if not isinstance(fields, list) or any(type(v) is not str for v in fields):
        raise ValueError("Invalid column selection")
    if len(fields) > len(REPORT_FIELDS) or len(set(fields)) != len(fields):
        raise ValueError("Duplicate or oversized column selection")
    if not set(fields) <= capability_fields(caps):
        raise ValueError("Columns exceed account permissions")
    return tuple(sorted(fields))


def effective_fields(caps: set[str] | frozenset[str], stored: str | None) -> frozenset[str]:
    available = capability_fields(caps)
    if stored is None:
        return available  # old accounts retain their existing effective access
    try:
        parsed = json.loads(stored)
        if not isinstance(parsed, list) or any(type(v) is not str for v in parsed):
            return frozenset()
        if len(parsed) != len(set(parsed)) or not set(parsed) <= FIELD_SET:
            return frozenset()
        return frozenset(parsed) & available
    except (TypeError, ValueError):
        return frozenset()


def project_call(row: dict | None, fields: frozenset[str] | set[str]) -> dict | None:
    if row is None:
        return None
    return {k: value for k, value in row.items() if k in fields and k in FIELD_SET}


def project_metrics(row: dict, fields: frozenset[str] | set[str]) -> dict:
    return {key: value for key, value in row.items()
            if key in METRIC_DEPENDENCIES
            and METRIC_DEPENDENCIES[key] <= fields}


def permitted_fields_for_capability(
    fields: frozenset[str], capability: str
) -> frozenset[str]:
    if capability == "calls:read":
        # Even a confidential-data grant does not make MCP summaries
        # sensitive. A separate audited tool is required for transcripts.
        return fields & frozenset(PUBLIC_COLUMNS + DETAIL_COLUMNS)
    if capability == "metrics:read":
        return fields & METRIC_FIELDS
    return frozenset()


def field_catalog() -> list[dict]:
    return [
        {"id": name, "label": REPORT_DESCRIPTIONS[name][0],
         "category": REPORT_DESCRIPTIONS[name][1],
         "requires": "calls:sensitive" if name in PRIVATE_FIELDS
                     else "calls:read or metrics:read"}
        for name in REPORT_FIELDS
    ]


def explain_field(
    field: str, user_fields: frozenset[str],
    approved_fields: frozenset[str], effective: frozenset[str]
) -> dict:
    """Self-only policy explanation. Does not enumerate records or people."""
    if field not in FIELD_SET:
        return {"allowed": False, "reason": "unknown_or_unavailable"}
    if field in effective:
        return {"allowed": True, "reason": "allowed"}
    if field not in user_fields:
        reason = "needs_admin_grant"
    elif field not in approved_fields:
        reason = "needs_user_consent"
    else:
        reason = "not_exposable"
    return {"allowed": False, "reason": reason,
            "field": field, "label": REPORT_DESCRIPTIONS[field][0]}
