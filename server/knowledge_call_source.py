"""Synthetic-only read-only source adapter. Raw text leaves only as transient input."""

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import os
import re

import psycopg

from .knowledge_call_contract import SOURCE_FIELDS, UnsupportedCallContract, require_synthetic_call_contract


SOURCE_DATABASE = "panadan_call_source_ci"
SOURCE_READER = "panadan_call_source_reader_ci"
SOURCE_PASSWORD = "synthetic_call_source_password_only"
MAX_TRANSCRIPT_BYTES = 262_144
MAX_PAGE_SIZE = 50
MAX_SCOPE_WINDOW = timedelta(days=30)
MAX_ID = 2**63 - 1

_COLUMN_TYPES = (
    ("bigint", True), ("text", True), ("timestamp with time zone", True),
    ("timestamp with time zone", True), ("bigint", True), ("boolean", True),
    ("integer", False), ("text", False),
)


class CallSourceUnavailable(RuntimeError):
    """A safe source failure without connection parameters or source text."""


@dataclass(frozen=True, order=True, slots=True)
class CallCursor:
    changed_at: datetime
    call_id: int


@dataclass(frozen=True, slots=True)
class SourceCall:
    cursor: CallCursor
    operator_key: str
    event_at: datetime
    revision_no: int
    is_deleted: bool
    duration_seconds: int | None
    transcript: str | None = field(repr=False)
    transcript_oversize: bool


def _utc(value):
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("An explicit timezone-aware source timestamp is required")
    return value.astimezone(timezone.utc)


def _valid_id(value):
    return type(value) is int and 1 <= value <= MAX_ID


def _window(event_start, event_end):
    start, end = map(_utc, (event_start, event_end))
    if not timedelta(0) < end - start <= MAX_SCOPE_WINDOW:
        raise ValueError("The source event window must be positive and at most 30 days")
    return start, end


def _verify_source(db):
    profile = db.execute("""SELECT current_database(),session_user,
        current_setting('server_version_num')::int / 10000,
        current_setting('transaction_read_only')='on',
        NOT (r.rolsuper OR r.rolcreatedb OR r.rolcreaterole OR r.rolreplication OR r.rolbypassrls),
        NOT EXISTS (SELECT 1 FROM pg_catalog.pg_auth_members m WHERE m.member=r.oid),
        NOT has_database_privilege(current_database(),'CREATE,TEMP')
        FROM pg_catalog.pg_roles r WHERE r.rolname=session_user""").fetchone()
    if profile != (SOURCE_DATABASE, SOURCE_READER, 18, True, True, True, True):
        raise CallSourceUnavailable("Synthetic call reader identity is unavailable")
    shape = db.execute("""SELECT a.attname,pg_catalog.format_type(a.atttypid,a.atttypmod),a.attnotnull
        FROM pg_catalog.pg_attribute a
        WHERE a.attrelid=to_regclass('panadan_synthetic_source.calls') AND a.attname=ANY(%s)
              AND a.attnum>0 AND NOT a.attisdropped""", (list(SOURCE_FIELDS),)).fetchall()
    if {name: (kind, required) for name, kind, required in shape} != dict(zip(SOURCE_FIELDS, _COLUMN_TYPES, strict=True)):
        raise CallSourceUnavailable("Synthetic call source fields are unavailable")
    permissions = db.execute("""SELECT c.relkind='r',
        EXISTS (SELECT 1 FROM pg_catalog.pg_constraint p JOIN pg_catalog.pg_attribute a
          ON a.attrelid=p.conrelid AND a.attname='call_id'
          WHERE p.conrelid=c.oid AND p.contype='p' AND p.convalidated AND NOT p.condeferrable
          AND p.conkey=ARRAY[a.attnum]),
        NOT has_table_privilege(c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES'),
        NOT has_any_column_privilege(c.oid,'INSERT,UPDATE,REFERENCES'),
        NOT has_schema_privilege(c.relnamespace,'CREATE'),
        NOT has_table_privilege(c.oid,'SELECT'),
        NOT EXISTS (SELECT 1 FROM pg_catalog.pg_attribute a WHERE a.attrelid=c.oid
          AND a.attnum>0 AND NOT a.attisdropped AND
          has_column_privilege(c.oid,a.attnum,'SELECT') IS DISTINCT FROM (a.attname=ANY(%s)))
        FROM pg_catalog.pg_class c WHERE c.oid=to_regclass('panadan_synthetic_source.calls')""",
        (list(SOURCE_FIELDS),)).fetchone()
    if permissions != (True,) * 7:
        raise CallSourceUnavailable("Synthetic call source identity or privileges are unsafe")


