"""Synthetic-only read-only Odoo vs staging parity census tests."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
from types import SimpleNamespace
import io
from hashlib import sha256
import json
from pathlib import Path
import subprocess

import pytest

from server import odoo_full_mirror_adapter as full
from server import odoo_mirror_parity_stream as parity
from server import odoo_mirror_transfer as wire
from server.platform_ingest import _validate_events


def fake_row(identity: int, changed: str = "demo"):
    return {
        key: (identity if key == "id"
              else date(2026, 11, 5) if kind == "date"
              else datetime(2026, 11, 5, 12, 0) if kind == "timestamp without time zone"
              else 5 if kind == "integer"
              else 5.0 if kind == "double precision"
              else {"en_US": "example"} if kind == "jsonb"
              else changed if key == "outcome"
              else "example")
        for key, kind in full.COLUMN_TYPES
    }


class Result:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = list(rows or [])

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class Source:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, sql, params=None):
        if "current_setting('transaction_read_only')" in sql:
            return Result(row={"db": "odoo", "role": "report_user", "read_only": "on"})
        if sql == full.SCHEMA_SQL:
            return Result(rows=[
                {"column_name": n, "data_type": t, "is_nullable": "YES"}
                for n, t in full.COLUMN_TYPES
            ])
        if sql == full.ID_SQL:
            after, limit = params
            return Result(rows=[row for row in self.rows if row["id"] > after][:limit])
        raise AssertionError("Unexpected source SQL")


def stream_from_rows(rows, page_size=100):
    source = Source(rows)
    cursor = 0
    output = []
    while True:
        pkt = wire.make_packet(source, after_id=cursor, limit=page_size)
        if page_size < parity.PAGE_SIZE:
            # Tests of the stream parser use production's expected limit
            # by regenerating packet metadata and checksum with PAGE_SIZE.
            pkt["limit"] = parity.PAGE_SIZE
            pkt["sha256"] = sha256(wire._canonical({
                k: pkt[k] for k in wire._KEYS
            })).hexdigest()
        output.append(wire._canonical(pkt) + b"\n")
        if not pkt["more"]:
            break
        cursor = int(pkt["events"][-1]["external_id"])
    return output


def digest_for(row):
    packet = wire.make_packet(Source([row]), after_id=0, limit=100)
    return _validate_events(wire.validate_packet(
        packet, expected_limit=100, expected_after_id=0,
    ))[0][1]


def test_full_parity_aggregates_matching_changed_new_and_stale_ids():
    rows = [fake_row(1), fake_row(2), fake_row(3)]
    stream = stream_from_rows(rows)
    stage = {
        "1": (digest_for(rows[0]), False),
        "2": ("f" * 64, False),
        "5": ("b" * 64, False),
    }
    summary = parity.compare_packets(stream, stage)
    assert summary == {
        "pages": 1, "source_view_rows": 3, "source_call_groups": 3,
        "matched": 1, "changed_at_staging": 1,
        "missing_at_staging": 1, "not_visible_in_source": 1,
        "duplicate_row_groups": 0,
    }


def test_duplicate_source_rows_preserved_without_coalescing():
    rows = [fake_row(1), fake_row(2), fake_row(2, "changed"), fake_row(3)]
    summary = parity.compare_packets(stream_from_rows(rows), {})
    assert summary["source_view_rows"] == 4
    assert summary["source_call_groups"] == 3
    assert summary["duplicate_row_groups"] == 1
    assert summary["missing_at_staging"] == 3


def test_duplicate_boundary_preserves_one_complete_id_group():
    rows = [fake_row(i) for i in range(1, 100)]
    rows.extend([fake_row(100), fake_row(100, "variant"), fake_row(101)])
    summary = parity.compare_packets(stream_from_rows(rows), {})
    assert summary["pages"] == 2
    assert summary["source_view_rows"] == 102
    assert summary["source_call_groups"] == 101
    assert summary["duplicate_row_groups"] == 1


def test_truncated_stream_fails_closed():
    rows = [fake_row(i) for i in range(1, 102)]
    stream = stream_from_rows(rows)
    assert len(stream) == 2
    with pytest.raises(ValueError, match="terminal"):
        parity.compare_packets(stream[:1], {})


def test_trailing_packet_after_end_rejected():
    rows = [fake_row(1)]
    stream = stream_from_rows(rows)
    with pytest.raises(ValueError, match="terminal"):
        parity.compare_packets(stream + stream, {})


def test_modified_payload_digest_is_rejected():
    stream = stream_from_rows([fake_row(1)])
    packet = json.loads(stream[0])
    packet["events"][0]["payload"]["source_rows"][0]["outcome"] = "changed"
    with pytest.raises(ValueError, match="digest"):
        parity.compare_packets([wire._canonical(packet)], {})


def test_inspection_shell_has_no_persistent_plaintext_or_writes():
    script = Path("tools/run-odoo-mirror-parity-census.sh")
    check = subprocess.run(["bash", "-n", str(script)],
                           capture_output=True, text=True)
    assert check.returncode == 0, check.stderr
    s = script.read_text()
    assert "set -euo pipefail" in s
    assert "flock -n 9" in s
    assert "127.0.0.1:55432" in s
    assert "--log-driver=none" in s and s.count("--log-driver=none") == 2
    assert "--network container:panadan-vpn-1" in s
    assert "--network host" in s
    assert "PANADAN_FULL_MIRROR_TARGET_MODE=isolated-staging" in s
    assert "PANADAN_MIRROR_PARITY_SOURCE_PIPE=YES" in s
    assert "pg_dump" not in s and "pg_restore" not in s
    assert "tee " not in s
    assert "TRUNCATE " not in s
    assert "DELETE FROM" not in s


@pytest.mark.parametrize("completed_pass", [2, 3, 4])
def test_parity_census_accepts_only_completed_checkpoints(
    monkeypatch, completed_pass
):
    from server import odoo_full_mirror_pilot as pilot

    query_log = []

    class Stage:
        def transaction(self):
            @contextmanager
            def transaction():
                yield
            return transaction()

        def execute(self, sql, params=None):
            query_log.append(sql)
            if sql == "SET TRANSACTION READ ONLY":
                return Result()
            if "FROM panadan_ingest.sources" in sql:
                return Result(row={"enabled": False})
            if "FROM panadan_ingest.source_records" in sql:
                return Result(rows=[{
                    "external_id": "42",
                    "current_digest": "f" * 64,
                    "is_deleted": False,
                }])
            raise AssertionError("Unexpected stage SQL")

    @contextmanager
    def owned():
        yield Stage()

    marker = {"pass": completed_pass, "last_id": 0}

    def read_checkpoint(_conn, *, source_key, stream):
        assert source_key == pilot.SOURCE_KEY
        return marker if stream == pilot.SNAPSHOT_STREAM else None

    monkeypatch.setattr(parity.target, "validate_staging_writer_config",
                        lambda: "isolated-staging")
    monkeypatch.setattr(parity.target, "owned_connection", owned)
    monkeypatch.setattr(parity, "checkpoint", read_checkpoint)
    monkeypatch.setattr(parity, "compare_packets",
                        lambda _lines, _stored: {"matched": 1})
    monkeypatch.setattr(parity.sys, "stdin",
                        SimpleNamespace(buffer=io.BytesIO(b"ignored")))

    result = parity.verify_pages()
    assert result["matched"] == 1
    assert result["staged_call_groups"] == 1
    assert result["checkpoint_unchanged"] is True
    assert result["staging_read_only"] is True
    assert "SET TRANSACTION READ ONLY" in query_log


def test_parity_census_refuses_incomplete_second_pass(monkeypatch):
    @contextmanager
    def owned():
        class Stage:
            def transaction(self):
                @contextmanager
                def transaction():
                    yield
                return transaction()
            def execute(self, sql, params=None):
                if sql == "SET TRANSACTION READ ONLY":
                    return Result()
                if "FROM panadan_ingest.sources" in sql:
                    return Result(row={"enabled": False})
                return Result(rows=[])
        yield Stage()

    monkeypatch.setattr(parity.target, "validate_staging_writer_config",
                        lambda: None)
    monkeypatch.setattr(parity.target, "owned_connection", owned)
    monkeypatch.setattr(
        parity, "checkpoint",
        lambda _conn, *, source_key, stream:
            {"pass": 2, "last_id": 123} if stream == "view_reconciliation_v1" else None,
    )
    with pytest.raises(ValueError, match="Completed reconciliation"):
        parity.verify_pages()
