"""Small, deterministic input guards for bounded Panadan MCP reads.

Keep errors non-sensitive: never echo report values, SQL or bearer tokens.
The underlying reporting database remains parameterized and read-only.
"""
from __future__ import annotations

from datetime import date
import re


class MCPInputError(ValueError):
    def __init__(self, field: str, hint: str):
        super().__init__(hint)
        self.field, self.hint = field, hint

    def response(self) -> dict:
        return {"error": "invalid_argument", "field": self.field, "hint": self.hint}


def iso_date(value: str, field: str, *, required: bool = False) -> date | None:
    if value == "" and not required:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise MCPInputError(field, "Use an ISO calendar date in YYYY-MM-DD format.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise MCPInputError(field, "Use a valid calendar date in YYYY-MM-DD format.") from exc


def date_window(after: str, before: str, *, required: bool = False,
                max_days: int | None = None) -> tuple[date | None, date | None]:
    first = iso_date(after, "after", required=required)
    last = iso_date(before, "before", required=required)
    if first is not None and last is not None:
        if first > last:
            raise MCPInputError("date_range", "after must be on or before before.")
        if max_days and (last - first).days + 1 > max_days:
            raise MCPInputError("date_range", f"Choose at most {max_days} calendar days.")
    return first, last


def page(limit: int, offset: int) -> tuple[int, int]:
    if type(limit) is not int or not 1 <= limit <= 100:
        raise MCPInputError("limit", "Choose a page size from 1 to 100.")
    if type(offset) is not int or not 0 <= offset <= 10000:
        raise MCPInputError("offset", "Choose an offset from 0 to 10000.")
    return limit, offset


def optional_text(value: str, field: str, *, max_length: int) -> str:
    if not isinstance(value, str) or len(value) > max_length or "\x00" in value:
        raise MCPInputError(field, f"Use at most {max_length} characters.")
    return value


def compare_values(previous: dict, current: dict) -> dict:
    """Only compare metrics that already survived per-field projection."""
    changes = {}
    for key in sorted(previous.keys() & current.keys()):
        before, after = previous[key], current[key]
        if (isinstance(before, (int, float)) and not isinstance(before, bool)
                and isinstance(after, (int, float)) and not isinstance(after, bool)):
            changes[key] = {
                "absolute": round(after - before, 2),
                "percent": round(100 * (after - before) / abs(before), 2)
                           if before != 0 else None,
            }
    return changes
