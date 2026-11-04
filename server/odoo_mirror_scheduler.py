"""Explicitly approved, scheduled-*by-operator* full-view reconciliation ticks.

This module has NO daemon, CronJob, timer registration or production startup
hook. An external scheduler may invoke one bounded tick only AFTER the source
owner approves copying sensitive records and the target source is manually
enabled. Each tick re-checks four approvals and obtains the existing exclusive
pilot lock. No Odoo writes, deletion, public endpoint or raw customer logging.
"""
from __future__ import annotations

import argparse
import sys
import time

from . import database, odoo_full_mirror_pilot as pilot
from . import odoo_sync_pilot as guarded
from .platform_processing import process_next

# Even if operators supply huge CLI values, enforce a small, bounded tick.
MAX_PAGES = 10
MAX_PROCESS_JOBS = 2000
MAX_TICK_SECONDS = 120
DEFAULT_MIN_PASS_GAP_SECONDS = 3600
DEFAULT_MAX_BACKLOG = 2500


def decision(status: dict, *, min_pass_gap_seconds: int,
             max_backlog: int) -> str:
    """Pure policy; do not start a fresh pass until its quiet period elapses."""
    if (type(min_pass_gap_seconds) is not int
            or not 300 <= min_pass_gap_seconds <= 7 * 86400):
        raise ValueError("Pass gap must be between five minutes and seven days")
    if type(max_backlog) is not int or not 100 <= max_backlog <= 10000:
        raise ValueError("Invalid processing backlog threshold")
    if not status.get("source_registered") or not status.get("source_enabled"):
        return "disabled"
    if status.get("processing_failed", 0):
        return "failed_processing"
    if status.get("processing_pending", 0) >= max_backlog:
        return "backpressure"
    if status.get("snapshot_in_progress"):
        return "resume"
    last_age = status.get("seconds_since_last_commit")
    if last_age is None:
        return "initial"
    if type(last_age) is not int or last_age < 0:
        return "invalid_freshness"
    return "new_pass" if last_age >= min_pass_gap_seconds else "quiet_period"


def process_backlog(target, *, max_jobs: int, deadline: float) -> int:
    """Process only full-mirror jobs, with finite work/time budgets."""
    if type(max_jobs) is not int or not 0 <= max_jobs <= MAX_PROCESS_JOBS:
        raise ValueError("Invalid mirror processing budget")
    processed = 0
    for _ in range(max_jobs):
        if time.monotonic() >= deadline:
            break
        if not process_next(target, source_key=pilot.SOURCE_KEY):
            break
        processed += 1
    return processed


def _run_snapshot_budget(source, target, *, pages: int, batch_size: int,
                         deadline: float) -> dict:
    """Run a bounded amount of already checkpointed work, then stop.

    A timeout between pages does not invalidate already committed pages.
    Repeated ticks never auto-replay a completed pass within the same tick.
    """
    result = {
        "pages": 0, "source_rows": 0, "calls": 0,
        "changed": 0, "unchanged": 0, "pass_complete": False,
    }
    for _ in range(pages):
        if time.monotonic() >= deadline:
            break
        part = pilot._snapshot(source, target, limit=batch_size)
        if result["pages"] == 0:
            result["pass"] = part["pass"]
        elif part["pass"] != result["pass"]:
            raise RuntimeError("Reconciliation pass changed unexpectedly")
        result["pages"] += 1
        for key in ("source_rows", "calls", "changed", "unchanged"):
            result[key] += part[key]
        result["pass_complete"] = part["pass_complete"]
        if part["pass_complete"]:
            break
    return result


