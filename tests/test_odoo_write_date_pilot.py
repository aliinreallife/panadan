"""Write-date/guard tests. No real Odoo, VPN, or customer-data connections."""
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from server import odoo_sync_adapter as a
from server import odoo_sync_pilot as pilot


T = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)
MARKER = "write_date"


class Result:
    def __init__(self, rows=(), row=None):
        self.rows = list(rows)
        self.row = row
    def fetchall(self): return self.rows
    def fetchone(self): return self.row


def sample(call_id, updated=T):
    return {
        "id": call_id,
        "CALLDATE": date(2026, 11, 3),
        "tellstate": "FollowUp",
        "tellside": "IntoOut",
        "aicallinfostate": "Unchecked",
        "voice_length": Decimal("180.5"),
        "possibility_of_sale_ai": Decimal("42.0"),
        "deal_value": Decimal("0"),
        MARKER: updated.replace(tzinfo=None),
    }


class Source:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.calls = []
    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if sql == a.SCHEMA_SQL:
            return Result(rows=[
                {"column_name": n, "data_type":
                 "integer" if n == "id" else
                 "timestamp without time zone" if n == MARKER else "text"}
                for n in a.DATA_COLUMNS + (MARKER,)
            ])
        if sql == a.ID_SQL_BY_MARKER[MARKER]:
            after, limit = params
            return Result(rows=sorted(
                (r for r in self.rows if r["id"] > after),
                key=lambda row: row["id"])[:limit])
        if sql == a.CHANGE_SQL_BY_MARKER[MARKER]:
            lo, hi, at, id_at, limit = params
            return Result(rows=sorted(
                (r for r in self.rows if lo <= r[MARKER] <= hi
                 and (r[MARKER], r["id"]) > (at, id_at)),
                key=lambda row: (row[MARKER], row["id"]))[:limit])
        if sql == a.SOURCE_CLOCK_SQL:
            return Result(row={"source_now": T + timedelta(minutes=7)})
        raise AssertionError("Unexpected source SQL")


def test_write_date_schema_and_payload_have_only_allowlisted_fields():
    source = Source([sample(5)])
    assert a.validate_schema(source, mode="utc_naive") == MARKER
    events = a.read_id_page(source, after_id=0, limit=100,
                            mode="utc_naive", marker=MARKER)
    assert [x[0] for x in events] == [5]
    assert events[0][2].payload[MARKER] == a._iso(T)
    assert "customername" not in events[0][2].payload
    assert "transcription" not in a.ID_SQL_BY_MARKER[MARKER]
    assert "customertell" not in a.CHANGE_SQL_BY_MARKER[MARKER]
    assert all(sql.lstrip().upper().startswith("SELECT") for sql, _ in source.calls)


def test_write_date_rejects_wrong_timestamp_mode_and_null_values():
    source = Source([sample(5)])
    with pytest.raises(RuntimeError, match="type"):
        a.validate_schema(source, mode="timestamptz")
    source.rows[0][MARKER] = None
    with pytest.raises(ValueError, match="timestamp"):
        a.read_id_page(source, after_id=0, mode="utc_naive", marker=MARKER)


def test_write_date_keyset_stable_for_timestamp_ties_and_old_changes():
    source = Source([sample(i) for i in range(1, 6)])
    pages, position = [], (T, 0)
    for _ in range(3):
        got = a.read_change_page(
            source, lower=T, upper=T + timedelta(minutes=1),
            position=position, limit=2, mode="utc_naive", marker=MARKER)
        pages.extend(i for i, _, _ in got)
        if not got or len(got) < 2:
            break
        position = got[-1][1], got[-1][0]
    assert pages == [1, 2, 3, 4, 5]
    assert " OFFSET " not in a.ID_SQL_BY_MARKER[MARKER].upper()
    assert " OFFSET " not in a.CHANGE_SQL_BY_MARKER[MARKER].upper()


def approved(command="seed"):
    return SimpleNamespace(command=command, mode="utc_naive",
                           batch_size=100, max_pages=1,
                           ack_source_contract=True, ack_retention=True,
                           ack_copy=True)


@pytest.mark.parametrize("field", pilot.REQUIRED_ACKS)
def test_pilot_refuses_any_missing_approval(field):
    opts = approved()
    setattr(opts, field, False)
    with pytest.raises(ValueError, match="approval|Write blocked|required"):
        pilot.require_approval(opts)


