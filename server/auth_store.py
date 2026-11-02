"""Explicit, isolated PostgreSQL authentication runtime selector for CI/staging.

Production remains SQLite. The PostgreSQL branch is constrained to an
operator-designated disposable loopback panadan_ci database, never the
Panadan-owned production database or source Odoo. No implicit fallback
between backends: failure must stop startup, not fork auth state.
"""
from __future__ import annotations

import os
import re
from collections.abc import Mapping

from psycopg.conninfo import conninfo_to_dict

from .security import Store


def validate_staging_dsn(dsn: str) -> None:
    """Require an explicit, single-host, disposable local test DSN."""
    if not isinstance(dsn, str) or not dsn or len(dsn) > 2048:
        raise ValueError("Explicit disposable PostgreSQL staging DSN required")
    try:
        opts = conninfo_to_dict(dsn)
    except Exception as exc:
        raise ValueError("Invalid disposable PostgreSQL staging DSN") from None

    # An allowlist prevents libpq's service, hostaddr, multi-host or options
    # from redirecting a nominal 127.0.0.1 DSN elsewhere.
    allowed = {"host", "port", "dbname", "user", "password",
               "connect_timeout", "sslmode", "application_name"}
    if set(opts) - allowed:
        raise ValueError("Unsupported PostgreSQL staging DSN option")
    if (opts.get("host") not in ("127.0.0.1", "localhost")
            or opts.get("dbname") != "panadan_ci"
            or opts.get("user") != "panadan_ci"
            or not opts.get("password")):
        raise ValueError("Only the disposable loopback panadan_ci role/database is permitted")
    port = opts.get("port", "")
    if not re.fullmatch(r"[0-9]{2,5}", port) or not 1 <= int(port) <= 65535:
        raise ValueError("An explicit disposable PostgreSQL TCP port is required")
    # "localhost" could resolve to a system-managed socket, or an IPv6
    # endpoint. Use numeric IPv4 so CI/test host is unambiguous.
    if opts["host"] != "127.0.0.1":
        raise ValueError("Use explicit IPv4 loopback for the disposable test")
    # Reject inherited libpq redirect/override variables, which libpq may
    # honor when keys aren't explicitly present in the DSN.
    for name in ("PGHOST", "PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE",
                 "PGOPTIONS", "PGDATABASE", "PGUSER", "PGPORT"):
        if os.environ.get(name):
            raise ValueError("Unexpected libpq environment configuration for isolated staging")


def create_auth_store(env: Mapping[str, str] | None = None):
    """Select SQLite normally or isolated PG18 for explicit staging tests."""
    if env is None:
        env = os.environ
    mode = env.get("PANADAN_AUTH_BACKEND", "sqlite")
    if mode == "sqlite":
        # An explicit DSN is ignored in SQLite mode; there is no partial
        # dual-write or emergency fallback to another auth authority.
        return Store(env.get("PANADAN_AUTH_DB", "/data/auth.sqlite"))
    if mode != "postgres-staging":
        raise ValueError("Unknown Panadan auth backend (refusing startup)")
    if env.get("PANADAN_AUTH_STAGING_ENABLE") != "YES":
        raise ValueError("PostgreSQL auth is staging-only and requires explicit opt-in")
    if env.get("PANADAN_AUTH_STAGING_ISOLATED") != "YES":
        raise ValueError("PostgreSQL auth staging must be isolated from production")
    dsn = env.get("PANADAN_AUTH_STAGING_DSN", "")
    validate_staging_dsn(dsn)
    # Delayed import avoids initializing any PG runtime in the default path.
    from .security_pg import PgStore
    return PgStore(dsn)
