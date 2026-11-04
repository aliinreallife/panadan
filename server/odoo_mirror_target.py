"""Select the existing owned writer or a *separate* isolated staging writer.

Default behavior is unchanged: the legacy guarded owned PG18 writer is used.
A staging override is allowed ONLY when separately enabled and points at a
loopback panadan_ci PG18 database. Never fall back after a failed staging
preflight. Source Odoo is always opened separately with read-only credentials.

Do not place DSNs, passwords, customer data or row identifiers in logs.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import os
import stat

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from . import odoo_sync_pilot as guarded

MODE_ENV = "PANADAN_FULL_MIRROR_TARGET_MODE"
STAGING_MODE = "isolated-staging"
STAGING_ACK = "PANADAN_FULL_MIRROR_STAGING_ISOLATED"
STAGING_DSN_FILE = "PANADAN_FULL_MIRROR_STAGING_WRITER_DSN_FILE"
_ALLOWED_DSN_FIELDS = frozenset({
    "host", "port", "dbname", "user", "password",
    "sslmode", "connect_timeout", "application_name",
})
_DSN_REDIRECT_ENV = (
    "PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE",
    "PGOPTIONS", "PGPASSFILE",
)


def validate_staging_writer_config(environ=None) -> str:
    """Validate local credentials without a network or SQL side effect.

    Return the DSN only to the caller creating a target connection.
    Reject production source and owned-production target DSNs by identity.
    """
    env = os.environ if environ is None else environ
    if (env.get(MODE_ENV) != STAGING_MODE
            or env.get(STAGING_ACK) != "YES"):
        raise ValueError("Full-mirror isolated staging mode requires explicit approval")
    if any(env.get(key) for key in _DSN_REDIRECT_ENV):
        raise ValueError("Unexpected PostgreSQL environment redirect")
    value = env.get(STAGING_DSN_FILE, "")
    if (not isinstance(value, str) or len(value) > 512
            or not value.startswith("/")
            or ".." in Path(value).parts):
        raise ValueError("Explicit absolute private staging writer DSN required")
    path = Path(value)
    try:
        meta = path.lstat()
        if (not stat.S_ISREG(meta.st_mode)
                or stat.S_IMODE(meta.st_mode) & 0o077
                or meta.st_uid not in (os.geteuid(), 0)
                or not 16 <= meta.st_size <= 4096):
            raise ValueError("Private staging writer DSN file required")
        dsn = path.read_text(encoding="utf-8").strip()
    except OSError:
        raise ValueError("Staging writer DSN file is unavailable") from None
    if "\n" in dsn or "\r" in dsn:
        raise ValueError("Staging writer DSN must contain one line")
    try:
        config = conninfo_to_dict(dsn)
    except Exception:
        raise ValueError("Invalid staging writer DSN") from None
    if (set(config) - _ALLOWED_DSN_FIELDS
            or config.get("host") != "127.0.0.1"
            or config.get("dbname") != "panadan_ci"
            or config.get("user") != "panadan_ingest_writer"
            or not config.get("password")
            or config.get("sslmode") not in ("prefer", "require", "verify-full")
            or not config.get("port", "").isdigit()
            or not 1 <= int(config["port"]) <= 65535):
        raise ValueError("Only the isolated loopback panadan_ci ingest writer is permitted")
    return dsn


@contextmanager
def owned_connection():
    """Use legacy owned writer by default, or tightly bounded stage target."""
    mode = os.environ.get(MODE_ENV)
    if mode is None or mode == "":
        with guarded.owned_connection() as conn:
            yield conn
        return
    if mode != STAGING_MODE:
        raise ValueError("Unsupported full-mirror target mode")
    dsn = validate_staging_writer_config()
    with psycopg.connect(
        dsn, row_factory=dict_row, autocommit=True, connect_timeout=5,
        options="-c statement_timeout=12000",
    ) as conn:
        row = conn.execute(
            "SELECT current_database() AS db, current_user AS role, "
            "current_setting('server_version_num') AS version"
        ).fetchone()
        if (not row or row["db"] != "panadan_ci"
                or row["role"] != "panadan_ingest_writer"
                or not 180000 <= int(row["version"]) < 190000):
            raise PermissionError("Staging target PostgreSQL identity mismatch")
        yield conn
