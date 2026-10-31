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


def public_call_facts(payload: Mapping[str, object]) -> dict[str, object]:
    """Small allowlist; never copies transcript, names, phones or AI prose.

    Facts are transformations, not proof of sales or call event timing.
    """
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object")
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


def process_next(conn) -> bool:
    """Atomically claim/process one job (SKIP LOCKED) with versioned facts.

    A SQL/processing failure rolls back the job and facts for a later retry.
    The pending queue is not an external queue; separate processes may safely
    call this function concurrently on Panadan's own PostgreSQL connection.
    """
    with conn.transaction():
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
