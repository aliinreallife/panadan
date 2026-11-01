"""PostgreSQL 18 proof that locally generated SCRAM verifiers authenticate.

Only runs with the disposable panadan_ci loopback test DSN and explicit opt-in.
Never connects to Odoo or to the persistent Panadan-owned database.
"""
import os

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
import pytest

from tools.scram_secret import verifier


def test_locally_generated_scram_verifier_authenticates_in_postgres18():
    dsn = os.environ.get("PANADAN_PLATFORM_TEST_DSN")
    if not dsn:
        pytest.skip("No synthetic PostgreSQL DSN")
    cfg = conninfo_to_dict(dsn)
    if (cfg.get("dbname") != "panadan_ci"
            or cfg.get("host") not in ("127.0.0.1", "localhost")
            or os.environ.get("PANADAN_PLATFORM_TEST_ALLOW_RESET") != "YES"):
        pytest.fail("Refusing SCRAM test against a non-disposable database")

    role = "panadan_scram_test"
    raw = "d" * 64  # Public, synthetic test credential only.
    hashed = verifier(raw.encode("ascii"), bytes(range(16)))
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
            sql.Identifier(role), sql.Literal(hashed)))
        try:
            admin.execute(sql.SQL("GRANT CONNECT ON DATABASE panadan_ci TO {}").format(
                sql.Identifier(role)))
            def connect_as(password):
                return psycopg.connect(
                    host=cfg["host"], port=cfg.get("port", "5432"),
                    dbname="panadan_ci", user=role, password=password,
                    connect_timeout=5, autocommit=True,
                )
            with connect_as(raw) as reader:
                assert reader.execute("SELECT current_user").fetchone()[0] == role
            with pytest.raises(psycopg.OperationalError):
                with connect_as("incorrect_synthetic_password"):
                    pass
        finally:
            admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
