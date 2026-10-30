"""Prevent accidental application-level writes to Odoo."""
from contextlib import contextmanager
import pytest
from server import database

class FakeConnection:
    def __init__(self): self.commands=[]
    def __enter__(self): return self
    def __exit__(self,*_): pass
    @contextmanager
    def transaction(self): yield
    def execute(self,command,*params):
        self.commands.append(command)
        return self
    def fetchall(self): return []

def test_each_query_opens_explicit_read_only_transaction(monkeypatch):
    db=FakeConnection()
    monkeypatch.setenv('PGUSER','test-user')
    monkeypatch.setenv('PGPASSWORD','not-a-real-password')
    monkeypatch.setattr(database.psycopg,'connect',lambda **kw: db)
    database.list_calls(limit=1)
    assert db.commands[0] == 'SET TRANSACTION READ ONLY'
    assert db.commands[1].startswith('SELECT ')

def test_call_type_filter_is_parameterized():
    where, parameters = database.filters(None, None, 'Unchecked', call_type='FollowUp')
    assert '"tellstate" = %s' in where
    assert '"aicallinfostate" = %s' in where
    assert parameters == ['Unchecked','FollowUp']

def test_call_type_filter_rejects_unbounded_values():
    with pytest.raises(ValueError):
        database.list_calls(call_type='X' * 61)


def test_operator_and_group_filters_are_parameterized():
    where,params=database.filters(None,None,None,operator="Test Operator")
    assert '"vw_danix_base_info_users_name" = %s' in where
    assert params==['Test Operator']
    where,params=database.filters(None,None,None,operator_names=['Test Operator','Other'])
    assert '"vw_danix_base_info_users_name" = ANY(%s)' in where
    assert params==[['Test Operator','Other']]
    where,params=database.filters(None,None,None,operator_names=[])
    assert 'FALSE' in where
    assert params==[]


def test_unspecified_operator_includes_missing_and_blank_rows():
    where,params=database.filters(None,None,None,operator=database.UNSPECIFIED)
    assert '"vw_danix_base_info_users_name" IS NULL' in where
    assert 'BTRIM' in where
    assert params==[]
    where,params=database.filters(None,None,None,
                                 operator_names=[database.UNSPECIFIED,'Test'])
    assert 'IS NULL' in where
    assert 'ANY(%s)' in where
    assert params==[['Test']]