@pytest.mark.parametrize("dsn", [
    "postgresql://panadan_owner:secret@panadan-auth-postgres:5432/panadan",
    "postgresql://panadan_ingest_writer:secret@192.168.3.9:5432/odoo",
    "postgresql://panadan_ingest_writer:secret@panadan-auth-postgres:5432/odoo",
    "postgresql://panadan_ingest_writer:secret@panadan-auth-postgres:5432/panadan?hostaddr=192.168.3.9",
    "postgresql://panadan_ingest_writer:secret@panadan-auth-postgres:5432/panadan?options=-c%20statement_timeout%3D0",
])
def test_wrong_target_credentials_identity_and_redirection_rejected(monkeypatch, dsn):
    for name in ("PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE", "PGOPTIONS", "PGPASSFILE"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValueError):
        pilot.validate_owned_dsn(dsn)


def test_private_target_dsn_file_permissions_and_no_dsn_logging(tmp_path, monkeypatch, capsys):
    dsn = "postgresql://panadan_ingest_writer:TOP_SECRET@panadan-auth-postgres:5432/panadan?sslmode=prefer"
    file = tmp_path / "owned.pguri"
    file.write_text(dsn)
    file.chmod(0o644)
    monkeypatch.setenv(pilot.DSN_FILE_ENV, str(file))
    for name in ("PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE", "PGOPTIONS", "PGPASSFILE"):
        monkeypatch.delenv(name, raising=False)
    assert pilot.main(["status"]) == 2
    assert "TOP_SECRET" not in capsys.readouterr().err
    file.chmod(0o600)
    assert pilot._read_target_dsn() == dsn
    file.unlink()
    file.symlink_to(tmp_path / "missing")
    with pytest.raises(ValueError):
        pilot._read_target_dsn()


def test_readonly_preview_never_calls_owned_connection(monkeypatch):
    from contextlib import contextmanager

    @contextmanager
    def source():
        yield Source([sample(2), sample(1)])
    monkeypatch.setattr(pilot.database, "connect", source)
    monkeypatch.setattr(pilot, "owned_connection",
                        lambda: pytest.fail("Preview must never contact target PG"))
    output = pilot.preview(mode="utc_naive", limit=2)
    assert output["marker"] == MARKER
    assert output["rows_examined"] == 2
    assert output["target_unchanged"]
    with pytest.raises(ValueError):
        pilot.preview(mode="utc_naive", limit=201)


def test_no_apply_before_approval_even_when_connections_are_available(monkeypatch):
    monkeypatch.setattr(pilot, "owned_connection",
                        lambda: pytest.fail("Do not connect before approvals"))
    opts = approved("backfill")
    opts.ack_copy = False
    with pytest.raises(ValueError, match="Write blocked"):
        pilot.apply(opts)



def test_combined_cycle_serially_polls_both_streams(monkeypatch):
    """No real database; combined cycle never executes streams concurrently."""
    from contextlib import contextmanager

    phases = []

    @contextmanager
    def target():
        phases.append("target")
        yield object()

    @contextmanager
    def lock(_):
        phases.append("lock")
        yield

    @contextmanager
    def source():
        phases.append("source")
        yield object()

    monkeypatch.setattr(pilot, "owned_connection", target)
    monkeypatch.setattr(pilot, "exclusive_pilot", lock)
    monkeypatch.setattr(pilot.database, "connect", source)
    monkeypatch.setattr(pilot.adapter, "validate_schema",
                        lambda src, *, mode: MARKER)

    def backfill(*args, **kwargs):
        phases.append("backfill")
        return SimpleNamespace(examined=2, changed=2, skipped=0, has_more=False)

    def changes(*args, **kwargs):
        phases.append("updates")
        return SimpleNamespace(examined=1, changed=1, skipped=0, has_more=False)

    monkeypatch.setattr(pilot.sync, "poll_id_page", backfill)
    monkeypatch.setattr(pilot.sync, "poll_update_page", changes)
    out = pilot.apply(approved("sync-once"))
    assert phases == ["target", "lock", "source", "backfill", "updates"]
    assert [row["operation"] for row in out] == ["backfill", "updates"]
    assert [row["changed"] for row in out] == [2, 1]


def test_session_lock_rejects_concurrent_worker():
    class Busy:
        def execute(self, sql, params):
            assert "pg_try_advisory_lock" in sql
            assert params == pilot.LOCK_KEYS
            return Result(row={"ok": False})
    with pytest.raises(ValueError, match="already active"):
        with pilot.exclusive_pilot(Busy()):
            pytest.fail("Should not enter critical section")


def test_app_does_not_silently_enable_any_schedule():
    from pathlib import Path
    script = Path("server/odoo_sync_pilot.py").read_text()
    assert "APScheduler" not in script and "cron" not in script.lower()
    assert "enabled = TRUE" not in script
    assert "DELETE FROM" not in script
