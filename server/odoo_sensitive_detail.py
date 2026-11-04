"""Draft full-field detail reader for explicitly authorized Panadan principals.

Library-only: NO HTTP, MCP tool, credential loader or source Odoo connection.
Requires a distinct, unprivileged PG18 sensitive reader identity, a verified
per-user Odoo operator grant, active transcript/sensitive-call capabilities
and a durable SQLite audit BEFORE any detail SELECT. Default deny.
"""
from __future__ import annotations

import json

from .odoo_full_mirror_adapter import COLUMN_NAMES
from .odoo_local_reporting import SOURCE_KEY
from .security import Store, has_capability

DETAIL_VIEW = "panadan_ingest.sensitive_mirror_call_detail_v1"
SENSITIVE_DB_ROLE = "panadan_mirror_sensitive_reader"
MAX_DETAIL_BYTES = 2_000_000
REQUIRED_CAPABILITIES = ("calls:read", "calls:sensitive", "calls:transcript:read")


def _connection_guard(conn):
    row = conn.execute(
        "SELECT current_database() AS db, current_user AS role, "
        "current_setting('server_version_num') AS version"
    ).fetchone()
    if (not row or row["db"] not in ("panadan_ci", "panadan")
            or row["role"] != SENSITIVE_DB_ROLE
            or not 180000 <= int(row["version"]) < 190000):
        raise PermissionError("Dedicated restricted PG18 sensitive role required")


def _call_id(value: int) -> int:
    if type(value) is not int or not 1 <= value <= 999_999_999:
        raise ValueError("Invalid source call ID")
    return value


def _validated_detail(row: dict, *, expected_id: int, permitted: list[int]) -> dict:
    """Refuse malformed or unexpectedly expanded sensitive source envelopes."""
    if (type(row.get("call_id")) is not int
            or row["call_id"] != expected_id
            or type(row.get("operator_id")) is not int
            or row["operator_id"] not in permitted):
        raise ValueError("Inconsistent sensitive record identity")
    variants = row.get("source_rows")
    if (not isinstance(variants, list) or not 1 <= len(variants) <= 100
            or type(row.get("source_row_count")) is not int
            or row["source_row_count"] != len(variants)):
        raise ValueError("Invalid sensitive record group")
    expected = set(COLUMN_NAMES)
    for variant in variants:
        if (not isinstance(variant, dict)
                or set(variant) != expected
                or type(variant["id"]) is not int
                or variant["id"] != expected_id
                or type(variant["vw_danix_base_info_users"]) is not int
                or variant["vw_danix_base_info_users"] != row["operator_id"]):
            raise ValueError("Invalid sensitive record schema")
    if len(json.dumps(variants, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")) > MAX_DETAIL_BYTES:
        raise ValueError("Sensitive record exceeds bounded detail size")
    # Include the source variants in full, including any conflicting joined
    # analyses. Never manufacture an authoritative winner.
    return {
        "call_id": expected_id,
        "operator_id": row["operator_id"],
        "revision_no": row["revision_no"],
        "source_row_count": len(variants),
        "source_rows": variants,
    }


def _read_detail(conn, *, call_id: int, permitted: list[int]) -> dict | None:
    _connection_guard(conn)
    if not permitted:
        raise PermissionError("No verified source operator scope")
    row = conn.execute(
        "SELECT call_id,operator_id,source_row_count,revision_no,source_rows "
        f"FROM {DETAIL_VIEW} "
        "WHERE source_key=%s AND operator_id=ANY(%s) AND call_id=%s LIMIT 1",
        (SOURCE_KEY, permitted, call_id),
    ).fetchone()
    if not row:
        return None
    return _validated_detail(dict(row), expected_id=call_id, permitted=permitted)


def _sqlite_store(auth_store):
    # An auth-backend migration must implement equivalent audited semantics,
    # rather than implicitly treating a PG staging store as the same authority.
    if not isinstance(auth_store, Store):
        raise PermissionError("Reviewed SQLite auth authority required")


def get_sensitive_call_for_session(
    conn, auth_store, *, session_token: str, call_id: int,
) -> dict | None:
    """Admin-approved source operator scope + 3 sensitive capabilities."""
    call_id = _call_id(call_id)
    _sqlite_store(auth_store)
    if not isinstance(session_token, str) or not 1 <= len(session_token) <= 256:
        raise PermissionError("Authenticated browser session required")
    session = auth_store.session(session_token)
    if not session or not all(has_capability(session, cap)
                              for cap in REQUIRED_CAPABILITIES):
        raise PermissionError("Sensitive-call and transcript access required")
    # Audit is committed before SQL. A failure to write the audit blocks data.
    permitted = auth_store.authorize_sensitive_mirror_attempt(
        user_id=session["user_id"], call_id=call_id, surface="dashboard",
    )
    return _read_detail(conn, call_id=call_id, permitted=permitted)


def get_sensitive_call_for_token(
    conn, auth_store, *, token: str, call_id: int,
) -> dict | None:
    """Only api:sensitive tokens. MCP reads deliberately NOT supported yet."""
    call_id = _call_id(call_id)
    _sqlite_store(auth_store)
    if not isinstance(token, str) or not 1 <= len(token) <= 256:
        raise PermissionError("Sensitive API token required")
    if not all(auth_store.verify_token(token, "api:sensitive", capability)
               for capability in REQUIRED_CAPABILITIES):
        raise PermissionError("Sensitive-call and transcript token scope required")
    actor = auth_store.actor_for_token(token, "api:sensitive")
    if type(actor) is not int or actor <= 0:
        raise PermissionError("Active sensitive token owner required")
    permitted = auth_store.authorize_sensitive_mirror_attempt(
        user_id=actor, call_id=call_id, surface="api",
    )
    return _read_detail(conn, call_id=call_id, permitted=permitted)
