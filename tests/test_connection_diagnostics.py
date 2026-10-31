"""Tests for connection stage diagnostics, using fake sockets and DB."""
from contextlib import contextmanager

from server import connection_diagnostics as diag


class FakeSocket:
    def __enter__(self):
        return self
    def __exit__(self, *_):
        pass


class FakeDB:
    def execute(self, sql):
        assert sql == "SELECT 1 AS connected"
        return self
    def fetchone(self):
        return {"connected": 1}


def test_diagnostic_can_identify_success(monkeypatch, capsys):
    monkeypatch.setenv("PGPORT", "15432")
    def fake_socket(addr, timeout):
        assert addr == ("127.0.0.1", 15432)
        assert timeout == 3
        return FakeSocket()
    monkeypatch.setattr(diag.socket, "create_connection", fake_socket)
    @contextmanager
    def connect():
        yield FakeDB()
    monkeypatch.setattr(diag.database, "connect", connect)
    assert diag.diagnose() == 0
    output = capsys.readouterr().out
    assert "OK: TCP accepted locally" in output
    assert "READ ONLY" in output


def test_diagnostic_reports_local_socket_failure_and_skips_db(monkeypatch, capsys):
    monkeypatch.setenv("PGPORT", "15432")
    def fail_socket(*_a, **_k):
        raise TimeoutError("private IP or DB password should not be logged")
    monkeypatch.setattr(diag.socket, "create_connection", fail_socket)
    monkeypatch.setattr(diag.database, "connect",
                        lambda: (_ for _ in ()).throw(AssertionError("unexpected DB connect")))
    assert diag.diagnose() == 2
    output = capsys.readouterr().out
    assert "local relay TCP unavailable" in output
    assert "private IP" not in output
    assert "password" not in output


def test_diagnostic_masks_remote_errors(monkeypatch, capsys):
    monkeypatch.setenv("PGPORT", "15432")
    monkeypatch.setattr(diag.socket, "create_connection",
                        lambda *_args, **_kwargs: FakeSocket())
    @contextmanager
    def connect():
        raise TimeoutError("private DB password and customer 09123456789")
        yield
    monkeypatch.setattr(diag.database, "connect", connect)
    assert diag.diagnose() == 2
    output = capsys.readouterr().out
    assert "TimeoutError" in output
    assert "09123456789" not in output
    assert "password and customer" not in output
