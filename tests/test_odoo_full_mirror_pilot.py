"""Synthetic full-mirror pilot safety checks; no real Odoo or PostgreSQL."""
from contextlib import contextmanager
from datetime import date, datetime
from types import SimpleNamespace
import json

import pytest

from server import odoo_full_mirror_pilot as pilot
from server import odoo_full_mirror_adapter as full


def opts(command='snapshot', **changes):
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


def test_snapshot_emits_grouped_upserts_and_atomic_cursor(monkeypatch):
    events = [full.read_snapshot_page(FakeRecords([fake_row(4)]), after_id=0)[0][0]]
    checkpoints = {pilot.UPDATES_STREAM: None, pilot.BACKFILL_STREAM: None,
                   pilot.SNAPSHOT_STREAM: None}
    monkeypatch.setattr(pilot, 'checkpoint',
                        lambda target, *, source_key, stream: checkpoints[stream])
    monkeypatch.setattr(pilot.full, 'validate_schema', lambda source: 'write_date')
    monkeypatch.setattr(pilot.full, 'read_snapshot_page',
                        lambda source, *, after_id, limit: (events, True, 1))
    recorded = {}

    def ingest(*args, **kwargs):
        recorded.update(kwargs)
        return SimpleNamespace(examined=1, upserted=1, unchanged=0)

    monkeypatch.setattr(pilot, 'ingest_batch', ingest)
    answer = pilot._snapshot(object(), FakeTarget(), limit=100)
    assert answer['changed'] == 1 and answer['calls'] == 1
    assert recorded['source_key'] == pilot.SOURCE_KEY
    assert recorded['stream'] == pilot.SNAPSHOT_STREAM
    assert recorded['next_cursor'] == {'pass': 1, 'last_id': 4}
    assert all(event.operation == 'upsert' for event in recorded['events'])
    assert len(recorded['events'][0].payload['source_rows'][0]) == 37


class FakeRecords:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, sql, params):
        if sql == full.ID_SQL:
            after, limit = params
            return Result(rows=[r for r in self.rows if r['id'] > after][:limit])
        raise AssertionError('Unexpected source SQL')


class FakeTarget:
    def __init__(self, previous=()):
        self.previous = previous

    def execute(self, sql, params):
        assert 'raw_revisions' in sql
        return Result(rows=self.previous)


def test_snapshot_pass_completion_and_no_tombstones(monkeypatch):
    checkpoints = {pilot.UPDATES_STREAM: None, pilot.BACKFILL_STREAM: None,
                   pilot.SNAPSHOT_STREAM: {'pass': 2, 'last_id': 9}}
    monkeypatch.setattr(pilot, 'checkpoint',
                        lambda target, *, source_key, stream: checkpoints[stream])
    monkeypatch.setattr(pilot.full, 'validate_schema', lambda source: 'write_date')
    monkeypatch.setattr(pilot.full, 'read_snapshot_page',
                        lambda source, *, after_id, limit: ([], False, 0))
    recorded = {}

    def ingest(*args, **kwargs):
        recorded.update(kwargs)
        return SimpleNamespace(examined=0, upserted=0, unchanged=0)

    monkeypatch.setattr(pilot, 'ingest_batch', ingest)
    result = pilot._snapshot(object(), FakeTarget(), limit=100)
    assert result['pass_complete']
    assert recorded['events'] == []
    assert recorded['next_cursor'] == {'pass': 3, 'last_id': 0}


def test_changed_identity_anchors_are_rejected(monkeypatch):
    event = full.read_snapshot_page(FakeRecords([fake_row(4)]),
                                    after_id=0)[0][0]
    old = dict(event.payload)
    old['source_rows'] = [dict(event.payload['source_rows'][0],
                               call_id='reused-call')]
    target = FakeTarget([{'external_id': '4', 'payload': old}])
    with pytest.raises(ValueError, match='identity appears reused'):
        pilot._check_identity_reuse(target, [event])


def test_legacy_cursors_block_snapshot(monkeypatch):
    checkpoints = {pilot.UPDATES_STREAM: {'marker': 'write_date'},
                   pilot.BACKFILL_STREAM: None,
                   pilot.SNAPSHOT_STREAM: None}
    monkeypatch.setattr(pilot, 'checkpoint',
                        lambda target, *, source_key, stream: checkpoints[stream])
    monkeypatch.setattr(pilot.full, 'validate_schema', lambda source: 'write_date')
    with pytest.raises(ValueError, match='Legacy'):
        pilot._snapshot(object(), FakeTarget(), limit=100)


