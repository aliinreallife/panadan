"""Synthetic-only reporting backend for the isolated Stytch authorization test.

No psycopg, Odoo imports, secrets, VPN, user rows or external database calls.
The exposed Panadan MCP tools and field policy are byte-identical snapshots
of the reviewed production modules; ONLY this reporting fixture is substituted.
"""
from __future__ import annotations

PUBLIC_COLUMNS = (
    "id", "CALLDATE", "tellstate", "tellside", "aicallinfostate",
    "voice_length", "possibility_of_sale_ai", "deal_value",
    "vw_danix_base_info_users_name",
)
DETAIL_COLUMNS = ("call_time",)
SENSITIVE_COLUMNS = (
    "call_id", "customername", "customertell", "outcome", "ai_recommendation",
    "summary", "transcription", "tell_state_desc", "create_date",
)
_SYNTHETIC_ROW = {
    "id": 73104,
    "CALLDATE": "2026-11-14",
    "aicallinfostate": "SYNTHETIC_UNCHECKED",
    "customername": "SYNTHETIC_SECRET_MUST_NOT_LEAK",
    "customertell": "SYNTHETIC_SECRET_MUST_NOT_LEAK",
    "transcription": "SYNTHETIC_SECRET_MUST_NOT_LEAK",
}
SYNTHETIC_ONLY = True


def list_calls(limit=10, offset=0, after=None, before=None, state=None,
               *, operator=None, operator_names=None, **_kw):
    if operator or operator_names or state not in (None, "SYNTHETIC_UNCHECKED"):
        return []
    if after and after.isoformat() > _SYNTHETIC_ROW["CALLDATE"]:
        return []
    if before and before.isoformat() < _SYNTHETIC_ROW["CALLDATE"]:
        return []
    return [dict(_SYNTHETIC_ROW)] if offset == 0 and limit > 0 else []


def get_call(call_id, sensitive=False):
    if sensitive:
        raise PermissionError("synthetic staging never serves sensitive records")
    return dict(_SYNTHETIC_ROW) if call_id == 73104 else None


def stats(after=None, before=None, *, operator=None, operator_names=None, **_kw):
    return {"total": 1, "sold_out": 0, "scored_calls": 0,
            "avg_ai_score": None, "avg_voice_length": None}


def statuses():
    return ["SYNTHETIC_UNCHECKED"]


def transcript_excerpt(*_args, **_kw):
    raise PermissionError("transcripts cannot be exposed in synthetic staging")
