"""Guarded SQLite snapshot -> Panadan-owned PostgreSQL 18 auth importer.

Phase-1 staging only. Does NOT connect to Odoo, change the FastAPI Store,
create PostgreSQL roles, install schedulers or permit production imports.
Never point at the active SQLite file: use a consistent offline backup copy.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from .auth_store import validate_staging_dsn

TABLE_COLUMNS = {
    "users": ("id","username","password_hash","role","grants","field_grants","is_active","profile_id"),
    "sessions": ("token_hash","user_id","csrf","expires_at"),
    "access_tokens": ("id","name","token_hash","scope","created_at","expires_at","last_used","owner_id","field_grants","cap_grants"),
    "mcp_client_grants": ("user_id","client_id","capabilities","fields","approved_at"),
    "oauth_identities": ("id","issuer","subject","user_id","created_at"),
    "transcript_access_audit": ("id","user_id","surface","call_id","char_limit","created_at"),
    "activity_events": ("id","user_id","surface","action","http_status","duration_ms","created_at"),
    "login_throttle": ("username_hash","failure_count","window_started","next_allowed"),
    "operator_directory": ("operator_name","destination","team","updated_at"),
}
IDENTITY_TABLES = ("users","access_tokens","oauth_identities","transcript_access_audit","activity_events")
MAX_SOURCE_BYTES = 128 * 1024 * 1024
MAX_ROWS_PER_TABLE = 200_000


def inspect_snapshot(path: Path) -> tuple[sqlite3.Connection, dict[str, int]]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("Require a regular, bounded SQLite backup snapshot")
    if path.with_name(path.name + "-wal").exists() or path.with_name(path.name+"-shm").exists():
        raise ValueError("Refusing a WAL-associated SQLite source; use the Online Backup API first")
    # Only read the operator-provided snapshot. Never mutate it.
    # This is a verified, closed snapshot (not a changing database). The
    # immutable reader does not create "-wal"/"-shm" sidecars on inspection,
    # and avoids a second read falsely rejecting the same backup.
    conn=sqlite3.connect(f"file:{path.resolve()}?mode=ro&immutable=1",uri=True)
    conn.row_factory=sqlite3.Row
    if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        conn.close()
        raise ValueError("SQLite snapshot integrity check failed")
    existing={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    missing=set(TABLE_COLUMNS)-existing
    if missing:
        conn.close()
        raise ValueError("Snapshot missing required auth tables: "+",".join(sorted(missing)))
    counts={}
    for table,expected in TABLE_COLUMNS.items():
        present={r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        # Allow NULL defaults when reading older SQLite account/token rows,
        # but require the consent table to exist before importing.
        optional = (
            {"profile_id", "field_grants"} if table=="users" else
            {"field_grants", "cap_grants"} if table=="access_tokens" else set()
        )
        required=set(expected) - optional
        if not required <= present:
            conn.close()
            raise ValueError(f"Snapshot table {table} lacks expected columns")
        n=int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        if n > MAX_ROWS_PER_TABLE:
            conn.close()
            raise ValueError(f"Excessively large auth snapshot table {table}; plan a batch migration")
        counts[table]=n
    if counts["users"]==0:
        conn.close()
        raise ValueError("No source accounts in auth snapshot")
    user_ids={int(r[0]) for r in conn.execute("SELECT id FROM users")}
    for table,column in (("sessions","user_id"),("access_tokens","owner_id"),
                         ("oauth_identities","user_id"),("transcript_access_audit","user_id"),
                         ("activity_events","user_id")):
        # Sessions/tokens with orphaned owner IDs must not become valid accidentally.
        for row in conn.execute(f"SELECT {column} FROM {table}"):
            if row[0] is not None and int(row[0]) not in user_ids:
                conn.close()
                raise ValueError(f"Orphaned user reference in {table}")
            if table=="access_tokens" and row[0] is None:
                conn.close()
                raise ValueError("Unowned access token; repair or revoke before migration")
    return conn,counts


def validate_disposable_target(dsn: str) -> None:
    if os.environ.get("PANADAN_AUTH_MIGRATION_TEST_ALLOW_APPLY") != "YES":
        raise ValueError("Only explicit disposable PostgreSQL imports are enabled")
    # Reuse the STRICT staging backend allowlist. Do not permit libpq
    # hostaddr/service/options redirection or production-owned databases.
    validate_staging_dsn(dsn)


def _row_fingerprint(values: tuple) -> bytes:
    """Internal-only exact-value comparison; never print auth row contents."""
    serialized=json.dumps(values,ensure_ascii=False,separators=(",",":"))
    return hashlib.sha256(serialized.encode("utf-8")).digest()


def _verify_table_parity(target, table: str,
                         columns: tuple[str, ...], records: list[tuple]) -> None:
    """Check every imported value and duplicate multiplicity before COMMIT.

    Ordered equality is unsuitable for SQL tables; compare multisets of
    full-row hashes instead. The source and target records stay in memory,
    and mismatch diagnostics contain only a hard-coded auth TABLE name.
    No passwords, token digests, usernames or hashes are logged.
    """
    if table not in TABLE_COLUMNS or columns != TABLE_COLUMNS[table]:
        raise ValueError("Unexpected auth table/column shape for parity audit")
    expected=Counter(_row_fingerprint(tuple(row)) for row in records)
    observed=Counter()
    # Named server-side cursor bounds the target-memory footprint.
    with target.cursor(name=f"auth_parity_{table}") as cursor:
        cursor.execute(
            f"SELECT {','.join(columns)} FROM panadan_auth.{table}"
        )
        while batch := cursor.fetchmany(1000):
            for row in batch:
                observed[_row_fingerprint(tuple(row[col] for col in columns))] += 1
    if observed != expected:
        raise ValueError(f"PostgreSQL migrated field parity mismatch in {table}")


def _read_rows(source: sqlite3.Connection,table: str) -> tuple[tuple[str,...],list[tuple]]:
    columns=TABLE_COLUMNS[table]
    present={r[1] for r in source.execute(f"PRAGMA table_info({table})")}
    selected=tuple(c for c in columns if c in present)
    query=f"SELECT {','.join(selected)} FROM {table}"
    records=[]
    for row in source.execute(query):
        data=dict(zip(selected,row))
        if table=="users":
            # If the SQLite store already has profile IDs, retain them.
            # Otherwise allocate cryptographically random opaque identifiers.
            data["profile_id"]=data.get("profile_id") or "prf_"+secrets.token_urlsafe(24)
            data.setdefault("field_grants", None)
        if table=="access_tokens":
            data.setdefault("field_grants", None)
            data.setdefault("cap_grants", None)
        records.append(tuple(data[col] for col in columns))
    return columns,records


def import_into_disposable(source: sqlite3.Connection, dsn: str, counts: dict[str,int]) -> dict[str,int]:
    validate_disposable_target(dsn)
    with psycopg.connect(dsn,connect_timeout=5,row_factory=dict_row) as target:
        with target.transaction():
            identity=target.execute(
                "SELECT current_database() AS db, current_setting('server_version_num')::int AS version"
            ).fetchone()
            if identity["db"]!="panadan_ci" or identity["version"] // 10000 != 18:
                raise ValueError("Target must be disposable Panadan PostgreSQL 18")
            target.execute("SET LOCAL lock_timeout='5s'")
            locked=target.execute("SELECT pg_try_advisory_xact_lock(70260318) AS acquired").fetchone()
            if not locked["acquired"]:
                raise ValueError("Another auth migration is already running")
            # Tables must have been created by the reviewed schema SQL first.
            for table in TABLE_COLUMNS:
                found=target.execute("SELECT to_regclass(%s) AS rel",
                                     (f"panadan_auth.{table}",)).fetchone()["rel"]
                if found is None:
                    raise ValueError("Missing PostgreSQL auth schema; apply migration 003 first")
                occupied=target.execute(f"SELECT EXISTS (SELECT 1 FROM panadan_auth.{table} LIMIT 1) AS yes").fetchone()["yes"]
                if occupied:
                    raise ValueError(f"Refusing to overwrite nonempty target {table}")
            for table in TABLE_COLUMNS:
                cols,records=_read_rows(source,table)
                placeholders=",".join("%s" for _ in cols)
                sql=f"INSERT INTO panadan_auth.{table} ({','.join(cols)}) VALUES ({placeholders})"
                if records:
                    with target.cursor() as cur:
                        cur.executemany(sql,records)
                n=target.execute(f"SELECT COUNT(*) AS n FROM panadan_auth.{table}").fetchone()["n"]
                if n!=counts[table]:
                    raise ValueError(f"PostgreSQL migrated count mismatch in {table}")
                # Verify exact field values *inside* this transaction.
                # A count match alone can conceal token/grant/owner drift.
                _verify_table_parity(target,table,cols,records)
            for table in IDENTITY_TABLES:
                target.execute(
                    f"SELECT setval(pg_get_serial_sequence('panadan_auth.{table}','id'),"
                    f"COALESCE(MAX(id),1),MAX(id) IS NOT NULL) FROM panadan_auth.{table}"
                )
    return counts


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite-snapshot",type=Path,required=True,
                        help="Consistent SQLite backup snapshot, not live /data/auth.sqlite")
    parser.add_argument("--apply-to-disposable",action="store_true",
                        help="Only panadan_ci on loopback with explicit allow flag")
    args=parser.parse_args()
    connection,counts=inspect_snapshot(args.sqlite_snapshot)
    try:
        if args.apply_to_disposable:
            import_into_disposable(
                connection,os.getenv("PANADAN_AUTH_MIGRATION_DSN",""),counts
            )
            print("PASS: Synthetic/disposable PostgreSQL auth migration committed")
        else:
            print("PASS: SQLite snapshot integrity and migration preflight")
        # Metadata only. Do NOT log usernames, hashes, token values, transcript text.
        print("Table row counts:",", ".join(f"{name}={n}" for name,n in counts.items()))
        print("NOTE: Production auth database is unchanged; FastAPI still uses SQLite")
    finally:
        connection.close()
    return 0


if __name__=="__main__":
    raise SystemExit(main())
