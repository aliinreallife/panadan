#!/usr/bin/env python3
"""Read-only, metadata-only off-site backup freshness gate.

This does NOT prove decryptability, integrity, independence of the remote, or
recoverability. Use a separate independent restore drill for those.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
import re
import subprocess
import sys

STORES = {
    "sqlite": (
        "PANADAN_BACKUP_RCLONE_DEST",
        re.compile(r"^auth-(\d{8}T\d{6}Z)-[0-9]+\.sqlite\.age$"),
        "auth-*.sqlite.age",
    ),
    "platform": (
        "PANADAN_PLATFORM_BACKUP_RCLONE_DEST",
        re.compile(r"^panadan-(\d{8}T\d{6}Z)-[0-9a-f]{16}\.dump\.age$"),
        "panadan-*.dump.age",
    ),
}
REMOTE_RE = re.compile(r"^[A-Za-z0-9_-]+:[^\s\x00-\x1f]+$")


def backup_age_hours(objects: object, pattern: re.Pattern[str], now: datetime) -> float | None:
    """Return age of newest plausible complete-sized backup, or None.

    Use timestamps encoded by the backup scripts rather than remote ModTime,
    which can change when an old object is copied or restored. This is only a
    freshness heuristic, never a proof the ciphertext is valid.
    """
    if not isinstance(objects, list):
        raise ValueError("Unexpected rclone listing format")
    candidates: list[float] = []
    for item in objects:
        if not isinstance(item, dict) or item.get("IsDir") is True:
            continue
        name = item.get("Name")
        size = item.get("Size")
        if not isinstance(name, str) or not isinstance(size, int) or isinstance(size, bool):
            continue
        if size < 128:
            continue
        match = pattern.fullmatch(name)
        if not match:
            continue
        try:
            timestamp = datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        age = (now - timestamp).total_seconds() / 3600
        # Clock-skew and filenames dated into the future must not pass a
        # backup freshness gate.
        if age >= 0:
            candidates.append(age)
    return min(candidates) if candidates else None


def read_remote(remote: str, include: str) -> object:
    # Never log remote path or subprocess stderr; it may contain cloud IDs.
    # No shell=True, no credentials passed on argv, no customer content reads.
    try:
        result = subprocess.run(
            ["rclone", "lsjson", "--files-only", "--max-depth", "1",
             "--include", include, remote],
            capture_output=True, text=True, check=True, timeout=30,
        )
        if len(result.stdout) > 4_000_000:
            raise ValueError("Remote listing exceeds safety bound")
        return json.loads(result.stdout)
    except (OSError, ValueError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Unable to inspect encrypted off-site backup metadata") from None


def run(store: str, max_age_hours: float, env: dict[str, str], now: datetime) -> int:
    selected = ("sqlite", "platform") if store == "both" else (store,)
    config: list[tuple[str, str, re.Pattern[str], str]] = []
    for name in selected:
        var, pattern, include = STORES[name]
        remote = env.get(var, "")
        if not REMOTE_RE.fullmatch(remote):
            print(f"CONFIG ERROR: {name} off-site remote not configured", file=sys.stderr)
            return 2
        config.append((name, remote, pattern, include))

    failed = False
    for name, remote, pattern, include in config:
        try:
            age = backup_age_hours(read_remote(remote, include), pattern, now)
        except (RuntimeError, ValueError):
            print(f"FAIL: {name} off-site backup metadata unavailable", file=sys.stderr)
            failed = True
            continue
        if age is None:
            print(f"FAIL: {name} has no recognized encrypted off-site backup", file=sys.stderr)
            failed = True
        elif age > max_age_hours:
            print(f"FAIL: {name} backup older than the configured threshold", file=sys.stderr)
            failed = True
        else:
            print(f"PASS: {name} backup timestamp is within the configured freshness threshold")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", choices=("sqlite", "platform", "both"), default="both")
    parser.add_argument("--max-age-hours", type=float, required=True,
                        help="Operator-approved backup freshness limit (1–720 hours); no implicit RPO")
    args = parser.parse_args()
    if (not math.isfinite(args.max_age_hours)
            or not 1 <= args.max_age_hours <= 720):
        parser.error("--max-age-hours must be between 1 and 720")
    return run(args.store, args.max_age_hours, os.environ, datetime.now(timezone.utc))


if __name__ == "__main__":
    raise SystemExit(main())
