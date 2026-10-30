"""Read-only enforcement tests; no VPN or customer reporting data is used."""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from server import database, mcp_tools
from server import readonly_audit


class Connection:
    def __init__(self):
        self.commands = []
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return None
    @contextmanager
    def transaction(self):
        yield
    def execute(self, sql, *_):
        self.commands.append(sql)
        return self
    def fetchall(self):
        return []
    def fetchone(self):
        return {}


@pytest.mark.parametrize("operation", [
    lambda: database.list_calls(),
    lambda: database.get_call(123),
    lambda: database.get_call(123, sensitive=True),
    lambda: database.transcript_excerpt(123,6000,6000),
    lambda: database.stats(),
    lambda: database.statuses(),
    lambda: database.call_types(),
    lambda: database.operators(),
    lambda: database.health(),
])
def test_every_reporting_operation_is_select_only_and_read_only(monkeypatch, operation):
    connection = Connection()
    monkeypatch.setenv("PGUSER", "synthetic-report-role")
    monkeypatch.setenv("PGPASSWORD", "not-a-real-secret")
    monkeypatch.setattr(database.psycopg, "connect", lambda **kwargs: connection)
    operation()
    assert connection.commands[0] == "SET TRANSACTION READ ONLY"
    assert len(connection.commands) == 2
    assert connection.commands[1].lstrip().upper().startswith("SELECT ")
    assert not any(token in connection.commands[1].upper() for token in (
        "INSERT INTO", "UPDATE PUBLIC.", "DELETE FROM", "DROP TABLE", "ALTER TABLE",
    ))


def test_only_non_sensitive_read_only_mcp_tools_exist():
    names = {tool.name for tool in mcp_tools.mcp._tool_manager.list_tools()}
    assert names == {
        "list_recent_calls", "get_call_summary", "get_call_metrics", "get_available_states",
        "get_redacted_call_transcript"
    }


def test_rest_reporting_routes_offer_get_only():
    from server.main import app
    for route in app.routes:
        path = getattr(route, "path", "")
        if path.startswith("/api/v1/") or path.startswith("/dashboard/data") or path.startswith("/dashboard/ai/") or path == "/dashboard/metrics":
            assert set(route.methods or ()) <= {"GET", "HEAD", "OPTIONS"}, path


@pytest.fixture
def audit_row():
    return {
        "role": "synthetic-report-role",
        "transaction_read_only": True,
        "can_select_report": True,
        "can_insert_report": False,
        "can_update_report": False,
        "can_delete_report": False,
        "can_truncate_report": False,
        "can_create_database_objects": False,
        "can_create_temporary_objects": True,
    }


def run_audit(monkeypatch, audit_row, *, schema_count=0, writable_relations=0):
    class AuditConnection(Connection):
        def __init__(self):
            super().__init__()
            self.answers = [
                audit_row,
                {"writable_schemas": schema_count},
                {"writable_relations": writable_relations},
            ]
        def fetchone(self):
            return self.answers.pop(0)
    conn = AuditConnection()
    @contextmanager
    def mock_connect():
        yield conn
    monkeypatch.setattr(readonly_audit.database, "connect", mock_connect)
    return readonly_audit.inspect_permissions(), conn


def test_clean_audit_passes_without_reading_call_rows(monkeypatch, audit_row):
    report, conn = run_audit(monkeypatch, audit_row)
    assert report["strict_report_read_only"] is True
    assert report["blocking"] == []
    assert report["advisories"]  # TEMP is an explicit advisory
    assert len(conn.commands) == 3
    assert all(sql.lstrip().upper().startswith("SELECT ") for sql in conn.commands)
    assert not any("FROM public.vw_danix_call_info_report" in sql for sql in conn.commands)


@pytest.mark.parametrize("change", [
    {"can_insert_report": True},
    {"can_update_report": True},
    {"can_create_database_objects": True},
    {"transaction_read_only": False},
    {"can_select_report": False},
])
def test_audit_fails_closed_for_privilege_gaps(monkeypatch, audit_row, change):
    report, _ = run_audit(monkeypatch, audit_row | change)
    assert report["strict_report_read_only"] is False
    assert report["blocking"]


def test_audit_detects_inherited_schema_or_relation_write(monkeypatch, audit_row):
    report, _ = run_audit(monkeypatch, audit_row, schema_count=1, writable_relations=2)
    assert not report["strict_report_read_only"]
    assert len(report["blocking"]) == 2



def test_audit_catalog_queries_do_not_use_invalid_multicharacter_escape():
    """PostgreSQL standard_conforming_strings makes ESCAPE '\\\\' two chars."""
    for query in (readonly_audit.SCHEMA_SQL, readonly_audit.RELATION_SQL):
        assert "LEFT(n.nspname, 3) <> 'pg_'" in query
        assert " ESCAPE " not in query
        assert query.lstrip().upper().startswith("SELECT ")


def test_database_audit_error_reports_only_exception_type_and_sqlstate(monkeypatch, capsys):
    class SyntheticDbError(RuntimeError):
        sqlstate = "22025"
    def bad_inspection():
        raise SyntheticDbError("sensitive connection details")
    monkeypatch.setattr(readonly_audit, "inspect_permissions", bad_inspection)
    assert readonly_audit.main() == 2
    output = capsys.readouterr().err
    assert "SyntheticDbError" in output and "SQLSTATE=22025" in output
    assert "sensitive connection details" not in output
