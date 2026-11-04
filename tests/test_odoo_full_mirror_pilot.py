"""Synthetic full-mirror pilot safety checks; no real Odoo or PostgreSQL."""
from contextlib import contextmanager
from datetime import date, datetime
from types import SimpleNamespace
import json

import pytest

from server import odoo_full_mirror_pilot as pilot
from server import odoo_full_mirror_adapter as full


def opts(command='backfill', **changes):
    data = dict(
        command=command, mode='utc_naive', batch_size=100, max_pages=1,
        ack_source_contract=True, ack_copy=True, ack_retention=True,
        ack_sensitive_data=True,
    )
    data.update(changes)
    return SimpleNamespace(**data)


@pytest.mark.parametrize('name', pilot.REQUIRED_ACKS)
def test_all_four_approvals_required(name):
    with pytest.raises(ValueError, match='approval'):
        pilot.require_approval(opts(**{name: False}))


@pytest.mark.parametrize('changes', [
    {'batch_size': 0}, {'batch_size': 101}, {'max_pages': 2},
    {'mode': 'timestamptz'},
])
def test_size_and_mode_bounds(changes):
    with pytest.raises(ValueError):
        pilot.require_approval(opts(**changes))


def fake_row(identity=1):
    kinds = dict(full.COLUMN_TYPES)
    data = {
        name: (
            identity if name == 'id' else
            date(2026, 11, 4) if kind == 'date' else
            datetime(2026, 11, 4, 3, 5) if kind == 'timestamp without time zone' else
            1 if kind == 'integer' else
            1.0 if kind == 'double precision' else
            {'en_US': 'Test'} if kind == 'jsonb' else
            'sensitive-data-not-to-log'
        )
        for name, kind in kinds.items()
    }
    return data


class Result:
    def __init__(self, rows=(), row=None):
        self.rows = list(rows)
        self.row = row
    def fetchall(self):
        return self.rows
    def fetchone(self):
        return self.row


class Source:
    def execute(self, sql, params=None):
        if sql == full.SCHEMA_SQL:
            return Result(rows=[
                {'column_name': n, 'data_type': t, 'is_nullable': 'YES'}
                for n, t in full.COLUMN_TYPES])
        if sql == full.ID_SQL:
            return Result(rows=[fake_row(1)])
        raise AssertionError('Unexpected source query')


def test_preview_is_only_counts_and_does_not_touch_owned_db(monkeypatch):
    @contextmanager
    def fake_source():
        yield Source()
    monkeypatch.setattr(pilot.database, 'connect', fake_source)
    monkeypatch.setattr(pilot.guarded, 'owned_connection',
                        lambda: pytest.fail('Preview must not touch owned DB'))
    summary = pilot.preview(limit=100)
    assert summary['fields'] == 37
    assert summary['rows_examined'] == 1
    assert summary['over_2mb'] == 0
    assert 'sensitive-data-not-to-log' not in json.dumps(summary)
    with pytest.raises(ValueError):
        pilot.preview(limit=200)


def test_source_disabled_refuses_write_before_looking_up_customer_data(monkeypatch):
    class Disabled:
        def execute(self, sql, params):
            assert 'FROM panadan_ingest.sources' in sql
            return Result(row={'enabled': False})

    @contextmanager
    def target():
        yield Disabled()

    @contextmanager
    def exclusive(_conn):
        yield

    monkeypatch.setattr(pilot.guarded, 'owned_connection', target)
    monkeypatch.setattr(pilot.guarded, 'exclusive_pilot', exclusive)
    monkeypatch.setattr(pilot.database, 'connect',
                        lambda: pytest.fail('Source should never be opened'))
    with pytest.raises(ValueError, match='not explicitly enabled'):
        pilot.apply(opts())


def test_backfill_emits_upserts_only_and_keeps_cursor(monkeypatch):
    events = [full.normalized(fake_row(4))]
    checkpoints = {'updated_at': {'marker': 'write_date',
                                  'completed_through': '2026-11-04T01:00:00+00:00'},
                   'id_backfill_and_new': None}
    monkeypatch.setattr(pilot, 'checkpoint',
                        lambda target, *, source_key, stream: checkpoints[stream])
    monkeypatch.setattr(pilot.full, 'validate_schema', lambda source: 'write_date')
    monkeypatch.setattr(pilot.full, 'read_id_page',
                        lambda source, *, after_id, limit: events)
    recorded = {}

    def ingest(*args, **kwargs):
        recorded.update(kwargs)
        return SimpleNamespace(examined=1, upserted=1, unchanged=0)

    monkeypatch.setattr(pilot, 'ingest_batch', ingest)
    answer = pilot._backfill(object(), object(), limit=100)
    assert answer['changed'] == 1 and answer['examined'] == 1
    assert recorded['source_key'] == pilot.SOURCE_KEY
    assert recorded['next_cursor'] == {'last_id': 4}
    assert all(event.operation == 'upsert' for event in recorded['events'])
    assert len(recorded['events'][0].payload) == 37


def test_no_scheduler_or_deletion_or_implicit_registration():
    from pathlib import Path
    script = Path('server/odoo_full_mirror_pilot.py').read_text()
    assert 'APScheduler' not in script
    assert 'cron.' not in script
    assert 'DELETE FROM' not in script
    assert 'UPDATE panadan_ingest.sources' not in script
    assert 'register_source(' not in script
    assert pilot.SOURCE_KEY != 'odoo_calls'
