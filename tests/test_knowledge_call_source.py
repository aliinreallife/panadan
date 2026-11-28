"""M02.2: fixed call-source contract, read-only credentials and bounded scope."""

from datetime import datetime, timedelta, timezone
import os

import psycopg
from psycopg import errors
import pytest

from server.knowledge_call_contract import SOURCE_FIELDS, SYNTHETIC_ADAPTER, UnsupportedCallContract, synthetic_call_contract
from server.knowledge_call_privacy import prepare_call
from server.knowledge_call_source import (
    CallCursor,
    CallSourceUnavailable,
    MAX_TRANSCRIPT_BYTES,
    SOURCE_DATABASE,
    SOURCE_PASSWORD,
    SOURCE_READER,
    SyntheticCallReader,
)
from test_knowledge_foundation import _reject, _validate_dsn, db


START = datetime(2026, 10, 1, tzinfo=timezone.utc)
END = START + timedelta(days=30)
CHANGED = END + timedelta(hours=1)
CUTOFF = CHANGED + timedelta(days=1)
WINDOW = dict(event_start=START, event_end=END, changed_before=CUTOFF)
CANARY = "Synthetic source original"


def _reader(port=48701, **overrides):
    config = dict(port=port, operator_key="operator-a", kind="database", adapter=SYNTHETIC_ADAPTER,
                  contract_state="synthetic", source_state="active", contract=synthetic_call_contract())
    return SyntheticCallReader(**(config | overrides))


@pytest.fixture
def source(db):
    cfg = _validate_dsn(os.environ["PANADAN_PLATFORM_TEST_DSN"], os.environ["PANADAN_PLATFORM_TEST_ALLOW_RESET"])
    db.rollback()
    db.autocommit = True
    assert db.execute("SELECT 1 FROM pg_database WHERE datname=%s", (SOURCE_DATABASE,)).fetchone() is None
    assert db.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (SOURCE_READER,)).fetchone() is None
    db.execute(f"CREATE DATABASE {SOURCE_DATABASE} TEMPLATE template0")
    try:
        db.execute(f"CREATE ROLE {SOURCE_READER} LOGIN NOINHERIT PASSWORD '{SOURCE_PASSWORD}'")
        try:
            db.execute(f"REVOKE ALL ON DATABASE {SOURCE_DATABASE} FROM PUBLIC")
            db.execute(f"GRANT CONNECT ON DATABASE {SOURCE_DATABASE} TO {SOURCE_READER}")
            cfg.update(dbname=SOURCE_DATABASE)
            with psycopg.connect(**cfg, autocommit=True, connect_timeout=5) as admin:
                admin.execute("CREATE SCHEMA panadan_synthetic_source")
                admin.execute("""CREATE TABLE panadan_synthetic_source.calls (
                    call_id bigint PRIMARY KEY,
                    operator_key text NOT NULL,
                    event_at timestamptz NOT NULL,
                    changed_at timestamptz NOT NULL,
                    revision_no bigint NOT NULL,
                    is_deleted boolean NOT NULL,
                    duration_seconds integer,
                    transcript text,
                    excluded_field text)""")
                admin.execute(f"GRANT USAGE ON SCHEMA panadan_synthetic_source TO {SOURCE_READER}")
                admin.execute(f"GRANT SELECT ({','.join(SOURCE_FIELDS)}) ON panadan_synthetic_source.calls TO {SOURCE_READER}")
                yield admin, int(cfg["port"]), cfg
        finally:
            db.execute(f"REVOKE CONNECT ON DATABASE {SOURCE_DATABASE} FROM {SOURCE_READER}")
            db.execute(f"DROP DATABASE {SOURCE_DATABASE}")
            db.execute(f"DROP ROLE {SOURCE_READER}")
    finally:
        if db.execute("SELECT 1 FROM pg_database WHERE datname=%s", (SOURCE_DATABASE,)).fetchone():
            db.execute(f"DROP DATABASE {SOURCE_DATABASE}")


def _row(admin, call_id, *, operator="operator-a", event_at=START, changed_at=CHANGED, revision=1,
         deleted=False, duration=77, text=CANARY):
    admin.execute("""INSERT INTO panadan_synthetic_source.calls
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'excluded-canary')""",
        (call_id, operator, event_at, changed_at, revision, deleted, duration, text))


def test_reader_denies_disabled_source_and_unverified_scope_before_connecting(monkeypatch):
    for config in ({"source_state": "disabled"}, {"operator_key": None}, {"operator_key": "different operator"},
                   {"contract_state": "draft"}, {"kind": "manual"}):
        with pytest.raises(UnsupportedCallContract):
            _reader(**config)
    monkeypatch.setenv("PGHOSTADDR", "192.0.2.1")
    with pytest.raises(CallSourceUnavailable, match="Inherited database"):
        _reader().read_page(**WINDOW)


def test_reader_refuses_unbounded_inputs_and_ambiguous_local_clock():
    for invalid in (
        {"event_start": START.replace(tzinfo=None)}, {"event_end": END + timedelta(seconds=1)},
        {"event_end": START}, {"changed_before": CHANGED.replace(tzinfo=None)},
        {"after": CallCursor(CHANGED, 0)}, {"after": CallCursor(CUTOFF, 1)}, {"limit": 51},
    ):
        with pytest.raises(ValueError):
            _reader().read_page(**(WINDOW | invalid))


