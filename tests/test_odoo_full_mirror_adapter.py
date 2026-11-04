"""No customer data, source connection, or DB write: synthetic full-field tests."""
from datetime import date, datetime, timezone, timedelta
import json

import pytest

from server import odoo_full_mirror_adapter as full


TS = datetime(2026, 11, 4, 3, 0, 0, 123456)
UTC = timezone.utc


def record(identity=1, **changes):
    values = {}
    for name, kind in full.COLUMN_TYPES:
        values[name] = {
            'integer': 1, 'double precision': 1.25,
            'character varying': 'عنوان فارسی', 'text': 'متن فارسی',
            'date': date(2026, 11, 4),
            'timestamp without time zone': TS,
            'jsonb': {'fa_IR': 'فروش', 'extra': [None, 1, True]},
        }[kind]
    values['id'] = identity
    values.update(changes)
    return values


class Result:
    def __init__(self, rows):
        self.rows = rows
    def fetchall(self):
        return self.rows


class Source:
    def __init__(self, records=(), schema=None):
        self.records = list(records)
        self.schema = schema or full.COLUMN_TYPES
        self.queries = []
    def execute(self, sql, params):
        self.queries.append((sql, params))
        if sql == full.SCHEMA_SQL:
            return Result([{'column_name': a, 'data_type': b, 'is_nullable': 'YES'}
                           for a, b in self.schema])
        if sql == full.ID_SQL:
            after, limit = params
            return Result(sorted((r for r in self.records if r['id'] > after),
                                 key=lambda r: r['id'])[:limit])
        if sql == full.CHANGE_SQL:
            lo, hi, at, identity, limit = params
            return Result(sorted((r for r in self.records
                                  if lo <= r['write_date'] <= hi
                                  and (r['write_date'], r['id']) > (at, identity)),
                                 key=lambda r: (r['write_date'], r['id']))[:limit])
        raise AssertionError('Unexpected SQL')


def test_explicit_source_schema_is_exactly_37_columns():
    assert len(full.COLUMN_TYPES) == 37
    assert full.COLUMN_NAMES[0] == 'id'
    assert full.COLUMN_NAMES[-1] == 'write_date'
    assert 'customername' in full.COLUMN_NAMES
    assert 'customertell' in full.COLUMN_NAMES
    assert 'transcription' in full.COLUMN_NAMES
    assert 'crm_team_name' in full.COLUMN_NAMES
    source = Source()
    assert full.validate_schema(source) == 'write_date'
    assert source.queries[0][1] == ('public', 'vw_danix_call_info_report')
    assert 'SELECT *' not in full.ID_SQL
    assert 'DELETE' not in full.ID_SQL.upper()
    assert ' OFFSET ' not in full.ID_SQL.upper()
    assert ' OFFSET ' not in full.CHANGE_SQL.upper()


@pytest.mark.parametrize('schema', [
    full.COLUMN_TYPES[:-1],
    full.COLUMN_TYPES + (('extra', 'text'),),
    tuple((n, 'text' if n == 'transcription' else t)
          for n, t in full.COLUMN_TYPES[:-1]) + (('write_date', 'timestamp with time zone'),),
    tuple(reversed(full.COLUMN_TYPES)),
])
def test_schema_drift_fails_closed(schema):
    with pytest.raises(RuntimeError, match='schema drift'):
        full.validate_schema(Source(schema=schema))


def test_all_fields_are_present_and_values_preserved():
    row = record(10, transcription='طولانی\nسلام' * 400,
                 customertell='۰۹۱۲۳۴۵۶۷۸۹', customername='مشتری',
                 crm_team_name={'fa_IR': 'تهران', 'en_US': None},
                 call_id=None, create_date=datetime(2025, 12, 31, 2, 4, 5))
    identity, updated, event = full.normalized(row)
    assert identity == 10
    assert updated == TS.replace(tzinfo=UTC)
    assert event.operation == 'upsert'
    assert set(event.payload) == set(full.COLUMN_NAMES)
    assert event.payload['call_id'] is None
    assert event.payload['customername'] == 'مشتری'
    assert event.payload['customertell'] == '۰۹۱۲۳۴۵۶۷۸۹'
    assert event.payload['transcription'] == row['transcription']
    assert event.payload['crm_team_name'] == {'fa_IR': 'تهران', 'en_US': None}
    assert event.payload['CALLDATE'] == '2026-11-04'
    assert event.payload['create_date'] == '2025-12-31T02:04:05.000000'
    assert event.payload['write_date'] == '2026-11-04T03:00:00.123456'
    json.dumps(event.payload, ensure_ascii=False, allow_nan=False)


def test_big_transcript_is_not_truncated_by_reader():
    transcript = 'پ' * 2_100_000
    event = full.normalized(record(2, transcription=transcript))[2]
    assert len(event.payload['transcription']) == len(transcript)
    # The existing ingest writer STILL has a 2MB payload limit and requires
    # separately reviewed capacity changes; never silently ignore this.


@pytest.mark.parametrize('bad', [
    {'id': None}, {'id': 0}, {'write_date': None},
    {'CALLDATE': '2026-11-04'}, {'voice_length': float('nan')},
    {'crm_team_name': {1: 'invalid-key'}}, {'crm_team_name': {'x': float('inf')}},
])
def test_bad_values_fail_closed_without_payload_logging(bad):
    with pytest.raises(ValueError):
        full.normalized(record(1, **bad))


def test_paged_read_and_changes_keep_ids_and_timestamp_order():
    rows = [record(i) for i in (3, 1, 2)]
    source = Source(rows)
    assert [x[0] for x in full.read_id_page(source, after_id=0, limit=2)] == [1, 2]
    assert [x[0] for x in full.read_id_page(source, after_id=2, limit=2)] == [3]
    when = TS.replace(tzinfo=UTC)
    assert [x[0] for x in full.read_change_page(
        source, lower=when, upper=when + timedelta(minutes=1),
        position=(when, 0), limit=2)] == [1, 2]
    assert [x[0] for x in full.read_change_page(
        source, lower=when, upper=when + timedelta(minutes=1),
        position=(when, 2), limit=2)] == [3]
    assert all(q.lstrip().upper().startswith('SELECT') for q, _ in source.queries)


def test_missing_rows_are_not_tombstoned():
    source = Source([record(1)])
    assert len(full.read_id_page(source, after_id=1, limit=100)) == 0
    assert not hasattr(full, 'delete_missing')
    assert not hasattr(full, 'tombstone_missing')


def test_reject_ambiguous_or_extra_fields():
    with pytest.raises(ValueError):
        full.normalized({**record(), 'unexpected': 'raw'})
    with pytest.raises(ValueError):
        full.normalized({k: v for k, v in record().items() if k != 'summary'})


def test_reject_non_utc_mode():
    with pytest.raises(ValueError):
        full.validate_schema(Source(), mode='timestamptz')
    with pytest.raises(ValueError):
        full.normalized(record(), mode='timestamptz')
