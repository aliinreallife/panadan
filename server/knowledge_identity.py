"""Opt-in identity adapter for the existing SQLite authority (M01.2).

No startup hook, web route, alternate login, automatic principal enrollment,
or production installer. Run the explicit profile bootstrap only in an
approved isolated auth store. A future cutover must verify namespace continuity,
backup/restore and session revocation before enabling any knowledge routes.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import re
import sqlite3
import time
from uuid import UUID

from .security import Store, digest

PROFILE = re.compile(r"prf_[0-9a-f]{48}\Z")


def _namespace(value: UUID) -> str:
    if not isinstance(value, UUID) or value.int == 0:
        raise ValueError("Explicit nonzero installation UUID required")
    return "sqlite:" + str(value)


@dataclass(frozen=True, slots=True)
class VerifiedIdentity:
    namespace: str
    subject: str


def install_profile_identity(store: Store, installation: UUID, *, confirmed: bool = False) -> None:
    """Explicit administrative migration; never invoked by Store or HTTP startup.

    Existing users receive random stable profiles, not knowledge memberships.
    First installation invalidates pre-profile browser sessions; fresh login
    is required because historical integer-keyed sessions cannot prove profile
    continuity. Reapplying the same installation does not revoke sessions.
    The existing PG auth importer preserves profile_id. This is not a cutover
    mechanism: a future authority change or restore needs separate review.
    The existing account lifecycle is deactivate-only; once installed, direct
    SQL deletion and ID rewrites are deliberately refused to prevent old
    integer-keyed sessions/tokens from being rebound to a recreated account.
    """
    if confirmed is not True or type(store) is not Store:
        raise ValueError("Explicit SQLite identity migration required")
    namespace = _namespace(installation)
    with closing(store.db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        # Do not adopt partial or foreign profile schemas automatically.
        marker = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='knowledge_identity_installation'"
        ).fetchone()
        if marker:
            row = db.execute("SELECT namespace FROM knowledge_identity_installation WHERE singleton=1").fetchone()
            triggers = {r[0] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='users'"
            )}
            required = {"knowledge_profile_insert_guard", "knowledge_profile_allocate",
                        "knowledge_profile_immutable", "knowledge_account_no_delete",
                        "knowledge_username_replace_guard"}
            if (not row or row[0] != namespace or not required <= triggers
                    or any(not isinstance(r[0], str) or not PROFILE.fullmatch(r[0])
                           for r in db.execute("SELECT profile_id FROM users"))):
                raise ValueError("Identity installation mismatch; review manually")
            return
        if "profile_id" in {r[1] for r in db.execute("PRAGMA table_info(users)")}:
            raise ValueError("Unreviewed existing profile identity")
        db.execute("ALTER TABLE users ADD COLUMN profile_id TEXT")
        db.execute("UPDATE users SET profile_id='prf_' || lower(hex(randomblob(24)))")
        db.execute("CREATE UNIQUE INDEX knowledge_profile_id_unique ON users(profile_id)")
        db.execute("""CREATE TABLE knowledge_identity_installation (
            singleton INTEGER PRIMARY KEY CHECK(singleton=1), namespace TEXT NOT NULL UNIQUE
        )""")
        db.execute("INSERT INTO knowledge_identity_installation VALUES(1,?)", (namespace,))
        db.execute("""CREATE TRIGGER knowledge_namespace_no_update
            BEFORE UPDATE ON knowledge_identity_installation
            BEGIN SELECT RAISE(ABORT,'Knowledge identity namespace is immutable'); END""")
        db.execute("""CREATE TRIGGER knowledge_namespace_no_replace
            BEFORE INSERT ON knowledge_identity_installation
            WHEN EXISTS(SELECT 1 FROM knowledge_identity_installation)
            BEGIN SELECT RAISE(ABORT,'Knowledge identity namespace is immutable'); END""")
        db.execute("""CREATE TRIGGER knowledge_namespace_no_delete
            BEFORE DELETE ON knowledge_identity_installation
            BEGIN SELECT RAISE(ABORT,'Knowledge identity namespace is immutable'); END""")
        db.execute("""CREATE TRIGGER knowledge_profile_insert_guard BEFORE INSERT ON users
            WHEN NEW.profile_id IS NOT NULL OR EXISTS(SELECT 1 FROM users WHERE id=NEW.id OR username=NEW.username)
            BEGIN SELECT RAISE(ABORT,'Explicit or replacement identity forbidden'); END""")
        db.execute("""CREATE TRIGGER knowledge_profile_allocate AFTER INSERT ON users
            WHEN NEW.profile_id IS NULL
            BEGIN UPDATE users SET profile_id='prf_' || lower(hex(randomblob(24))) WHERE id=NEW.id; END""")
        db.execute("""CREATE TRIGGER knowledge_profile_immutable BEFORE UPDATE ON users
            WHEN NEW.id IS NOT OLD.id OR
                 (OLD.profile_id IS NOT NULL AND NEW.profile_id IS NOT OLD.profile_id)
            BEGIN SELECT RAISE(ABORT,'Knowledge account identity is immutable'); END""")
        db.execute("""CREATE TRIGGER knowledge_username_replace_guard BEFORE UPDATE OF username ON users
            WHEN EXISTS(SELECT 1 FROM users WHERE username=NEW.username AND id<>OLD.id)
            BEGIN SELECT RAISE(ABORT,'Replacement identity forbidden'); END""")
        db.execute("""CREATE TRIGGER knowledge_account_no_delete BEFORE DELETE ON users
            BEGIN SELECT RAISE(ABORT,'Deactivate the account instead of deleting it'); END""")
        # Only on first explicit installation, in the same transaction.
        # Do not bridge pre-installation integer-keyed browser sessions.
        db.execute("DELETE FROM sessions")


class SQLiteIdentityBridge:
    """Resolve current browser sessions in a single authority query.

    Only this channel is implemented. API/MCP/worker identity and PG staging
    continuity are deliberately not inferred. No profile supplied by a client
    is accepted, and no numeric account ID is used as the principal key.
    """
    def __init__(self, store: Store, installation: UUID):
        if type(store) is not Store:
            raise ValueError("Only the existing SQLite authority is supported")
        self._store = store
        self._namespace = _namespace(installation)

    def _display_names(self, subjects):
        """Resolve only a bounded, authorized same-installation member list.
        
        Presentation only: labels never grant access. Missing labels stay
        unknown rather than resolving users by name or another authority.
        """
        subjects = tuple(dict.fromkeys(s for s in subjects
                         if isinstance(s, str) and PROFILE.fullmatch(s)))
        if not subjects or len(subjects)>100:
            return {}
        placeholders = ",".join("?" for _ in subjects)
        try:
            with closing(self._store.db()) as db:
                rows=db.execute(
                    "SELECT u.profile_id,u.username FROM users u "
                    "JOIN knowledge_identity_installation i ON i.singleton=1 "
                    "WHERE i.namespace=? AND u.profile_id IN ("+placeholders+")",
                    (self._namespace,*subjects)).fetchall()
                return {row[0]:row[1] for row in rows}
        except sqlite3.Error:
            return {}

    def resolve_session(self, raw: str | None) -> VerifiedIdentity | None:
        if not isinstance(raw, str) or not 1 <= len(raw) <= 256:
            return None
        try:
            with closing(self._store.db()) as db:
                # Join session, active user and installation in the same read.
                row = db.execute("""SELECT u.profile_id, i.namespace
                    FROM sessions s JOIN users u ON u.id=s.user_id
                    CROSS JOIN knowledge_identity_installation i
                    WHERE s.token_hash=? AND s.expires_at>? AND u.is_active=1
                    AND i.singleton=1 AND i.namespace=?""",
                    (digest(raw), int(time.time()), self._namespace)).fetchone()
            if row and isinstance(row[0], str) and PROFILE.fullmatch(row[0]):
                return VerifiedIdentity(row[1], row[0])
        except sqlite3.Error:
            # Missing schema/unavailable authority never falls back to a name,
            # legacy role, cached identity or another database.
            return None
        return None
