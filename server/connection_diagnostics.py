"""Diagnose local relay and end-to-end PostgreSQL availability safely.

This reports only connection stages / exception *types* / SQLSTATE; no
credentials, connection URLs, customer records, or exception text are printed.
The PostgreSQL check uses the reporting client's enforced READ ONLY transaction.
"""
from __future__ import annotations

import os
import socket
import sys

from . import database


def diagnose() -> int:
    port = int(os.environ.get("PGPORT", "15432"))
    if not 1 <= port <= 65535:
        print("Invalid local relay port", file=sys.stderr)
        return 2

    print("[1/2] WSL -> localhost PostgreSQL relay")
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=3):
            pass
    except OSError as exc:
        print(f"FAIL: local relay TCP unavailable ({type(exc).__name__}).")
        print("Check Docker port mapping, compose.dev.yaml and pgrelay logs.")
        return 2
    print("OK: TCP accepted locally. This does NOT confirm access to PostgreSQL.")

    print("[2/2] End-to-end PostgreSQL SSL/auth/READ ONLY SELECT")
    try:
        with database.connect() as conn:
            row = conn.execute("SELECT 1 AS connected").fetchone()
        if not row or row["connected"] != 1:
            print("FAIL: unexpected test query result")
            return 2
    except Exception as exc:
        sqlstate = getattr(exc, "sqlstate", None) or "unknown"
        print(f"FAIL: {type(exc).__name__} SQLSTATE={sqlstate}")
        print("If VPN->PostgreSQL pg_isready also fails: investigate the VPN's")
        print("database host reachability / firewall / PostgreSQL listener.")
        print("If pg_isready succeeds: check TLS, credentials and DB grants")
        print("using local-only logs (do not share passwords).")
        return 2
    print("OK: PostgreSQL query completed with READ ONLY transaction.")
    return 0


if __name__ == "__main__":
    raise SystemExit(diagnose())
