"""Opt-in transactional, source-agnostic raw-record ingestion.

This module deliberately has NO Odoo, VPN, or dashboard integration.
Callers must provide a separate authorized Panadan PostgreSQL connection and
an explicitly enabled source. No credentials, customer data or payload are logged.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from collections.abc import Mapping, Sequence
import json
import re

from psycopg.types.json import Jsonb


SOURCE_KEY = re.compile(r"^[a-z][a-z0-9_-]{1,62}$")
KINDS = frozenset({"database", "api", "file", "event", "manual"})
MAX_EVENTS = 500
PIPELINE_NAME = "normalize"
PIPELINE_VERSION = "v1"


class StaleCheckpointError(RuntimeError):
    """Another worker already advanced this source stream."""


@dataclass(frozen=True)
class SourceEvent:
    external_id: str
    operation: str
    payload: Mapping[str, object] | None = None


@dataclass(frozen=True)
class BatchResult:
    examined: int
    upserted: int
    deleted: int
    unchanged: int


def _json_bytes(value: object, limit: int) -> bytes:
    try:
        encoded = json.dumps(value, sort_keys=True, ensure_ascii=False,
                             allow_nan=False, separators=(",", ":")).encode("utf-8")
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("Invalid JSON value") from None
    if len(encoded) > limit:
        raise ValueError("JSON value exceeds allowed size")
    return encoded


def _validate_source(source_key: str, stream: str) -> None:
    if not isinstance(source_key, str) or not SOURCE_KEY.fullmatch(source_key):
        raise ValueError("Invalid source key")
    if not isinstance(stream, str) or not 1 <= len(stream) <= 80 or "\x00" in stream:
        raise ValueError("Invalid stream identifier")


def _validate_events(events: Sequence[SourceEvent]) -> list[tuple[SourceEvent, str | None]]:
    if not isinstance(events, (list, tuple)) or len(events) > MAX_EVENTS:
        raise ValueError("Invalid batch size")
    checked = []
    for event in events:
        if not isinstance(event, SourceEvent):
            raise ValueError("Invalid source event")
        if not isinstance(event.external_id, str) or not 1 <= len(event.external_id) <= 512 or "\x00" in event.external_id:
            raise ValueError("Invalid external ID")
        if event.operation == "upsert":
            if not isinstance(event.payload, dict) or any(not isinstance(key, str) for key in event.payload):
                raise ValueError("Expected a JSON object")
            serialized = _json_bytes(event.payload, limit=2_000_000)
            digest = sha256(serialized).hexdigest()
        elif event.operation == "delete":
            if event.payload is not None:
                raise ValueError("Tombstones must not carry a payload")
            digest = None
        else:
            raise ValueError("Invalid operation")
        checked.append((event, digest))
    return checked


def register_source(conn, *, source_key: str, kind: str, label: str) -> None:
    """Register an initially DISABLED source; activation is a separate decision."""
    _validate_source(source_key, "default")
    if kind not in KINDS or not isinstance(label, str) or not 1 <= len(label) <= 120:
        raise ValueError("Invalid source metadata")
    with conn.transaction():
        conn.execute(
            """INSERT INTO panadan_ingest.sources(source_key, kind, label)
               VALUES (%s, %s, %s) ON CONFLICT (source_key) DO NOTHING""",
            (source_key, kind, label),
        )


def ingest_batch(conn, *, source_key: str, stream: str,
                 events: Sequence[SourceEvent],
                 expected_cursor: Mapping[str, object] | None,
                 next_cursor: Mapping[str, object] | None) -> BatchResult:
    """Write revisions, jobs, run stats and cursor in one ACID transaction.

    - The owner-only lock helper protects source enablement until commit.
    - SELECT/lock on (source,stream) serializes concurrent workers.
    - CAS expected_cursor prevents stale workers from overwriting checkpoints.
    - Same content replay creates no new revision/job.
    - Tombstones ONLY come from explicit upstream change events; never infer
      deletion because a row was absent from a bounded/partial view page.
    - Enabled source must be separately approved. Never call on a source DB.
    """
    _validate_source(source_key, stream)
    checked = _validate_events(events)
    for cursor in (expected_cursor, next_cursor):
        if cursor is not None:
            if not isinstance(cursor, dict):
                raise ValueError("Cursor must be a JSON object")
            _json_bytes(cursor, limit=4096)
    with conn.transaction():
        source = conn.execute(
            "SELECT panadan_ingest.lock_source_for_ingest(%s) AS enabled",
            (source_key,),
        ).fetchone()
        if not source or not source["enabled"]:
            raise ValueError("Source is not enabled")

        conn.execute(
            """INSERT INTO panadan_ingest.sync_checkpoints(source_key, stream, cursor)
               VALUES (%s, %s, NULL)
               ON CONFLICT (source_key, stream) DO NOTHING""",
            (source_key, stream),
        )
        checkpoint = conn.execute(
            """SELECT cursor FROM panadan_ingest.sync_checkpoints
               WHERE source_key = %s AND stream = %s FOR UPDATE""",
            (source_key, stream),
        ).fetchone()
        if checkpoint["cursor"] != expected_cursor:
            raise StaleCheckpointError("Source checkpoint changed")

        changed, deleted, unchanged = 0, 0, 0
        for event, digest in checked:
            conn.execute(
                """INSERT INTO panadan_ingest.source_records(source_key, external_id)
                   VALUES (%s, %s) ON CONFLICT (source_key, external_id) DO NOTHING""",
                (source_key, event.external_id),
            )
            current = conn.execute(
                """SELECT revision_no, current_digest, is_deleted
                   FROM panadan_ingest.source_records
                   WHERE source_key = %s AND external_id = %s FOR UPDATE""",
                (source_key, event.external_id),
            ).fetchone()
            tombstone = event.operation == "delete"
            if current["revision_no"] > 0 and current["is_deleted"] == tombstone and (
                tombstone or current["current_digest"] == digest
            ):
                unchanged += 1
                continue

            revision = current["revision_no"] + 1
            record = conn.execute(
                """INSERT INTO panadan_ingest.raw_revisions(
                       source_key, external_id, revision_no, operation, payload, digest)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   RETURNING revision_id""",
                (source_key, event.external_id, revision, event.operation,
                 Jsonb(dict(event.payload)) if not tombstone else None, digest),
            ).fetchone()
            conn.execute(
                """UPDATE panadan_ingest.source_records
                   SET revision_no = %s, current_digest = %s, is_deleted = %s,
                       last_changed_at = now()
                   WHERE source_key = %s AND external_id = %s""",
                (revision, digest, tombstone, source_key, event.external_id),
            )
            conn.execute(
                """INSERT INTO panadan_ingest.processing_jobs(
                       revision_id, processor, processor_version)
                   VALUES (%s, %s, %s) ON CONFLICT DO NOTHING""",
                (record["revision_id"], PIPELINE_NAME, PIPELINE_VERSION),
            )
            if tombstone:
                deleted += 1
            else:
                changed += 1

        conn.execute(
            """UPDATE panadan_ingest.sync_checkpoints
               SET cursor = %s, updated_at = now()
               WHERE source_key = %s AND stream = %s""",
            (Jsonb(dict(next_cursor)) if next_cursor is not None else None, source_key, stream),
        )
        conn.execute(
            """INSERT INTO panadan_ingest.sync_runs(
                   source_key, stream, examined, changed, deleted)
               VALUES (%s, %s, %s, %s, %s)""",
            (source_key, stream, len(checked), changed, deleted),
        )
    return BatchResult(len(checked), changed, deleted, unchanged)


def checkpoint(conn, *, source_key: str, stream: str) -> dict | None:
    _validate_source(source_key, stream)
    row = conn.execute(
        """SELECT cursor FROM panadan_ingest.sync_checkpoints
           WHERE source_key = %s AND stream = %s""", (source_key, stream)
    ).fetchone()
    return row["cursor"] if row else None