def test_reader_paginates_exact_operator_and_half_open_window_without_altering_source(source):
    admin, port, cfg = source
    # The lower event bound is included. The upper event bound, later change,
    # other operator and pre-window event are excluded.
    _row(admin, 1, event_at=START)
    _row(admin, 2, event_at=END - timedelta(microseconds=1), revision=2)
    _row(admin, 3, event_at=END)
    _row(admin, 4, event_at=START - timedelta(microseconds=1))
    _row(admin, 5, operator="operator-b")
    _row(admin, 6, changed_at=CUTOFF)
    _row(admin, 7, changed_at=CHANGED + timedelta(minutes=1), deleted=True)
    _row(admin, 8, changed_at=CHANGED + timedelta(minutes=2), text="ت" * (MAX_TRANSCRIPT_BYTES // 2 + 1))
    _row(admin, 9, changed_at=CHANGED + timedelta(minutes=3), text=None, duration=None)

    reader = _reader(port)
    before = admin.execute("SELECT call_id,md5(transcript) FROM panadan_synthetic_source.calls ORDER BY call_id").fetchall()
    head = reader.read_page(**WINDOW, limit=1)
    assert [row.cursor.call_id for row in head] == [1]
    assert head[0].transcript == CANARY and CANARY not in repr(head)
    tail = reader.read_page(**WINDOW, after=head[0].cursor)
    assert [row.cursor.call_id for row in tail] == [2, 7, 8, 9]
    assert tail[0].revision_no == 2 and tail[0].event_at == END - timedelta(microseconds=1)
    assert tail[1].is_deleted and tail[1].transcript is None
    assert tail[2].transcript is None and tail[2].transcript_oversize
    assert tail[3].transcript is None and not tail[3].transcript_oversize
    assert not reader.read_page(**WINDOW, after=tail[-1].cursor)
    assert admin.execute("SELECT call_id,md5(transcript) FROM panadan_synthetic_source.calls ORDER BY call_id").fetchall() == before

    with psycopg.connect(**(cfg | {"user": SOURCE_READER, "password": SOURCE_PASSWORD})) as reader_db:
        _reject(reader_db, errors.InsufficientPrivilege, "UPDATE panadan_synthetic_source.calls SET duration_seconds=0")
        _reject(reader_db, errors.InsufficientPrivilege, "SELECT excluded_field FROM panadan_synthetic_source.calls")
        _reject(reader_db, errors.InsufficientPrivilege, "CREATE TEMP TABLE forbidden (id int)")


def test_reader_refuses_ambiguous_identity_and_broader_source_privileges(source):
    admin, port, _ = source
    reader = _reader(port)
    admin.execute("ALTER TABLE panadan_synthetic_source.calls DROP CONSTRAINT calls_pkey")
    admin.execute("ALTER TABLE panadan_synthetic_source.calls ALTER COLUMN call_id SET NOT NULL")
    with pytest.raises(CallSourceUnavailable, match="identity or privileges"):
        reader.read_page(**WINDOW)
    admin.execute("ALTER TABLE panadan_synthetic_source.calls ADD PRIMARY KEY (call_id)")
    admin.execute(f"GRANT UPDATE (duration_seconds) ON panadan_synthetic_source.calls TO {SOURCE_READER}")
    with pytest.raises(CallSourceUnavailable, match="identity or privileges"):
        reader.read_page(**WINDOW)
    admin.execute(f"REVOKE UPDATE (duration_seconds) ON panadan_synthetic_source.calls FROM {SOURCE_READER}")
    admin.execute(f"GRANT SELECT (excluded_field) ON panadan_synthetic_source.calls TO {SOURCE_READER}")
    with pytest.raises(CallSourceUnavailable, match="identity or privileges"):
        reader.read_page(**WINDOW)


def test_reader_refuses_malformed_rows_and_missing_source_fields(source):
    admin, port, _ = source
    _row(admin, 1, revision=0)
    with pytest.raises(CallSourceUnavailable, match="ambiguous row"):
        _reader(port).read_page(**WINDOW)
    admin.execute("ALTER TABLE panadan_synthetic_source.calls ALTER COLUMN event_at DROP NOT NULL")
    with pytest.raises(CallSourceUnavailable, match="fields are unavailable"):
        _reader(port).read_page(**WINDOW)


def test_source_to_filter_boundary_yields_only_filtered_text_and_keeps_source(source):
    admin, port, _ = source
    original = "بلیط رفت‌وبرگشت، تلفن ۰۹۱۲۳۴۵۶۷۸۹ و contact-canary@example.invalid"
    _row(admin, 1, text=original)
    call, = _reader(port).read_page(**WINDOW)
    prepared = prepare_call(call)
    assert prepared.representation.text == "بلیط رفت‌وبرگشت، تلفن [PHONE] و [EMAIL]"
    assert "contact-canary" not in repr(prepared)
    assert admin.execute("SELECT transcript FROM panadan_synthetic_source.calls").fetchone() == (original,)
