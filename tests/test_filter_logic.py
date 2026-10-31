"""Report-filter predicates are fixed SQL and dates always constrain OR results."""
from datetime import date
from contextlib import contextmanager
from pathlib import Path

import pytest

from server import database


def test_any_mode_groups_dimensions_but_dates_remain_and():
    where, params = database.filters(
        date(2026, 10, 1), date(2026, 10, 31),
        'SoldOut', call_type='FollowUp', operator='Other Op',
        direction='Incoming', filter_mode='any',
        any_operator_groups=[['Test Op'], ['__unspecified__']],
    )
    assert where.startswith(' WHERE "CALLDATE" >= %s AND "CALLDATE" <= %s AND (')
    assert '"aicallinfostate" = %s OR "tellstate" = %s' in where
    assert '"tellside"::text = %s OR ' in where
    assert '"vw_danix_base_info_users_name" = ANY(%s)' in where
    assert 'IS NULL OR BTRIM(' in where
    assert params == [date(2026,10,1), date(2026,10,31),
                      'SoldOut','FollowUp','Incoming','Other Op',['Test Op']]
    assert where.count(' OR ') >= 5


def test_default_all_mode_preserves_existing_directory_intersection():
    where, params = database.filters(None, None, 'Unchecked',
                                     operator='Test Op',operator_names=['Test Op'],
                                     direction='Outgoing')
    assert ' OR ' not in where
    assert '"tellside"::text = %s' in where
    assert ' AND ' in where
    assert params == ['Unchecked','Outgoing','Test Op',['Test Op']]


def test_unmatched_directory_group_is_false_not_unrestricted():
    where, params = database.filters(None, None, None,
                                     filter_mode='any',
                                     any_operator_groups=[[]])
    assert 'FALSE' in where
    assert not params
    where, params = database.filters(None, None, None,
                                     operator_names=[])
    assert 'FALSE' in where


def test_invalid_mode_never_becomes_sql():
    with pytest.raises(ValueError):
        database.filters(None,None,None,filter_mode='weird')
    with pytest.raises(ValueError):
        database.filters(None,None,None,filter_mode='OR 1=1')


def test_filter_query_stays_read_only_and_parameterized(monkeypatch):
    queries = []
    class FakeConnection:
        def execute(self, q, params):
            queries.append((q, params))
            return self
        def fetchall(self):
            return []
        def fetchone(self):
            return {'total':0, 'sold_out':0, 'scored_calls':0,
                    'avg_ai_score':None,'avg_voice_length':None}

    @contextmanager
    def connect():
        yield FakeConnection()

    monkeypatch.setattr(database,'connect',connect)
    assert database.list_calls(
        after=date(2026,10,1),state='SoldOut',
        direction='Incoming',filter_mode='any',operator='Other Op') == []
    result = database.stats(
        after=date(2026,10,1),state='SoldOut',
        direction='Incoming',filter_mode='any',operator='Other Op')
    assert result['total'] == 0
    assert len(queries)==2
    for sql, args in queries:
        assert sql.startswith('SELECT ')
        assert ' WHERE "CALLDATE" >= %s AND (' in sql
        assert '"tellside"::text = %s' in sql
        assert '"aicallinfostate" = %s OR ' in sql
        assert 'Other Op' not in sql
        assert 'Incoming' not in sql
        assert 'Other Op' in args
        assert 'Incoming' in args


def test_mobile_ui_and_filter_contract_are_scoped():
    html = Path('templates/dashboard.html').read_text()
    js = Path('static/app.js').read_text()
    css = Path('static/style.css').read_text()
    assert 'id="direction" multiple data-multi' in html
    assert 'name="filter_mode"' not in html
    assert 'id="created_after"' not in html
    assert "for(const value of multiValues(select))values.append(key,value)" in js
    assert "params.delete('limit')" in js
    assert "td.dataset.label" in js
    assert '.calls-panel tbody tr{' in css
    assert '.report-filters{' in css
    assert '#metric-length{' in css


def test_multiselect_or_matches_all_selected_values_but_dates_are_and():
    where, params = database.filters(
        date(2026,10,1), date(2026,10,31), None,
        filter_mode='any',
        selected_facets={
            'operators':['Ali','Sara'],
            'states':['SoldOut','Unchecked'],
            'call_types':['FollowUp'],
            'directions':['1','2'],
        },
        any_operator_groups=[['Team Alpha'], ['__unspecified__']],
    )
    assert where.startswith(' WHERE "CALLDATE" >= %s AND "CALLDATE" <= %s AND (')
    assert '"vw_danix_base_info_users_name" = ANY(%s)' in where
    assert '"aicallinfostate" = ANY(%s)' in where
    assert '"tellstate" = ANY(%s)' in where
    assert '"tellside"::text = ANY(%s)' in where
    assert ' OR ' in where
    assert params[:2] == [date(2026,10,1),date(2026,10,31)]
    assert ['Ali','Sara'] in params
    assert ['SoldOut','Unchecked'] in params
    assert ['1','2'] in params
    assert ['Team Alpha'] in params


def test_operator_profile_remains_fixed_and_cannot_expand_via_other_facets():
    where, params = database.filters(
        date(2026,10,1), None, None,
        operator='Ali', filter_mode='any',
        selected_facets={'states':['SoldOut','Unchecked']},
    )
    assert ' WHERE "CALLDATE" >= %s AND "vw_danix_base_info_users_name" = %s AND (' in where
    assert '"aicallinfostate" = ANY(%s)' in where
    assert params == [date(2026,10,1),'Ali',['SoldOut','Unchecked']]


@pytest.mark.parametrize('bad',[
    {'unknown':['a']},{'states':['a']*21},
    {'states':['']},{'operators':['x'*181]},{'directions':['x'*61]},
])
def test_multiselect_validation_rejects_untrusted_inputs(bad):
    with pytest.raises(ValueError):
        database.filters(None,None,None,selected_facets=bad,filter_mode='any')


def test_empty_multiselect_has_no_restricting_or_predicates():
    where, params = database.filters(None,None,None,
                                     selected_facets={'states':[],'directions':[]},
                                     filter_mode='any')
    assert where == ''
    assert params == []
