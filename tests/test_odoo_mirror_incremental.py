"""Synthetic write_date/create_date mirror tests. No Odoo or staging access."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import subprocess

import pytest

from server import odoo_full_mirror_adapter as full
from server import odoo_mirror_incremental as inc
from server import odoo_mirror_transfer as transfer
from server import odoo_full_mirror_pilot as pilot

NOW = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)


def sample(identity, *, created=None, written=None, outcome="demo"):
    created = created or datetime(2026, 11, 5, 10)
    written = written or datetime(2026, 11, 5, 11, 30)
    result = {
        name: (identity if name == "id"
               else date(2026, 11, 5) if kind == "date"
               else created if name == "create_date"
               else written if name == "write_date"
               else datetime(2026, 11, 5, 10)
                    if kind == "timestamp without time zone"
               else 1 if kind == "integer"
               else 1.0 if kind == "double precision"
               else {"en_US": "test"} if kind == "jsonb"
               else outcome if name == "outcome" else "test")
        for name, kind in full.COLUMN_TYPES
    }
    result["call_id"] = f"synthetic-{identity}"
    return result


class Result:
    def __init__(self, one=None, rows=()):
        self.one = one
        self.rows = list(rows)

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.rows


class Source:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, sql, params=None):
        if sql == full.SCHEMA_SQL:
            return Result(rows=[
                {"column_name": name, "data_type": typ}
                for name, typ in full.COLUMN_TYPES])
        if "current_database() AS db" in sql:
            return Result(one={
                "db": "odoo", "role": "report_user", "read_only": "on"})
        if sql == inc.CANDIDATE_SQL:
            low, high, last_ts, last_id, limit = (
                params[0], params[1], params[6], params[7], params[8])
            found = {}
            for row in self.rows:
                create, write = row["create_date"], row["write_date"]
                if low <= write <= high or (
                    create is not None and low <= create <= high):
                    touched = max(v for v in (write, create)
                                  if v is not None)
                    if low <= touched <= high:
                        found[row["id"]] = max(
                            found.get(row["id"], touched), touched)
            matched = [
                {"id": identity, "touched": touched}
                for identity, touched in found.items()
                if (touched, identity) > (last_ts, last_id)]
            matched.sort(key=lambda r: (r["touched"], r["id"]))
            return Result(rows=matched[:limit])
        if sql == inc.GROUP_SQL:
            ids = params[0]
            return Result(rows=sorted(
                (row for row in self.rows if row["id"] in ids),
                key=lambda r: r["id"]))
        raise AssertionError("Unexpected source SQL")


def page(rows, before=None):
    return inc.make_incremental_packet(Source(rows), before, now=NOW)


def test_new_lower_id_detected_by_create_date():
    rows = [
        sample(9000, created=datetime(2026, 11, 4, 10),
               written=datetime(2026, 11, 5, 11, 40)),
        sample(1, created=datetime(2026, 11, 5, 11, 55),
               written=datetime(2026, 11, 4, 8))]
    packet = page(rows)
    assert {e.external_id for e in inc.validate_incremental_packet(packet)} \
        == {"9000", "1"}
    assert packet["next_cursor"]["kind"] == inc.KIND
    assert packet["next_cursor"]["completed_through"] == \
        inc._iso(NOW - inc.SETTLE)
    assert packet["source_rows"] == 2


def test_duplicate_join_variants_are_preserved():
    packet = page([sample(52, outcome="a"),
                   sample(52, outcome="b"), sample(99)])
    events = inc.validate_incremental_packet(packet)
    assert len(events) == 2
    record = next(e for e in events if e.external_id == "52")
    assert len(record.payload["source_rows"]) == 2
    assert {row["outcome"] for row in record.payload["source_rows"]} == \
        {"a", "b"}
    assert packet["source_rows"] == 3


def test_conflicting_identity_anchors_stop():
    a, b = sample(8), sample(8)
    b["call_id"] = "other"
    with pytest.raises(ValueError, match="Conflicting stable source"):
        page([a, b])


def test_frozen_window_resume_and_completion():
    rows = [sample(i) for i in range(1, 86)]
    first = page(rows)
    assert first["more"] and len(first["events"]) == inc.PAGE_LIMIT
    assert first["next_cursor"]["window"]["last_id"] == 80
    second = page(rows, first["next_cursor"])
    assert not second["more"] and len(second["events"]) == 5
    assert "window" not in second["next_cursor"]
    inc.validate_incremental_packet(second)


def test_completed_through_in_future_is_noop():
    cursor = {"kind": inc.KIND,
              "completed_through": inc._iso(NOW - timedelta(seconds=30))}
    packet = page([sample(1)], cursor)
    assert packet["noop"] and packet["next_cursor"] == cursor
    assert inc.validate_incremental_packet(packet) == []


def test_forged_packet_and_drift_rejected():
    packet = page([sample(1)])
    packet["events"][0]["payload"]["source_rows"][0]["outcome"] = "bad"
    with pytest.raises(ValueError, match="digest mismatch"):
        inc.validate_incremental_packet(packet)
    packet = page([sample(1)])
    packet["events"][0]["payload"]["source_rows"][0].pop("customername")
    unsigned = {k: v for k, v in packet.items() if k != "sha256"}
    packet["sha256"] = sha256(transfer._canonical(unsigned)).hexdigest()
    with pytest.raises(ValueError, match="full-field"):
        inc.validate_incremental_packet(packet)


def test_staging_writer_preserves_snapshot_cursor(monkeypatch):
    packet = page([sample(1), sample(2)])
    requests = []

    class Stage:
        def execute(self, sql, params=None):
            if "SELECT enabled FROM panadan_ingest.sources" in sql:
                return Result(one={"enabled": True})
            raise AssertionError("Unexpected stage SQL")

    @contextmanager
    def owned():
        yield Stage()

    @contextmanager
    def exclusive(_):
        yield

    def checkpoint(_conn, *, source_key, stream):
        assert source_key == pilot.SOURCE_KEY
        if stream == pilot.SNAPSHOT_STREAM:
            return {"pass": 3, "last_id": 0}
        return None

    def ingest(_conn, **kwargs):
        requests.append(kwargs)
        return SimpleNamespace(examined=2, upserted=2, unchanged=0)

    monkeypatch.setattr(inc.target, "validate_staging_writer_config",
                        lambda: "isolated-staging")
    monkeypatch.setattr(inc.target, "owned_connection", owned)
    monkeypatch.setattr(inc.guarded, "exclusive_pilot", exclusive)
    monkeypatch.setattr(inc, "checkpoint", checkpoint)
    monkeypatch.setattr(inc.pilot, "_check_identity_reuse",
                        lambda *_: None)
    monkeypatch.setattr(inc, "ingest_batch", ingest)
    outcome = inc.import_incremental_packet(packet)
    assert outcome["calls"] == 2
    assert len(requests) == 1
    assert requests[0]["stream"] == inc.STREAM
    assert requests[0]["expected_cursor"] is None
    assert requests[0]["next_cursor"] == packet["next_cursor"]


def test_shell_guardrails_and_syntax():
    script = Path("tools/run-odoo-mirror-incremental-cycle.sh")
    check = subprocess.run(["bash", "-n", str(script)],
                           capture_output=True, text=True)
    assert check.returncode == 0, check.stderr
    s = script.read_text()
    assert "set -euo pipefail" in s
    assert "set +x" in s
    assert "umask 077" in s
    assert "flock -n 9" in s
    assert "--network container:panadan-vpn-1" in s
    assert "--network host" in s
    assert s.count("--log-driver=none") == 2
    assert "PANADAN_MIRROR_INCREMENTAL_PIPE=YES" in s
    assert "MIN_AVAILABLE_KIB=6291456" in s
    assert "MAX_PAGES=10" in s
    assert "pg_dump" not in s and "age -r" not in s
    assert "TRUNCATE " not in s and "DELETE FROM " not in s
    assert "odoo_mirror_parity_stream" not in s
    assert "run-odoo-mirror-staging-reconcile" not in s


def test_bad_cycle_arguments_rejected_without_sudo():
    r = subprocess.run(
        ["bash", "tools/run-odoo-mirror-incremental-cycle.sh", "bad"],
        capture_output=True, text=True, timeout=5)
    assert r.returncode == 2 and "Usage:" in r.stderr