_PAGE_SQL = """SELECT call_id,operator_key,event_at,changed_at,revision_no,is_deleted,duration_seconds,
    CASE WHEN NOT is_deleted AND octet_length(transcript)<=%s THEN transcript END,
    coalesce(NOT is_deleted AND octet_length(transcript)>%s,false)
  FROM panadan_synthetic_source.calls
  WHERE operator_key=%s AND event_at>=%s AND event_at<%s AND changed_at<%s
    AND (%s::timestamptz IS NULL OR changed_at>=%s)
    AND (%s::timestamptz IS NULL OR (changed_at,call_id)>(%s,%s))
  ORDER BY changed_at,call_id
  LIMIT %s"""


class SyntheticCallReader:
    """A trusted synthetic runtime binds an approved operator before reading."""

    def __init__(self, *, port, operator_key, kind, adapter, contract_state, source_state, contract):
        require_synthetic_call_contract(kind=kind, adapter=adapter, state=contract_state, contract=contract)
        if (source_state != "active" or type(operator_key) is not str
                or not re.fullmatch(r"[a-z][a-z0-9_.-]{0,79}", operator_key)):
            raise UnsupportedCallContract("Synthetic call source scope is unavailable")
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("An explicit synthetic source port is required")
        self._port = port
        self._operator_key = operator_key

    @contextmanager
    def _connect(self):
        if any(value for name, value in os.environ.items() if name.startswith("PG")):
            raise CallSourceUnavailable("Inherited database configuration is not allowed")
        try:
            with psycopg.connect(host="127.0.0.1", port=self._port, dbname=SOURCE_DATABASE,
                    user=SOURCE_READER, password=SOURCE_PASSWORD, sslmode="disable", connect_timeout=3,
                    options="-c search_path=pg_catalog -c statement_timeout=3000 -c lock_timeout=1000") as db:
                db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                _verify_source(db)
                yield db
        except psycopg.Error:
            raise CallSourceUnavailable("Synthetic call source read failed") from None

    def read_page(self, *, event_start, event_end, changed_before, changed_since=None, after=None, limit=MAX_PAGE_SIZE):
        start, end = _window(event_start, event_end)
        cutoff = _utc(changed_before)
        if type(limit) is not int or not 1 <= limit <= MAX_PAGE_SIZE:
            raise ValueError("Invalid synthetic source page limit")
        if changed_since is not None:
            changed_since = _utc(changed_since)
            if changed_since >= cutoff:
                raise ValueError("The change cutoff must follow the lower bound")
        if after is not None:
            if type(after) is not CallCursor or not _valid_id(after.call_id):
                raise ValueError("Invalid synthetic source cursor")
            after = CallCursor(_utc(after.changed_at), after.call_id)
            if after.changed_at >= cutoff:
                raise ValueError("The source cursor must precede the change cutoff")
        after_time, after_id = (after.changed_at, after.call_id) if after else (None, None)
        with self._connect() as db:
            rows = db.execute(_PAGE_SQL, (
                MAX_TRANSCRIPT_BYTES, MAX_TRANSCRIPT_BYTES, self._operator_key,
                start, end, cutoff, changed_since, changed_since, after_time, after_time, after_id, limit,
            )).fetchall()

        calls = []
        for call_id, operator, event_at, changed_at, revision, deleted, duration, text, oversize in rows:
            event_at = _utc(event_at)
            cursor = CallCursor(_utc(changed_at), call_id)
            if (operator != self._operator_key or not _valid_id(call_id) or not _valid_id(revision)
                    or not start <= event_at < end or cursor.changed_at >= cutoff
                    or (changed_since is not None and cursor.changed_at < changed_since)
                    or (after is not None and cursor <= after)):
                raise CallSourceUnavailable("Synthetic call source returned an ambiguous row")
            calls.append(SourceCall(cursor, operator, event_at, revision, deleted, duration, text, oversize))
            after = cursor
        return tuple(calls)

    def check_scope(self, *, known_ids, event_start, event_end):
        """Check already-collected identities without projecting any source content."""
        start, end = _window(event_start, event_end)
        if (type(known_ids) is not tuple or len(known_ids) > MAX_PAGE_SIZE
                or not all(_valid_id(value) for value in known_ids)):
            raise ValueError("Invalid collection reconciliation scope")
        if not known_ids:
            return {}
        with self._connect() as db:
            rows = db.execute("""SELECT call_id,operator_key=%s AND event_at>=%s AND event_at<%s AND NOT is_deleted
                FROM panadan_synthetic_source.calls WHERE call_id=ANY(%s)""",
                (self._operator_key, start, end, list(known_ids))).fetchall()
        return dict(rows)
