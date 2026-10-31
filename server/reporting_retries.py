"""Bounded retry for idempotent SELECT-only reporting calls.

Only connection-level failures are retried. Never retry SQL errors, auth,
validation, cancellations or user-initiated writes. No customer data is cached.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

import psycopg

T = TypeVar("T")
RETRY_DELAY_SECONDS = 0.35


def is_transient_connection_failure(error: Exception) -> bool:
    code = getattr(error, "sqlstate", None)
    if isinstance(code, str) and (code.startswith("08") or code in ("57P01", "57P02", "57P03")):
        return True
    # A PostgreSQL exception with a non-connection SQLSTATE must not be retried.
    if code:
        return False
    # psycopg ConnectionTimeout subclasses OperationalError on most releases.
    return isinstance(error, psycopg.OperationalError)


def read_with_retry(operation: Callable[[], T], *, sleep: Callable[[float], None] = time.sleep) -> T:
    """Try at most twice; let the final sanitized route error handler respond."""
    try:
        return operation()
    except Exception as exc:
        if not is_transient_connection_failure(exc):
            raise
    sleep(RETRY_DELAY_SECONDS)
    return operation()
