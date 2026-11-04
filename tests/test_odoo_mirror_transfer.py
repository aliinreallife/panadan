"""Synthetic-only Odoo VPN -> isolated staging pipe transport tests."""
from contextlib import contextmanager
from datetime import date, datetime
import copy
import json
from types import SimpleNamespace

import pytest

from server import odoo_mirror_transfer as transfer
from server import odoo_full_mirror_adapter as full
from server import odoo_full_mirror_pilot as pilot


def fake_row(identity=7, *, name="private-customer"):
    return {
        key: (
            identity if key == "id" else
            date(2026, 11, 4) if kind == "date" else
            datetime(2026, 11, 4, 11, 4) if kind == "timestamp without time zone" else
            1 if kind == "integer" else
            1.0 if kind == "double precision" else
            {"en_US": "example"} if kind == "jsonb" else
            name
        )
        for key, kind in full.COLUMN_TYPES
    }


class Result:
    def __init__(self, *, row=None, rows=()):
        self.row, self.rows = row, list(rows)
    def fetchone(self):
        return self.row
    def fetchall(self):
        return self.rows


class Source:
    def __init__(self, rows):
        self.rows = rows
        self.identity = {"db": "odoo", "role": "report_user", "read_only": "on"}
    def execute(self, sql, params=None):
        if "current_setting('transaction_read_only')" in sql:
            return Result(row=self.identity)
        if sql == full.SCHEMA_SQL:
            return Result(rows=[
                {"column_name": n, "data_type": t, "is_nullable": "YES"}
                for n, t in full.COLUMN_TYPES
            ])
        if sql == full.ID_SQL:
            after, limit = params
            return Result(rows=[
                row for row in self.rows if row["id"] > after
            ][:limit])
        raise AssertionError("Unexpected source query")


def approvals(batch_size=25, **kwargs):
    data = {
        "command": "snapshot", "mode": "utc_naive",
        "batch_size": batch_size, "max_pages": 1,
        "ack_source_contract": True,
        "ack_retention": True,
        "ack_copy": True,
        "ack_sensitive_data": True,
    }
    data.update(kwargs)
    return SimpleNamespace(**data)


def test_pipe_packet_reproduces_all_37_fields_without_truncation():
    source = Source([fake_row(7), fake_row(8)])
    packet = transfer.make_packet(source, after_id=0, limit=25)
    assert packet["version"] == 1
    assert packet["source_key"] == pilot.SOURCE_KEY
    assert packet["more"] is False
    assert packet["source_rows"] == 2
    payload = transfer._canonical(packet)
    rebuilt = transfer.validate_packet(json.loads(payload), expected_limit=25,
                                       expected_after_id=0)
    assert len(rebuilt) == 2
    assert len(rebuilt[0].payload["source_rows"][0]) == 37
    assert rebuilt[0].payload["source_rows"][0]["customername"] == "private-customer"
    assert rebuilt[0].payload["source_rows"][0]["write_date"] == "2026-11-04T11:04:00.000000"
    assert rebuilt[0].payload["source_rows"][0]["CALLDATE"] == "2026-11-04"
    assert transfer._canonical(packet) == payload


def test_source_readonly_identity_checked_before_customer_query():
    source = Source([fake_row(7)])
    source.identity["read_only"] = "off"
    with pytest.raises(PermissionError, match="read-only"):
        transfer.make_packet(source, after_id=0, limit=25)


def test_duplicate_source_rows_are_not_lost():
    first = fake_row(7)
    second = dict(first, possibility_of_sale_ai=60)
    packet = transfer.make_packet(
        Source([first, second, fake_row(8)]), after_id=0, limit=25)
    events = transfer.validate_packet(packet, expected_limit=25,
                                      expected_after_id=0)
    assert packet["source_rows"] == 3
    assert len(events) == 2
    assert len(events[0].payload["source_rows"]) == 2


@pytest.mark.parametrize("corruption", [
    lambda p: p["events"][0]["payload"]["source_rows"][0].pop("customername"),
    lambda p: p["events"][0]["payload"]["source_rows"][0].__setitem__("id", 42),
    lambda p: p["events"][0].__setitem__("operation", "delete"),
    lambda p: p.__setitem__("source_rows", 100),
    lambda p: p.__setitem__("after_id", 42),
    lambda p: p.__setitem__("version", 2),
    lambda p: p.__setitem__("sha256", "0" * 64),
])
def test_corrupted_or_replayed_packet_is_rejected(corruption):
    packet = transfer.make_packet(Source([fake_row(7)]), after_id=0, limit=25)
    modified = copy.deepcopy(packet)
    corruption(modified)
    with pytest.raises(ValueError):
        transfer.validate_packet(modified, expected_limit=25, expected_after_id=0)