def tick(args: argparse.Namespace) -> dict:
    """One supervised run: backlog processing, pause gate, then bounded scan."""
    pilot.require_approval(args)
    if (type(args.max_process_jobs) is not int
            or not 0 <= args.max_process_jobs <= MAX_PROCESS_JOBS
            or type(args.max_tick_seconds) is not int
            or not 10 <= args.max_tick_seconds <= MAX_TICK_SECONDS):
        raise ValueError("Invalid tick resource budget")
    deadline = time.monotonic() + args.max_tick_seconds
    with guarded.owned_connection() as target:
        with guarded.exclusive_pilot(target):
            before = pilot.local_status(target)
            # No processing or source IO if the source has not been enabled
            # by a separate administrative approval.
            if not before["source_enabled"] or not before["source_registered"]:
                raise ValueError("Full mirror source is not explicitly enabled")
            if before["processing_failed"]:
                raise RuntimeError("Mirror processing failure requires intervention")

            processed = process_backlog(
                target, max_jobs=args.max_process_jobs, deadline=deadline)
            status = pilot.local_status(target)
            action = decision(
                status, min_pass_gap_seconds=args.min_pass_gap_seconds,
                max_backlog=args.max_backlog)
            outcome = {
                "decision": action,
                "processed": processed,
                "pending": status["processing_pending"],
                "failed": status["processing_failed"],
                "pages": 0, "pass_complete": False,
            }
            if action not in ("initial", "resume", "new_pass"):
                return outcome

            if time.monotonic() >= deadline:
                outcome["decision"] = "time_budget"
                return outcome
            # Retain the pre-existing read-only source connection with its
            # server-side statement timeout and no privileged Odoo account.
            with database.connect() as source:
                result = _run_snapshot_budget(
                    source, target, pages=args.max_pages,
                    batch_size=args.batch_size, deadline=deadline)
            outcome.update(result)
            return outcome


def health(status: dict, *, max_stale_seconds: int = 86400) -> dict:
    """Return no identifiers or payloads; non-zero CLI exit if unhealthy."""
    if (type(max_stale_seconds) is not int
            or not 300 <= max_stale_seconds <= 30 * 86400):
        raise ValueError("Invalid freshness alert threshold")
    if not status["source_registered"] or not status["source_enabled"]:
        signal = "disabled"
    elif status["processing_failed"]:
        signal = "processing_failed"
    elif status["seconds_since_last_commit"] is None:
        signal = "not_started"
    elif status["seconds_since_last_commit"] >= max_stale_seconds:
        signal = "stale"
    else:
        signal = "healthy"
    return {
        "signal": signal,
        "source_enabled": status["source_enabled"],
        "completed_passes": status["completed_passes"],
        "snapshot_in_progress": status["snapshot_in_progress"],
        "last_page_age_seconds": status["seconds_since_last_commit"],
        "pending_jobs": status["processing_pending"],
        "failed_jobs": status["processing_failed"],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("tick", "health"))
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument("--max-process-jobs", type=int, default=1200)
    parser.add_argument("--max-tick-seconds", type=int, default=120)
    parser.add_argument("--min-pass-gap-seconds", type=int,
                        default=DEFAULT_MIN_PASS_GAP_SECONDS)
    parser.add_argument("--max-backlog", type=int, default=DEFAULT_MAX_BACKLOG)
    parser.add_argument("--max-stale-seconds", type=int, default=86400)
    parser.add_argument("--mode", choices=("utc_naive",), default="utc_naive")
    for name in pilot.REQUIRED_ACKS:
        parser.add_argument("--" + name.replace("_", "-"), action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "tick":
            # One tick is internally equivalent to one snapshot-run budget.
            args.command = "snapshot-run"
            print("FULL MIRROR TICK:", tick(args))
            return 0
        with guarded.owned_connection() as target:
            result = health(
                pilot.local_status(target),
                max_stale_seconds=args.max_stale_seconds)
        print("FULL MIRROR HEALTH:", result)
        return 0 if result["signal"] == "healthy" else 3
    except Exception as exc:
        state = getattr(exc, "sqlstate", None)
        state = state if isinstance(state, str) and len(state) == 5 and state.isalnum() else "unknown"
        print(f"FULL MIRROR TICK FAILED: {type(exc).__name__} SQLSTATE={state}",
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
