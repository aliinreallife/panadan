#!/usr/bin/env bash
# Verify a copied, age-encrypted Panadan SQLite auth backup OFF the VPS.
# NEVER points at /data/auth.sqlite, opens a production connection, or uses Docker.
set -euo pipefail
umask 077

usage() {
  echo "Usage: bash tools/verify-offsite-auth-restore.sh ENCRYPTED_AUTH_SQLITE.age OFFSITE_AGE_IDENTITY" >&2
  exit 2
}
fail() {
  echo "FAIL: offline auth SQLite restore verification ($1)" >&2
  exit 1
}

[[ $# -eq 2 ]] || usage
ARCHIVE="$1"
IDENTITY="$2"
[[ -f "$ARCHIVE" && -s "$ARCHIVE" && ! -L "$ARCHIVE" ]] ||
  fail "encrypted auth backup must be an existing regular file"
[[ -f "$IDENTITY" && -s "$IDENTITY" && ! -L "$IDENTITY" ]] ||
  fail "offsite age identity must be an existing regular file"
for exe in age python3 mktemp rm rmdir; do
  command -v "$exe" >/dev/null 2>&1 || fail "required offline dependency missing"
done
# Keep all temporary decrypted material in memory-backed Linux tmpfs.
# Do not silently fall back to /tmp, the project directory, or the VPS.
[[ -d /dev/shm && -w /dev/shm ]] ||
  fail "memory-backed /dev/shm unavailable; use a trusted offline Linux/WSL machine"
WORK="$(mktemp -d /dev/shm/panadan-auth-restore-XXXXXXXX)" ||
  fail "unable to allocate tmpfs restore directory"
cleanup() {
  rm -f -- "$WORK/decrypted.sqlite" "$WORK/restored.sqlite" >/dev/null 2>&1 || true
  rmdir -- "$WORK" >/dev/null 2>&1 || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Off-VPS private age identity is never transmitted or printed. Do not show
# age's raw stderr (it could disclose private operator-controlled file paths).
age -d -i "$IDENTITY" -o "$WORK/decrypted.sqlite" "$ARCHIVE" >/dev/null 2>&1 ||
  fail "cannot decrypt backup with offsite age identity"

python3 - "$WORK/decrypted.sqlite" "$WORK/restored.sqlite" <<'PY'
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

source_path, restored_path = (Path(value) for value in sys.argv[1:])
required = {
    "users": {"id", "username", "password_hash", "role", "is_active"},
    "sessions": {"token_hash", "user_id", "csrf", "expires_at"},
    "access_tokens": {"id", "token_hash", "scope", "owner_id"},
}

def inspect(db):
    if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise ValueError("integrity check failed")
    tables = {
        name for (name,) in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    if not set(required).issubset(tables):
        raise ValueError("missing core authentication tables")
    for table, columns in required.items():
        existing = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
        if not columns.issubset(existing):
            raise ValueError("missing required authentication columns")
    if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        raise ValueError("account table empty")
    if db.execute(
        "SELECT COUNT(*) FROM users WHERE role='admin' AND is_active=1 "
        "AND length(password_hash)>32 AND instr(password_hash,':')>0"
    ).fetchone()[0] == 0:
        raise ValueError("no active hashed admin account")
    return {
        table: db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        for table in tables
    }

try:
    if not source_path.is_file() or source_path.stat().st_size > 128 * 1024 * 1024:
        raise ValueError("invalid or oversized auth backup")
    if any(source_path.with_name(source_path.name + suffix).exists()
           for suffix in ("-wal", "-shm")):
        raise ValueError("unexpected SQLite WAL sidecars")
    # Immutable, read-only snapshot; never create WAL sidecars or edit source.
    uri = "file:" + quote(str(source_path.resolve()), safe="/") + "?mode=ro&immutable=1"
    with sqlite3.connect(uri, uri=True) as source:
        source_counts = inspect(source)
        # Exercise the SQLite restore/backup API into a wholly new test DB.
        with sqlite3.connect(restored_path) as restored:
            source.backup(restored)
    with sqlite3.connect(
        "file:" + quote(str(restored_path.resolve()), safe="/") + "?mode=ro&immutable=1",
        uri=True,
    ) as restored:
        restored_counts = inspect(restored)
    if source_counts != restored_counts:
        raise ValueError("restored row-count parity mismatch")
except (sqlite3.Error, ValueError, OSError):
    # No usernames, passwords, token hashes, paths, or ciphertext in output.
    print("FAIL: SQLite data/schema/account restore verification", file=sys.stderr)
    raise SystemExit(1)

print("PASS: Offline age decryption, SQLite integrity, auth schema and account presence")
print("PASS: Disposable SQLite restore and all-table row-count parity")
print("NOTE: No live users, credentials, sessions or production services were changed")
print("NOTE: This verifies recovery of this artifact, not snapshot freshness or live login")
PY
