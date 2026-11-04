"""Read-only source and isolated target preflight tests, synthetic only."""
from contextlib import contextmanager

import pytest

from server import odoo_mirror_preflight as preflight


def test_preflight_checks_role_and_source_without_mutations(monkeypatch):
    queries = []

    class Result:
        def __init__(self, item):
            self.item = item
        def fetchone(self):
            return self.item

    class Target:
        def execute(self, sql):
            queries.append(("target", sql))
            assert sql.lstrip().startswith("SELECT")
            return Result({
                "can_create_db": False,
                "can_create_schema_objects": False,
                "can_enable_sources": False,
            })

    class Source:
        def execute(self, sql):
            queries.append(("source", sql))
            assert sql.lstrip().startswith("SELECT")
            return Result({
                "db": "odoo", "role": "report_user", "read_only": "on",
            })

    @contextmanager
    def owned():
        yield Target()

    @contextmanager
    def source():
        yield Source()

    monkeypatch.setattr(preflight.target, "validate_staging_writer_config",
                        lambda: "fake-private-test-dsn")
    monkeypatch.setattr(preflight.target, "owned_connection", owned)
    monkeypatch.setattr(preflight.odoo, "connect", source)
    monkeypatch.setattr(preflight.full, "validate_schema",
                        lambda source: "write_date")
    monkeypatch.setattr(preflight.pilot, "local_status", lambda target: {
        "source_registered": False, "source_enabled": False,
        "local_records": 0, "local_revisions": 0,
    })
    result = preflight.preflight()
    assert result["fixed_source_fields"] == 37
    assert result["odoo_report_only"]
    assert result["writer_least_privilege"]
    assert not result["source_modified"] and not result["target_modified"]
    assert not result["mirror_enabled"]
    assert len(queries) == 2
    assert all("FROM public.vw_danix_call_info_report" not in statement
               for _, statement in queries)


def test_preflight_fails_closed_on_unsafe_source_or_writer(monkeypatch):
    access = {"source": 0}

    class Result:
        def __init__(self, data):
            self.data = data
        def fetchone(self):
            return self.data

    class Connection:
        def __init__(self, record):
            self.record = record
        def execute(self, sql):
            return Result(self.record)

    @contextmanager
    def owner():
        yield Connection({
            "can_create_db": True,
            "can_create_schema_objects": False,
            "can_enable_sources": False,
        })

    @contextmanager
    def source():
        access["source"] += 1
        yield Connection({
            "db": "odoo", "role": "postgres", "read_only": "off",
        })

    monkeypatch.setattr(preflight.target, "validate_staging_writer_config",
                        lambda: "synthetic")
    monkeypatch.setattr(preflight.target, "owned_connection", owner)
    monkeypatch.setattr(preflight.odoo, "connect", source)
    monkeypatch.setattr(preflight.pilot, "local_status", lambda target: {
        "source_registered": False, "source_enabled": False,
        "local_records": 0, "local_revisions": 0,
    })
    with pytest.raises(PermissionError, match="excess privileges"):
        preflight.preflight()
    assert access["source"] == 0

    @contextmanager
    def restricted_owner():
        yield Connection({
            "can_create_db": False,
            "can_create_schema_objects": False,
            "can_enable_sources": False,
        })

    monkeypatch.setattr(preflight.target, "owned_connection", restricted_owner)
    with pytest.raises(PermissionError, match="read-only Odoo"):
        preflight.preflight()
    assert access["source"] == 1


def test_preflight_cli_rejects_arguments_without_opening_source(monkeypatch, capsys):
    monkeypatch.setattr(preflight, "preflight",
                        lambda: pytest.fail("Must not be invoked"))
    assert preflight.main(["--write"]) == 2
    assert "FAILED" in capsys.readouterr().err
