"""Deterministic v1 processing of explicitly approved, non-sensitive call fields.

This is a library-only pipeline prototype: NOT scheduled, NOT wired to live
Odoo, dashboard, API or MCP. Source payloads never appear in logs, errors or
test reports. Future processors can be independently versioned/replayed.
"""
from __future__ import annotations

from collections.abc import Mapping
import math
import re

from psycopg.types.json import Jsonb

from .platform_ingest import PIPELINE_NAME, PIPELINE_VERSION


ENUM = re.compile(r"^[A-Za-z0-9_]{1,60}$")
DIRECTIONS = {"IntoOut": "outgoing", "OutToIn": "incoming"}


# These are deliberately the only raw fields that the v1 facts processor
# can use. Sensitive raw 37-field variants remain in the restricted revision
# store, never in the public facts projection.
_MIRROR_SAFE_FIELDS = (
    "tellside", "tellstate", "aicallinfostate",
    "voice_length", "possibility_of_sale_ai",
)


def _uniform_mirror_facts(payload: Mapping[str, object]) -> dict[str, object]:
    """Only project facts that agree across *every* joined view variant.

    The reporting view is not unique by call id. Picking the first or highest
    score would fabricate an authoritative analysis where none is known.
    Malformed envelopes fail closed without displaying raw values.
    """
    rows = payload.get("source_rows")
    identity = payload.get("id")
    if (type(identity) is not int or identity < 1
            or not isinstance(rows, list) or not rows
            or any(not isinstance(row, dict) or row.get("id") != identity
                   for row in rows)):
        raise ValueError("Invalid full mirror source envelope")
    first = rows[0]
    return {
        name: first[name]
        for name in _MIRROR_SAFE_FIELDS
        if name in first
        and all(name in row and row[name] == first[name] for row in rows[1:])
    }


def public_call_facts(payload: Mapping[str, object]) -> dict[str, object]:
    """Small allowlist; never copies transcript, names, phones or AI prose.

    Facts are transformations, not proof of sales or call event timing.
    """
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object")
    if payload.get("source_schema") == "odoo_view_37_v1":
        payload = _uniform_mirror_facts(payload)
    out = {}
    direction = payload.get("tellside")
    if isinstance(direction, str) and direction in DIRECTIONS:
        out["call_direction"] = {"code": direction, "meaning": DIRECTIONS[direction]}
    for raw_key, fact in (
        ("tellstate", "call_type"),
        ("aicallinfostate", "ai_call_status"),
    ):
        raw = payload.get(raw_key)
        if isinstance(raw, str) and ENUM.fullmatch(raw.strip()):
            out[fact] = {"source_code": raw.strip()}
    duration = payload.get("voice_length")
    if isinstance(duration, (float, int)) and not isinstance(duration, bool) and math.isfinite(duration) and 0 <= duration < 10_000_000:
        out["recording_duration"] = {"seconds": duration}
    score = payload.get("possibility_of_sale_ai")
    if isinstance(score, (float, int)) and not isinstance(score, bool) and math.isfinite(score) and 0 <= score <= 100:
        out["ai_sales_estimate"] = {"score_0_100": score, "is_confirmed_sale": False}
    return out


def process_next(conn, *, source_key: str | None = None) -> bool:
    """Atomically claim/process one job (SKIP LOCKED) with versioned facts.

    A SQL/processing failure rolls back the job and facts for a later retry.
    Optional source scope is limited to the explicit full-mirror source so
    the supervised worker cannot accidentally drain unrelated pipelines.
    The pending queue is not an external queue; separate processes may safely
    call this function concurrently on Panadan's own PostgreSQL connection.
    """
    with conn.transaction():
        if source_key is not None:
            if source_key != "odoo_calls_full_v1":
                raise ValueError("Scoped processing supports only the reviewed full mirror")
            job = conn.execute(
                """SELECT j.job_id, j.revision_id
                   FROM panadan_ingest.processing_jobs AS j
                   JOIN panadan_ingest.raw_revisions AS r
                     ON r.revision_id=j.revision_id
                   WHERE j.status='pending' AND j.processor=%s
                     AND j.processor_version=%s AND r.source_key=%s
                   ORDER BY j.job_id FOR UPDATE OF j SKIP LOCKED LIMIT 1""",
                (PIPELINE_NAME, PIPELINE_VERSION, source_key),
            ).fetchone()
        else:
            job = conn.execute(
                """SELECT job_id, revision_id
                   FROM panadan_ingest.processing_jobs
                   WHERE status = 'pending' AND processor = %s AND processor_version = %s
                   ORDER BY job_id FOR UPDATE SKIP LOCKED LIMIT 1""",
                (PIPELINE_NAME, PIPELINE_VERSION),
            ).fetchone()
        if job is None:
            return False
        rev = conn.execute(
            """SELECT operation, payload
               FROM panadan_ingest.raw_revisions WHERE revision_id = %s""",
            (job["revision_id"],),
        ).fetchone()
        if rev is None:
            raise RuntimeError("Missing raw revision")
        facts = {} if rev["operation"] == "delete" else public_call_facts(rev["payload"])
        for key, value in facts.items():
            conn.execute(
                """INSERT INTO panadan_ingest.derived_facts(
                       revision_id, processor, processor_version, fact_key, value)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (revision_id, processor, processor_version, fact_key)
                   DO UPDATE SET value = EXCLUDED.value""",
                (job["revision_id"], PIPELINE_NAME, PIPELINE_VERSION, key, Jsonb(value)),
            )
        conn.execute(
            """UPDATE panadan_ingest.processing_jobs
               SET status = 'succeeded', attempts = attempts + 1, finished_at = now()
               WHERE job_id = %s""", (job["job_id"],),
        )
        return True
