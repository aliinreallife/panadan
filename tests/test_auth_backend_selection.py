"""Explicit staged runtime selector: no real PostgreSQL, Odoo or VPN."""
import os

import pytest

from server.auth_store import create_auth_store, validate_staging_dsn
from server.security import Store
from server.security_pg import PgStore

FAKE_DSN = "postgresql://panadan_ci:synthetic-testing-only@127.0.0.1:5432/panadan_ci"
ENABLED = {
    "PANADAN_AUTH_BACKEND": "postgres-staging",
    "PANADAN_AUTH_STAGING_ENABLE": "YES",
    "PANADAN_AUTH_STAGING_ISOLATED": "YES",
    "PANADAN_AUTH_STAGING_DSN": FAKE_DSN,
}


def test_sqlite_stays_default_even_if_pg_settings_are_present(tmp_path):
    store = create_auth_store({
        "PANADAN_AUTH_DB": str(tmp_path/"sqlite.sqlite"),
        **{key: val for key,val in ENABLED.items() if key != "PANADAN_AUTH_BACKEND"},
    })
    assert isinstance(store, Store)
    assert (tmp_path/"sqlite.sqlite").exists()


def test_explicit_staging_selector_constructs_pg_without_connecting(monkeypatch):
    for name in ("PGHOST","PGHOSTADDR","PGSERVICE","PGSERVICEFILE",
                 "PGOPTIONS","PGDATABASE","PGUSER","PGPORT"):
        monkeypatch.delenv(name, raising=False)
    store = create_auth_store(ENABLED)
    assert isinstance(store, PgStore)


@pytest.mark.parametrize("override", [
    {"PANADAN_AUTH_STAGING_ENABLE": "no"},
    {"PANADAN_AUTH_STAGING_ENABLE": ""},
    {"PANADAN_AUTH_STAGING_ISOLATED": "no"},
    {"PANADAN_AUTH_STAGING_DSN": ""},
    {"PANADAN_AUTH_BACKEND": "postgres"},
    {"PANADAN_AUTH_BACKEND": "auto"},
])
def test_postgresql_mode_requires_exact_reviewed_opt_in(override):
    with pytest.raises(ValueError):
        create_auth_store(ENABLED | override)


@pytest.mark.parametrize("dsn", [
    "postgresql://panadan_ci:synthetic@192.168.3.9:5432/panadan_ci",
    "postgresql://panadan_ci:synthetic@db.example.test:5432/panadan_ci",
    "postgresql://panadan_ci:synthetic@localhost:5432/panadan_ci",
    "postgresql://panadan_owner:synthetic@127.0.0.1:5432/panadan",
    "postgresql://report_user:synthetic@127.0.0.1:5432/odoo",
    "postgresql://panadan_ci:synthetic@127.0.0.1/panadan_ci",
    "postgresql://panadan_ci:synthetic@127.0.0.1:5432/panadan_ci?hostaddr=192.168.3.9",
    "postgresql://panadan_ci:synthetic@127.0.0.1:5432/panadan_ci?service=prod",
    "postgresql://panadan_ci:synthetic@127.0.0.1:5432/panadan_ci?options=-c%20search_path%3Dpublic",
    "postgresql://panadan_ci:synthetic@127.0.0.1,192.168.3.9:5432/panadan_ci",
    "postgresql://panadan_ci:synthetic@127.0.0.1:0/panadan_ci",
    "not-a-dsn",
])
def test_rejects_non_disposable_remote_or_libpq_redirects(dsn):
    with pytest.raises(ValueError):
        validate_staging_dsn(dsn)


@pytest.mark.parametrize("key", [
    "PGHOST", "PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE",
    "PGOPTIONS", "PGDATABASE", "PGUSER", "PGPORT",
])
def test_rejects_inherited_libpq_host_and_service_overrides(monkeypatch,key):
    monkeypatch.setenv(key,"redirect")
    with pytest.raises(ValueError):
        validate_staging_dsn(FAKE_DSN)
