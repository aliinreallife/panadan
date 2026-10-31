"""Tests for bounded, safe retries of read-only PostgreSQL reporting."""
import psycopg
import pytest

from server.reporting_retries import (
    RETRY_DELAY_SECONDS, is_transient_connection_failure, read_with_retry,
)


def test_retry_once_after_connection_failure_and_succeed():
    counts = []
    delays = []
    def read_only():
        counts.append('SELECT only')
        if len(counts) == 1:
            raise psycopg.OperationalError('never log this secret')
        return {'items': [1, 2]}
    assert read_with_retry(read_only, sleep=delays.append) == {'items': [1, 2]}
    assert len(counts) == 2
    assert delays == [RETRY_DELAY_SECONDS]


def test_two_connection_errors_propagate_after_single_retry():
    counts, delays = [], []
    def failing_read():
        counts.append(1)
        raise psycopg.OperationalError('network unrecoverable')
    with pytest.raises(psycopg.OperationalError):
        read_with_retry(failing_read, sleep=delays.append)
    assert len(counts) == 2
    assert delays == [RETRY_DELAY_SECONDS]


@pytest.mark.parametrize('error', [
    ValueError('bad filter'), RuntimeError('programmer mistake'),
    psycopg.errors.UndefinedColumn('bad column'),
    psycopg.errors.QueryCanceled('statement timeout'),
    psycopg.errors.InsufficientPrivilege('permission error')
])
def test_non_transient_or_non_connection_errors_never_retry(error):
    delays, counts = [], []
    def broken_sql():
        counts.append(1)
        raise error
    with pytest.raises(type(error)):
        read_with_retry(broken_sql, sleep=delays.append)
    assert counts == [1]
    assert delays == []


def test_sqlstate_connection_is_retryable_even_for_unusual_driver_exception():
    class LostConnection(Exception):
        sqlstate = '08006'
    assert is_transient_connection_failure(LostConnection())
    assert is_transient_connection_failure(psycopg.OperationalError())
    assert not is_transient_connection_failure(ValueError())
    assert not is_transient_connection_failure(psycopg.errors.QueryCanceled())
