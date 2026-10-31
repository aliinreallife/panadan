"""Source-side Odoo adapter unit tests: ZERO VPN or source DB access."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from server import odoo_sync_adapter as o


UTC = timezone.utc
T = datetime(2026, 10, 31, 12, 0, 0, tzinfo=UTC)


def fake_row(record_id: int, updated: datetime, **overrides):
    data = {
        'id': record_id, 'CALLDATE': date(2026, 10, 30),
        'tellstate': 'FollowUp', 'tellside': 'IntoOut',
        'aicallinfostate': 'Unchecked', 'voice_length': 178,
        'possibility_of_sale_ai': Decimal('50.0'), 'deal_value': Decimal('0'),
        'sync_updated_at': updated,
    }
    data.update(overrides)
    return data


class Result:
    def __init__(self, *, rows=None, row=None):
        self.rows = rows or []
        self.row = row
    def fetchall(self): return self.rows
    def fetchone(self): return self.row


class FakeSource:
    def __init__(self, rows=(), now=T, *, has_timestamp=True,
                 timestamp_type='timestamp without time zone'):
        self.rows = list(rows)
        self.now = now
        self.has_timestamp = has_timestamp
        self.timestamp_type = timestamp_type
        self.queries = []

    def execute(self, sql, params=None):
        self.queries.append((sql, params))
        if sql == o.SCHEMA_SQL:
            columns = [
                {'column_name': col, 'data_type':
                 ('integer' if col == 'id' else
                  self.timestamp_type if col == 'sync_updated_at'
                  else 'text')}
                for col in o.COLUMNS
                if col != 'sync_updated_at' or self.has_timestamp
            ]
            return Result(rows=columns)
        if sql == o.SOURCE_CLOCK_SQL:
            return Result(row={'source_now': self.now})
        if sql == o.ID_SQL:
            after, limit = params
            return Result(rows=sorted(
                (row for row in self.rows if row['id'] > after),
                key=lambda r:r['id'],
            )[:limit])
        if sql == o.CHANGE_SQL:
            low, high, at, last_id, limit = params
            return Result(rows=sorted(
                (r for r in self.rows
                 if low <= r['sync_updated_at'] <= high
                 and (r['sync_updated_at'], r['id']) > (at, last_id)),
                key=lambda r:(r['sync_updated_at'],r['id']),
            )[:limit])
        raise AssertionError('Unexpected source SQL (read-only contract)')


def test_schema_requires_timestamp_added_and_explicit_type():
    src = FakeSource(has_timestamp=False)
    with pytest.raises(RuntimeError, match='lacks required'):
        o.validate_schema(src, mode='utc_naive')
    src = FakeSource(timestamp_type='timestamp without time zone')
    with pytest.raises(RuntimeError, match='type'):
        o.validate_schema(src, mode='timestamptz')
    o.validate_schema(src, mode='utc_naive')
    assert all(query.strip().upper().startswith('SELECT') for query,_ in src.queries)


def test_id_pages_find_new_records_and_use_keyset_not_offset():
    r1 = fake_row(1, T.replace(tzinfo=None), voice_length=Decimal('178.4'))
    r2 = fake_row(2, T.replace(tzinfo=None))
    r3 = fake_row(3, T.replace(tzinfo=None))
    src = FakeSource([r3, r1, r2])
    first = o.read_id_page(src, after_id=0, limit=2, mode='utc_naive')
    assert [item[0] for item in first] == [1, 2]
    assert first[0][2].payload['voice_length'] == '178.4'
    assert first[0][2].payload['sync_updated_at'] == o._iso(T)
    cursor = o.id_next_cursor(first,None)
    assert cursor == {'last_id': 2}
    assert [item[0] for item in o.read_id_page(src, after_id=cursor['last_id'],
                                                limit=2, mode='utc_naive')] == [3]
    assert ' OFFSET ' not in o.ID_SQL.upper()
    assert ' LIMIT %s' in o.ID_SQL
    assert src.queries[-1][1] == (2,2)


def test_change_pages_include_same_timestamp_different_ids():
    timestamp = T.replace(tzinfo=None)
    src=FakeSource([fake_row(i,timestamp) for i in range(1,6)])
    window = (T, T+timedelta(minutes=2), (T,0))
    all_ids = []
    position = window[2]
    for _ in range(4):
        page = o.read_change_page(src, lower=window[0], upper=window[1],
                                  position=position, limit=2, mode='utc_naive')
        all_ids.extend(x[0] for x in page)
        if len(page) < 2:
            break
        position=(page[-1][1],page[-1][0])
    assert all_ids==[1,2,3,4,5]
    assert ' OFFSET ' not in o.CHANGE_SQL.upper()
    assert '("sync_updated_at", id) > (%s, %s)' in o.CHANGE_SQL


def test_update_window_does_not_repeat_first_page_after_a_full_page():
    cursor=o.initial_change_cursor(T)
    assert cursor['completed_through']==o._iso(T-timedelta(seconds=60))
    assert cursor['marker']=='sync_updated_at'
    window=o.plan_change_window(cursor,T+timedelta(minutes=4))
    assert window[1]==T+timedelta(minutes=3)
    rows = [(1,T+timedelta(minutes=1),None),
            (2,T+timedelta(minutes=1),None)]
    next_cursor=o.change_next_cursor(cursor,window,rows,2)
    resumed=o.plan_change_window(next_cursor,T+timedelta(minutes=6))
    assert resumed==(
        window[0],window[1],(T+timedelta(minutes=1),2)
    )
    assert o.change_next_cursor(next_cursor,resumed,[],2)=={
        'completed_through':o._iso(window[1]),
        'marker':'sync_updated_at',
    }
    next_window=o.plan_change_window({'completed_through':o._iso(window[1]),
                                      'marker':'sync_updated_at'},
                                      T+timedelta(minutes=7))
    assert next_window[0]==window[1]-o.OVERLAP


@pytest.mark.parametrize('invalid',[-1,0,201,True,1.2,'100'])
def test_page_size_bounds(invalid):
    with pytest.raises(ValueError):
        o._limit(invalid)


def test_payload_allowlist_never_reads_personal_data():
    row=fake_row(5,T.replace(tzinfo=None))
    row['customername']='SECRET'
    with pytest.raises(ValueError,match='Unexpected source columns'):
        o._normalized(row,mode='utc_naive')
    assert 'transcription' not in o.SELECT_COLUMNS
    assert 'customername' not in o.SELECT_COLUMNS
    assert 'customertell' not in o.SELECT_COLUMNS
    assert 'SELECT *' not in o.ID_SQL and 'SELECT *' not in o.CHANGE_SQL


def test_source_rejects_bad_identifiers_times_and_unordered_pages():
    with pytest.raises(ValueError):
        o._normalized(fake_row(-1,T.replace(tzinfo=None)),mode='utc_naive')
    with pytest.raises(ValueError):
        o._normalized(fake_row(1,None),mode='utc_naive')
    with pytest.raises(ValueError):
        o._normalized(fake_row(1,T.replace(tzinfo=None)),mode='timestamptz')
    with pytest.raises(ValueError):
        o.read_id_page(FakeSource([fake_row(1,T.replace(tzinfo=None)),
                                   fake_row(1,T.replace(tzinfo=None))]),
                       after_id=0,mode='utc_naive')
    with pytest.raises(ValueError):
        o._parse('bad timestamp')


def test_updated_at_alias_is_supported_without_dynamic_untrusted_sql():
    src = FakeSource(has_timestamp=False)
    original=src.execute
    def execute(sql,params=None):
        if sql == o.SCHEMA_SQL:
            return Result(rows=[
                {'column_name': n,
                 'data_type':'integer' if n=='id'
                             else 'timestamp without time zone' if n=='updated_at'
                             else 'text'}
                for n in o.DATA_COLUMNS + ('updated_at',)
            ])
        if sql == o.ID_SQL_BY_MARKER['updated_at']:
            return Result(rows=[{
                **{key:value for key,value in fake_row(7,T.replace(tzinfo=None)).items()
                   if key!='sync_updated_at'},
                'updated_at':T.replace(tzinfo=None),
            }])
        return original(sql,params)
    src.execute=execute
    marker=o.validate_schema(src,mode='utc_naive')
    assert marker=='updated_at'
    result=o.read_id_page(src,after_id=0,mode='utc_naive',marker=marker)
    assert result[0][2].payload['updated_at']==o._iso(T)
    assert 'sync_updated_at' not in result[0][2].payload
    assert 'updated_at' in o.ID_SQL_BY_MARKER
    assert 'updated_at' in o.CHANGE_SQL_BY_MARKER
    assert o.ID_SQL_BY_MARKER['updated_at'].startswith('SELECT ')
    with pytest.raises(ValueError):
        o.read_id_page(src,after_id=0,mode='utc_naive',marker='malicious SQL;')


def test_active_cursor_preserves_selected_source_marker():
    cursor=o.initial_change_cursor(T,marker='updated_at')
    window=o.plan_change_window(cursor,T+timedelta(minutes=5))
    completed=o.change_next_cursor(cursor,window,[],2)
    assert completed['marker']=='updated_at'
    assert o.plan_change_window(completed,T+timedelta(minutes=7)) is not None