def test_no_scheduler_or_deletion_or_implicit_registration():
    from pathlib import Path
    script = Path('server/odoo_full_mirror_pilot.py').read_text()
    assert 'APScheduler' not in script
    assert 'cron.' not in script
    assert 'DELETE FROM' not in script
    assert 'UPDATE panadan_ingest.sources' not in script
    assert 'register_source(' not in script
    assert pilot.SOURCE_KEY != 'odoo_calls'



def test_mirror_projection_omits_conflicting_ai_scores():
    from server.platform_processing import public_call_facts

    one = fake_row(42)
    one.update(tellside='IntoOut', tellstate='FirstToch',
               aicallinfostate='SoldOut', voice_length=120.0,
               possibility_of_sale_ai=20,
               customername='SECRET-NAME',
               transcription='SECRET-TRANSCRIPT')
    two = dict(one, possibility_of_sale_ai=80,
               tell_state_desc='conflicting analysis')
    event = full.read_snapshot_page(FakeRecords([one, two]),
                                    after_id=0, limit=100)[0][0]
    facts = public_call_facts(event.payload)
    assert facts['call_direction'] == {'code': 'IntoOut', 'meaning': 'outgoing'}
    assert facts['recording_duration'] == {'seconds': 120.0}
    assert 'ai_sales_estimate' not in facts
    assert 'SECRET-NAME' not in json.dumps(facts)
    assert 'SECRET-TRANSCRIPT' not in json.dumps(facts)

    # When there is no ambiguity, the legacy safe scoring fact is supported.
    single = full.read_snapshot_page(FakeRecords([one]),
                                     after_id=0)[0][0]
    assert public_call_facts(single.payload)['ai_sales_estimate'] == {
        'score_0_100': 20, 'is_confirmed_sale': False}


@pytest.mark.parametrize('payload', [
    {'id': 1, 'source_schema': 'odoo_view_37_v1', 'source_rows': []},
    {'id': 1, 'source_schema': 'odoo_view_37_v1',
     'source_rows': [{'id': 2, 'transcription': 'PRIVATE'}]},
    {'id': 1, 'source_schema': 'odoo_view_37_v1',
     'source_rows': ['PRIVATE']},
])
def test_mirror_projection_rejects_invalid_envelopes(payload):
    from server.platform_processing import public_call_facts
    with pytest.raises(ValueError, match='Invalid full mirror'):
        public_call_facts(payload)



def test_manual_snapshot_run_commits_pages_and_stops_at_pass_boundary(monkeypatch):
    """One supervised command can resume pages without crossing into a new pass."""
    recorded = []

    def part(_source, _target, *, limit):
        recorded.append(limit)
        return {
            'pass': 7, 'source_rows': 100, 'calls': 100,
            'changed': 2, 'unchanged': 98,
            'pass_complete': len(recorded) == 3,
        }

    monkeypatch.setattr(pilot, '_snapshot', part)
    result = pilot._snapshot_run(object(), object(), limit=100, max_pages=10)
    assert recorded == [100, 100, 100]
    assert result == {
        'operation': 'snapshot-run', 'pages': 3, 'source_rows': 300,
        'calls': 300, 'changed': 6, 'unchanged': 294,
        'pass_complete': True, 'pass': 7,
    }


def test_manual_snapshot_run_enforces_budget_and_approval(monkeypatch):
    calls = []

    def part(_source, _target, *, limit):
        calls.append(limit)
        return {
            'pass': 1, 'source_rows': 100, 'calls': 100,
            'changed': 0, 'unchanged': 100, 'pass_complete': False,
        }

    monkeypatch.setattr(pilot, '_snapshot', part)
    result = pilot._snapshot_run(object(), object(), limit=100, max_pages=2)
    assert result['pages'] == 2 and not result['pass_complete']
    assert len(calls) == 2

    with pytest.raises(ValueError, match='budget'):
        pilot._snapshot_run(object(), object(), limit=100, max_pages=11)
    with pytest.raises(ValueError, match='pages'):
        pilot.require_approval(opts(command='snapshot-run', max_pages=11))
    with pytest.raises(ValueError, match='pages'):
        pilot.require_approval(opts(command='snapshot', max_pages=2))
    pilot.require_approval(opts(command='snapshot-run', max_pages=10))


def test_manual_snapshot_run_aborts_on_page_failure(monkeypatch):
    count = {'n': 0}

    def part(_source, _target, *, limit):
        count['n'] += 1
        if count['n'] == 2:
            raise RuntimeError('synthetic source interruption')
        return {
            'pass': 1, 'source_rows': 100, 'calls': 100,
            'changed': 100, 'unchanged': 0, 'pass_complete': False,
        }

    monkeypatch.setattr(pilot, '_snapshot', part)
    with pytest.raises(RuntimeError, match='interruption'):
        pilot._snapshot_run(object(), object(), limit=100, max_pages=4)
    assert count['n'] == 2
