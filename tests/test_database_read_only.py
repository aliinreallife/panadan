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
