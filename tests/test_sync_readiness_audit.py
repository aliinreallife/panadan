"""Sync-readiness audit must not fetch source call rows into Python."""
from contextlib import contextmanager
import json
import pytest

from server import sync_readiness_audit as audit


class Cursor:
    def __init__(self, rows=None, row=None):
        self.rows = rows or []
        self.row = row
    def fetchall(self): return self.rows
    def fetchone(self): return self.row


class Connection:
    def __init__(self, queries, has_markers=False):
        self.queries = queries
        self.has_markers = has_markers
    def execute(self, sql, params=None):
        self.queries.append((sql, params))
        if sql == audit.COLUMN_SQL:
            names = ['id', 'create_date', 'transcription']
            if self.has_markers:
                names += ['write_date', 'deleted_at']
            return Cursor(rows=[{'column_name':n, 'data_type': 'integer' if n=='id' else 'timestamp without time zone',
                                 'is_nullable':'YES'} for n in names])
        if sql == audit.KIND_SQL:
            return Cursor(row={'relation_kind':'v'})
        if sql == audit.SAMPLE_SQL:
            return Cursor(row={'sampled_rows':100,'nonnull_ids':100,
                               'distinct_ids':100,'creation_dates_present':100,
                               'creation_order_inversions':0})
        if sql == audit.PLAN_SQL:
            return Cursor(row={'QUERY PLAN':[{'Plan': {'Plan Rows':50000, 'Plan Width':1024}}]})
        raise AssertionError('unexpected SQL: '+sql)


def test_bounded_audit_with_plan_does_not_report_ids_or_transcripts(monkeypatch):
    queries=[]
    @contextmanager
    def conn():
        yield Connection(queries)
    monkeypatch.setattr(audit.database, 'connect', conn)
    out=audit.inspect()
    assert len(queries)==4
    assert queries[2]==(audit.SAMPLE_SQL,(100,))
    assert queries[3]==(audit.PLAN_SQL,None)
    assert out['relation_kind']=='view'
    assert out['identity_candidate']=='id'
    assert out['update_marker_candidates']==[]
    assert out['deletion_marker_candidates']==[]
    assert out['plan_estimate']['planner_rows_estimate']==50000
    assert out['readiness']['can_detect_updates']=='no_visible_update_marker'
    assert out['sample']['distinct_ids']==100
    assert 'transcription' not in json.dumps(out)
    assert 'SELECT *' not in str(queries[2])
    assert all(q.strip().upper().startswith(('SELECT ', 'WITH ', 'EXPLAIN '))
               for q,_ in queries)


def test_schema_markers_are_only_candidates_not_proven(monkeypatch):
    @contextmanager
    def conn():
        yield Connection([],has_markers=True)
    monkeypatch.setattr(audit.database,'connect',conn)
    out=audit.inspect(sample=0,explain=False)
    assert out['update_marker_candidates']==['write_date']
    assert out['update_marker_details'] == [
        {'name':'write_date','data_type':'timestamp without time zone',
         'nullable':True}
    ]
    assert out['deletion_marker_candidates']==['deleted_at']
    assert out['readiness']['can_detect_updates']=='unverified'
    assert out['readiness']['can_detect_deletes']=='unverified'
    assert out['sample'] is None
    assert out['plan_estimate'] is None


@pytest.mark.parametrize('bad',[-1,301,1.5,True,'100'])
def test_invalid_sample_rejected_before_connect(monkeypatch,bad):
    monkeypatch.setattr(audit.database,'connect',lambda: pytest.fail('must not connect'))
    with pytest.raises(ValueError):
        audit.inspect(sample=bad)


def test_plan_error_does_not_discard_catalog_and_sample(monkeypatch):
    class PlanErrorConnection(Connection):
        def execute(self, sql, params=None):
            if sql==audit.PLAN_SQL:
                raise RuntimeError('explain not available')
            return super().execute(sql,params)
    @contextmanager
    def conn():
        yield PlanErrorConnection([])
    monkeypatch.setattr(audit.database,'connect',conn)
    assert audit.inspect()['plan_estimate'] is None


def test_error_message_does_not_leak_sensitive_exception(monkeypatch,capsys):
    def fail(**kwargs):
        raise RuntimeError('password=secret customer phone 09120000000')
    monkeypatch.setattr(audit,'inspect',fail)
    assert audit.main([])==2
    stderr=capsys.readouterr().err
    assert 'password' not in stderr and '0912' not in stderr
    assert 'RuntimeError SQLSTATE=unknown' in stderr


def test_write_at_is_detected_by_catalog_only_and_not_approved_for_sync(monkeypatch):
    class WriteAtConnection(Connection):
        def execute(self, sql, params=None):
            if sql == audit.COLUMN_SQL:
                return Cursor(rows=[
                    {'column_name':'id', 'data_type':'bigint', 'is_nullable':'NO'},
                    {'column_name':'write_at',
                     'data_type':'timestamp without time zone', 'is_nullable':'YES'},
                ])
            return super().execute(sql, params)
    calls=[]
    @contextmanager
    def conn():
        yield WriteAtConnection(calls)
    monkeypatch.setattr(audit.database,'connect',conn)
    out=audit.inspect(sample=0,explain=False)
    assert out['update_marker_candidates']==['write_at']
    assert out['update_marker_details']==[
        {'name':'write_at','data_type':'timestamp without time zone','nullable':True}
    ]
    assert out['readiness']['can_detect_updates']=='unverified'
    assert len(calls)==2
    assert all(q.strip().upper().startswith('SELECT') for q,_ in calls)

    # Discovery of a candidate does NOT enable source polling via the
    # adapter: only verified updated_at or sync_updated_at is allowed.
    from server import odoo_sync_adapter
    assert 'write_at' not in odoo_sync_adapter.UPDATE_COLUMNS
