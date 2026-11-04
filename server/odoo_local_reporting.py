"""Staging-only, explicitly operator-scoped reads from the sanitized PG18 mirror.

No Odoo/VPN connection, raw revision SELECT, secret lookup or FastAPI route.
The caller MUST obtain operator_ids from authenticated, verified server-side
authorization; user-supplied search filters are not an authorization source.
Until that mapping exists in all API/MCP/dashboard paths, do not cut over.
"""
from __future__ import annotations

from collections.abc import Sequence

SOURCE_KEY = "odoo_calls_full_v1"
MAX_OPERATOR_IDS = 200
MAX_PAGE_SIZE = 100

# No customer phone/name, transcript, raw free text, or arbitrary JSON payload.
_COLUMNS = (
    "call_id", "call_date", "operator_id", "source_row_count",
    "tellside", "tellstate", "aicallinfostate",
    "voice_length_text", "ai_sales_score",
)
_SELECT = ", ".join(_COLUMNS)
_VIEW = "panadan_ingest.safe_mirror_call_listing_v1"


def _scope(operator_ids: Sequence[int]) -> list[int]:
    if type(operator_ids) not in (list, tuple) or len(operator_ids) > MAX_OPERATOR_IDS:
        raise ValueError("Expected a bounded trusted operator scope")
    if any(type(x) is not int or not 1 <= x <= 999_999_999 for x in operator_ids):
        raise ValueError("Invalid operator scope")
    return sorted(set(operator_ids))


def _reader(conn):
    row = conn.execute(
        "SELECT current_database() AS db, current_user AS role, "
        "current_setting('server_version_num') AS version"
    ).fetchone()
    if (row is None or row["db"] not in ("panadan_ci", "panadan")
            or row["role"] != "panadan_report_reader"
            or not 180000 <= int(row["version"]) < 190000):
        raise ValueError("Restricted PG18 reporting connection required")


def list_calls(conn, *, operator_ids: Sequence[int], after_id: int = 0,
               limit: int = 50) -> list[dict]:
    """One bounded current-state page, restricted to trusted operator IDs.

    A source record with absent or ambiguous operator identity is NOT shown.
    A caller cannot request all records by passing an empty scope.
    """
    permitted = _scope(operator_ids)
    if type(after_id) is not int or after_id < 0:
        raise ValueError("Invalid listing cursor")
    if type(limit) is not int or not 1 <= limit <= MAX_PAGE_SIZE:
        raise ValueError("Invalid listing page size")
    _reader(conn)
    if not permitted:
        return []
    rows = conn.execute(
        f"SELECT {_SELECT} FROM {_VIEW} "
        "WHERE source_key = %s AND operator_id = ANY(%s) "
        "AND call_id > %s ORDER BY call_id ASC LIMIT %s",
        (SOURCE_KEY, permitted, after_id, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def get_call(conn, *, operator_ids: Sequence[int], call_id: int) -> dict | None:
    """Direct ID access also enforces operator scope; no raw detail returned."""
    permitted = _scope(operator_ids)
    if type(call_id) is not int or call_id <= 0:
        raise ValueError("Invalid call identity")
    _reader(conn)
    if not permitted:
        return None
    row = conn.execute(
        f"SELECT {_SELECT} FROM {_VIEW} "
        "WHERE source_key = %s AND operator_id = ANY(%s) "
        "AND call_id = %s LIMIT 1",
        (SOURCE_KEY, permitted, call_id),
    ).fetchone()
    return dict(row) if row else None


def count_calls(conn, *, operator_ids: Sequence[int]) -> int:
    """Aggregates obey the SAME scope as lists and by-ID lookup."""
    permitted = _scope(operator_ids)
    _reader(conn)
    if not permitted:
        return 0
    row = conn.execute(
        f"SELECT COUNT(*) AS n FROM {_VIEW} "
        "WHERE source_key = %s AND operator_id = ANY(%s)",
        (SOURCE_KEY, permitted),
    ).fetchone()
    return int(row["n"])