def test_packet_mismatch_blocks_stale_checkpoint():
    packet = transfer.make_packet(Source([fake_row(7)]), after_id=0, limit=25)
    with pytest.raises(ValueError):
        transfer.validate_packet(packet, expected_limit=25, expected_after_id=7)
    with pytest.raises(ValueError):
        transfer.validate_packet(packet, expected_limit=24, expected_after_id=0)


def test_grouped_call_larger_than_page_fails_closed():
    with pytest.raises(ValueError, match="Too many"):
        transfer.make_packet(Source([fake_row(7)] * 26), after_id=0, limit=25)


def test_enabled_stage_only_and_four_approval_flags(monkeypatch):
    packet = transfer.make_packet(Source([fake_row(7)]), after_id=0, limit=25)
    access = []

    class Target:
        def __init__(self, enabled):
            self.enabled = enabled
        def execute(self, sql, params):
            access.append("sql")
            if "FROM panadan_ingest.sources" in sql:
                return Result(row={"enabled": self.enabled})
            raise AssertionError("Unexpected staging SQL")

    enabled = [False]

    @contextmanager
    def owned():
        access.append("staging")
        yield Target(enabled[0])

    @contextmanager
    def exclusive(_):
        yield

    monkeypatch.setattr(transfer.target, "validate_staging_writer_config",
                        lambda: "test-stage-only")
    monkeypatch.setattr(transfer.target, "owned_connection", owned)
    monkeypatch.setattr(transfer.guarded, "exclusive_pilot", exclusive)

    with pytest.raises(ValueError, match="explicitly enabled"):
        transfer.import_page(packet, expected_limit=25, approvals=approvals())
    assert access == ["staging", "sql"]

    access.clear()
    with pytest.raises(ValueError, match="approval"):
        transfer.import_page(
            packet, expected_limit=25,
            approvals=approvals(ack_sensitive_data=False))
    assert not access

    enabled[0] = True
    monkeypatch.setattr(transfer, "checkpoint", lambda *_args, **_kw: None)
    monkeypatch.setattr(transfer.pilot, "_check_identity_reuse",
                        lambda *_args: None)

    def ingest(_target, **kw):
        access.append(("ingest", kw))
        return SimpleNamespace(examined=1, upserted=1, unchanged=0)

    monkeypatch.setattr(transfer, "ingest_batch", ingest)
    access.clear()
    outcome = transfer.import_page(
        packet, expected_limit=25, approvals=approvals())
    assert outcome == {
        "pages": 1, "pass": 1, "source_rows": 1, "calls": 1,
        "changed": 1, "unchanged": 0, "pass_complete": True,
    }
    kw = access[-1][1]
    assert kw["expected_cursor"] is None
    assert kw["next_cursor"] == {"pass": 2, "last_id": 0}
    assert kw["source_key"] == pilot.SOURCE_KEY
    assert kw["stream"] == pilot.SNAPSHOT_STREAM


def test_100_view_rows_roundtrip_with_37_fields_and_stable_hash():
    rows = [fake_row(i) for i in range(1, 101)]
    page = transfer.make_packet(Source(rows), after_id=0, limit=100)
    assert transfer.MAX_CALLS == 100
    assert page["source_rows"] == 100
    assert len(page["events"]) == 100
    rebuilt = transfer.validate_packet(
        json.loads(transfer._canonical(page)),
        expected_limit=100, expected_after_id=0)
    assert len(rebuilt) == 100
    assert all(len(event.payload["source_rows"][0]) == 37 for event in rebuilt)


def test_100_view_rows_does_not_split_duplicate_id_at_boundary():
    rows = [fake_row(i) for i in range(1, 99)]
    variant = dict(fake_row(99), possibility_of_sale_ai=42)
    rows.extend([fake_row(99), variant, fake_row(100), fake_row(101)])
    packet = transfer.make_packet(Source(rows), after_id=0, limit=100)
    events = transfer.validate_packet(
        packet, expected_limit=100, expected_after_id=0)
    assert packet["more"] is True
    assert packet["source_rows"] == 100
    assert len(events) == 99
    assert events[-1].external_id == "99"
    assert len(events[-1].payload["source_rows"]) == 2
    following = transfer.make_packet(Source(rows), after_id=99, limit=100)
    assert following["events"][0]["external_id"] == "100"


def test_page_budget_101_is_rejected_for_both_export_and_import():
    with pytest.raises(ValueError):
        transfer.make_packet(Source([fake_row(1)]), after_id=0, limit=101)
    packet = transfer.make_packet(Source([fake_row(1)]), after_id=0, limit=100)
    with pytest.raises(ValueError):
        transfer.validate_packet(
            packet, expected_limit=101, expected_after_id=0)


def test_100_row_wire_ceiling_is_not_increased():
    assert transfer.MAX_WIRE_BYTES == 55_000_000
    assert transfer.MAX_CALLS == 100
    packet = transfer.make_packet(Source([fake_row(1)]), after_id=0, limit=100)
    assert len(transfer._canonical(packet)) < transfer.MAX_WIRE_BYTES
