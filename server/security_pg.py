"""Staging-only PostgreSQL 18 core auth adapter; not selected by FastAPI.

The live authoritative Store remains SQLite until a separately approved cutover.
All SQL targets panadan_auth in the Panadan-owned PostgreSQL only.
"""
from __future__ import annotations
import json
import secrets
import time
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from .security import (
    CAPABILITIES, ROLE_GRANTS, SESSION_SECONDS, LOGIN_THROTTLE_WINDOW,
    LOGIN_THROTTLE_THRESHOLD, LOGIN_THROTTLE_MAX_DELAY, _DUMMY_HASH,
    digest, password_hash, password_check, permissions,
)


class PgStore:
    def __init__(self, dsn: str):
        if not dsn:
            raise ValueError("Panadan-owned PostgreSQL DSN required")
        self._dsn = dsn

    @contextmanager
    def db(self):
        with psycopg.connect(self._dsn, connect_timeout=5, row_factory=dict_row) as con:
            yield con

    def bootstrap(self, user: str, password: str | None):
        with self.db() as con:
            row=con.execute(
                """SELECT current_database() AS db,
                   current_setting('server_version_num')::integer AS version,
                   to_regclass('panadan_auth.users') AS users"""
            ).fetchone()
            if row["db"] not in ("panadan","panadan_ci") or row["version"]//10000!=18 or row["users"] is None:
                raise RuntimeError("Wrong PostgreSQL target/version or missing auth schema")
            con.execute("SELECT pg_advisory_xact_lock(706018001)")
            if con.execute("SELECT count(*) AS n FROM panadan_auth.users").fetchone()["n"]==0:
                if not password or len(password)<14 or "REPLACE" in password.upper():
                    raise RuntimeError("Secure first-run admin password required")
                con.execute(
                    """INSERT INTO panadan_auth.users
                       (username,password_hash,role,profile_id)
                       VALUES (%s,%s,'admin',%s)""",
                    (user,password_hash(password),"prf_"+secrets.token_urlsafe(24))
                )

    @staticmethod
    def _login_throttle_key(username: str) -> str:
        return digest(username if 0<len(username)<=80 else "<invalid-login-identifier>")

    def login_is_throttled(self, username: str, *, now: int | None = None) -> bool:
        now=int(time.time()) if now is None else now
        with self.db() as con:
            row=con.execute(
                """SELECT window_started,next_allowed FROM panadan_auth.login_throttle
                   WHERE username_hash=%s""",(self._login_throttle_key(username),)
            ).fetchone()
        return bool(row and row["window_started"]>now-LOGIN_THROTTLE_WINDOW and
                    row["next_allowed"]>now)

    def record_login_failure(self, username: str, *, now: int | None = None) -> None:
        now=int(time.time()) if now is None else now
        key=self._login_throttle_key(username)
        with self.db() as con:
            con.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",(key,))
            con.execute("DELETE FROM panadan_auth.login_throttle WHERE window_started<=%s",
                        (now-LOGIN_THROTTLE_WINDOW,))
            row=con.execute(
                """SELECT failure_count,window_started FROM panadan_auth.login_throttle
                   WHERE username_hash=%s FOR UPDATE""",(key,)
            ).fetchone()
            count=int(row["failure_count"])+1 if row else 1
            started=int(row["window_started"]) if row else now
            delay=(min(LOGIN_THROTTLE_MAX_DELAY,2 ** min(count-LOGIN_THROTTLE_THRESHOLD,6))
                   if count>=LOGIN_THROTTLE_THRESHOLD else 0)
            con.execute(
                """INSERT INTO panadan_auth.login_throttle
                   (username_hash,failure_count,window_started,next_allowed)
                   VALUES (%s,%s,%s,%s)
                   ON CONFLICT(username_hash) DO UPDATE SET
                   failure_count=excluded.failure_count,
                   window_started=excluded.window_started,
                   next_allowed=excluded.next_allowed""",
                (key,count,started,now+delay),
            )

    def clear_login_failures(self, username: str) -> None:
        with self.db() as con:
            con.execute("DELETE FROM panadan_auth.login_throttle WHERE username_hash=%s",
                        (self._login_throttle_key(username),))

    def verify_login(self, name: str, password: str) -> int | None:
        with self.db() as con:
            row=con.execute(
                "SELECT id,password_hash,is_active FROM panadan_auth.users WHERE username=%s",
                (name,),
            ).fetchone()
        ok=password_check(password,row["password_hash"] if row else _DUMMY_HASH)
        return int(row["id"]) if row and row["is_active"] and ok else None

    def create_session(self, uid: int) -> tuple[str,str]:
        raw,csrf=secrets.token_urlsafe(40),secrets.token_urlsafe(32)
        with self.db() as con:
            con.execute(
                """INSERT INTO panadan_auth.sessions(token_hash,user_id,csrf,expires_at)
                   VALUES (%s,%s,%s,%s)""",
                (digest(raw),uid,csrf,int(time.time())+SESSION_SECONDS),
            )
        return raw,csrf

    def session(self, raw: str | None):
        if not raw or len(raw)>256:
            return None
        with self.db() as con:
            return con.execute(
                """SELECT s.user_id,s.csrf,u.username,u.role,u.grants
                   FROM panadan_auth.sessions s JOIN panadan_auth.users u
                   ON u.id=s.user_id WHERE s.token_hash=%s AND s.expires_at>%s
                   AND u.is_active=1""",(digest(raw),int(time.time())),
            ).fetchone()

    def logout(self, raw: str | None):
        if raw and len(raw)<=256:
            with self.db() as con:
                con.execute("DELETE FROM panadan_auth.sessions WHERE token_hash=%s",
                            (digest(raw),))

    def list_users(self):
        with self.db() as con:
            return con.execute(
                "SELECT id,username,role,grants,is_active FROM panadan_auth.users ORDER BY id"
            ).fetchall()

    def create_user(self, username: str, password: str, role: str,
                    caps: list[str] | None = None):
        if not username or len(username)>80 or not username.replace("_","").replace("-","").isalnum():
            raise ValueError("Invalid username")
        if len(password)<14:
            raise ValueError("Password must be at least 14 characters")
        if role not in ROLE_GRANTS:
            raise ValueError("Unknown role")
        if caps is not None and (
            set(caps)-set(CAPABILITIES)
            or ("users:manage" in caps and role!="admin")
            or ("tokens:manage" in caps and role!="admin")
        ):
            raise ValueError("Invalid user privileges")
        grants=json.dumps(sorted(set(caps))) if caps is not None and role!="admin" else None
        with self.db() as con:
            return int(con.execute(
                """INSERT INTO panadan_auth.users
                   (username,password_hash,role,grants,profile_id)
                   VALUES (%s,%s,%s,%s,%s) RETURNING id""",
                (username,password_hash(password),role,grants,
                 "prf_"+secrets.token_urlsafe(24)),
            ).fetchone()["id"])

    def update_user(self, user_id: int, role: str, caps: list[str] | None,
                    active: bool, actor_id: int):
        if role not in ROLE_GRANTS:
            raise ValueError("Unknown role")
        if caps is not None and (
            set(caps)-set(CAPABILITIES)
            or ("users:manage" in caps and role!="admin")
            or ("tokens:manage" in caps and role!="admin")
        ):
            raise ValueError("Invalid user privileges")
        if int(user_id)==actor_id and (not active or role!="admin"):
            raise ValueError("Cannot deactivate or demote your own admin account")
        grants=json.dumps(sorted(set(caps))) if caps is not None and role!="admin" else None
        with self.db() as con:
            con.execute("SELECT pg_advisory_xact_lock(706018002)")
            user=con.execute(
                "SELECT id,role,is_active FROM panadan_auth.users WHERE id=%s FOR UPDATE",
                (user_id,),
            ).fetchone()
            if not user:
                raise ValueError("Unknown user")
            count=con.execute(
                "SELECT count(*) AS n FROM panadan_auth.users WHERE role='admin' AND is_active=1"
            ).fetchone()["n"]
            if user["role"]=="admin" and user["is_active"] and count<=1 and (role!="admin" or not active):
                raise ValueError("Cannot remove last active administrator")
            con.execute(
                "UPDATE panadan_auth.users SET role=%s,grants=%s,is_active=%s WHERE id=%s",
                (role,grants,int(active),user_id),
            )
            for table,column in (("sessions","user_id"),("access_tokens","owner_id"),
                                 ("oauth_identities","user_id")):
                con.execute(f"DELETE FROM panadan_auth.{table} WHERE {column}=%s",(user_id,))

    def _token_user(self, con, raw: str):
        if not raw or len(raw)>256:
            return None
        return con.execute(
            """SELECT u.id,u.username,u.profile_id,u.role,u.grants,u.is_active,
                      t.scope,t.id AS token_id
               FROM panadan_auth.access_tokens t JOIN panadan_auth.users u
               ON u.id=t.owner_id WHERE t.token_hash=%s AND t.expires_at>%s""",
            (digest(raw),int(time.time())),
        ).fetchone()

    def create_token(self, name: str, scope: str, days: int = 30,
                     owner_id: int | None = None) -> tuple[int,str]:
        if scope not in ("api:read","api:sensitive","mcp:read") or not 1<=days<=365:
            raise ValueError("Invalid token scope or expiration")
        raw="panadan_"+secrets.token_urlsafe(36)
        now=int(time.time())
        with self.db() as con:
            if owner_id is None:
                admin=con.execute(
                    "SELECT id FROM panadan_auth.users WHERE role='admin' AND is_active=1 ORDER BY id LIMIT 1"
                ).fetchone()
                owner_id=int(admin["id"]) if admin else None
            if owner_id is None:
                raise ValueError("No active token owner")
            owner=con.execute(
                "SELECT role,grants,is_active FROM panadan_auth.users WHERE id=%s FOR UPDATE",
                (owner_id,),
            ).fetchone()
            if not owner or not owner["is_active"]:
                raise ValueError("Inactive owner")
            grants=permissions(owner["role"],owner["grants"])
            required=(
                {"calls:read","metrics:read"} if scope=="api:read" else
                {"calls:read","calls:sensitive"} if scope=="api:sensitive" else
                {"mcp:use","calls:read","metrics:read"}
            )
            if not (bool(grants & required) if scope=="api:read" else required<=grants):
                raise ValueError("Owner has insufficient permissions")
            tid=con.execute(
                """INSERT INTO panadan_auth.access_tokens
                   (name,token_hash,scope,created_at,expires_at,owner_id)
                   VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
                (name[:80],digest(raw),scope,now,now+days*86400,owner_id),
            ).fetchone()["id"]
        return int(tid),raw

    def verify_token(self, raw: str, scope: str, capability: str | None = None) -> bool:
        if scope not in ("api:read","api:sensitive","mcp:read"):
            return False
        with self.db() as con:
            row=self._token_user(con,raw)
            if not row or not row["is_active"]:
                return False
            grants=permissions(row["role"],row["grants"])
            matching=(row["scope"]==scope or
                      (scope=="api:read" and row["scope"]=="api:sensitive"))
            valid=bool(matching and (
                ({"calls:read","metrics:read"} & grants) if scope=="api:read" else
                {"calls:read","calls:sensitive"} <= grants if scope=="api:sensitive" else
                {"mcp:use","calls:read","metrics:read"} <= grants
            ) and (not capability or capability in grants))
            if valid:
                con.execute(
                    "UPDATE panadan_auth.access_tokens SET last_used=%s WHERE id=%s",
                    (int(time.time()),row["token_id"]),
                )
            return valid

    def actor_for_token(self, raw: str, scope: str) -> int | None:
        if scope not in ("api:read","api:sensitive","mcp:read"):
            return None
        with self.db() as con:
            row=self._token_user(con,raw)
        if not row or not row["is_active"]:
            return None
        if row["scope"]!=scope and not (scope=="api:read" and row["scope"]=="api:sensitive"):
            return None
        return int(row["id"])

    def list_tokens(self):
        with self.db() as con:
            return con.execute(
                """SELECT t.id,t.name,t.scope,t.created_at,t.expires_at,t.last_used,
                          u.username AS owner FROM panadan_auth.access_tokens t
                   JOIN panadan_auth.users u ON u.id=t.owner_id ORDER BY t.id DESC"""
            ).fetchall()

    def revoke(self, tid: int):
        with self.db() as con:
            con.execute("DELETE FROM panadan_auth.access_tokens WHERE id=%s",(tid,))

    def bind_oauth_identity(self, issuer: str, subject: str, user_id: int) -> int:
        if not isinstance(subject,str) or not 1<=len(subject)<=256 or subject.strip()!=subject:
            raise ValueError("Invalid identity-provider subject")
        if not issuer or len(issuer)>512:
            raise ValueError("Invalid identity-provider issuer")
        with self.db() as con:
            user=con.execute(
                "SELECT role,grants,is_active FROM panadan_auth.users WHERE id=%s FOR UPDATE",
                (user_id,),
            ).fetchone()
            if (not user or not user["is_active"] or
                    not {"mcp:use","calls:read","metrics:read"} <=
                    permissions(user["role"],user["grants"])):
                raise ValueError("Active user with MCP privileges required")
            return int(con.execute(
                """INSERT INTO panadan_auth.oauth_identities
                   (issuer,subject,user_id,created_at)
                   VALUES (%s,%s,%s,%s) RETURNING id""",
                (issuer,subject,user_id,int(time.time())),
            ).fetchone()["id"])

    def list_oauth_identities(self, issuer: str) -> list[dict]:
        with self.db() as con:
            return con.execute(
                """SELECT i.id,i.subject,i.created_at,u.username,u.is_active
                   FROM panadan_auth.oauth_identities i
                   JOIN panadan_auth.users u ON u.id=i.user_id
                   WHERE i.issuer=%s ORDER BY i.id DESC""",(issuer,)
            ).fetchall()

    def revoke_oauth_identity(self, issuer: str, identity_id: int) -> None:
        with self.db() as con:
            con.execute(
                "DELETE FROM panadan_auth.oauth_identities WHERE issuer=%s AND id=%s",
                (issuer,identity_id),
            )

    def _oauth_user(self, con, issuer: str | None, subject: str):
        return con.execute(
            """SELECT u.id,u.profile_id,u.username,u.role,u.grants,u.is_active
               FROM panadan_auth.oauth_identities i JOIN panadan_auth.users u
               ON u.id=i.user_id WHERE i.issuer=%s AND i.subject=%s""",
            (issuer,subject),
        ).fetchone()

    def oauth_identity_has_mcp_access(self, issuer: str, subject: str) -> bool:
        with self.db() as con:
            row=self._oauth_user(con,issuer,subject)
        return bool(row and row["is_active"] and
                    {"mcp:use","calls:read","metrics:read"} <=
                    permissions(row["role"],row["grants"]))

    def actor_for_oauth(self, issuer: str, subject: str) -> int | None:
        if not issuer or not subject:
            return None
        with self.db() as con:
            row=self._oauth_user(con,issuer,subject)
        return int(row["id"]) if row and row["is_active"] else None

    def authorized_transcript_actor(self, *, oauth_issuer: str | None = None,
                                    oauth_subject: str | None = None,
                                    legacy_token: str | None = None) -> int | None:
        if bool(oauth_subject)==bool(legacy_token):
            return None
        with self.db() as con:
            if oauth_subject:
                row=self._oauth_user(con,oauth_issuer,oauth_subject)
            else:
                row=self._token_user(con,legacy_token)
                if row and row["scope"]!="mcp:read":
                    return None
        if not row or not row["is_active"]:
            return None
        if not {"mcp:use","calls:read","metrics:read","calls:transcript:read"} <= permissions(row["role"],row["grants"]):
            return None
        return int(row["id"])

    def mcp_profile(self, *, oauth_issuer: str | None = None,
                    oauth_subject: str | None = None,
                    legacy_token: str | None = None) -> dict | None:
        if bool(oauth_subject)==bool(legacy_token):
            return None
        with self.db() as con:
            if oauth_subject:
                row=self._oauth_user(con,oauth_issuer,oauth_subject)
            else:
                row=self._token_user(con,legacy_token)
                if row and row["scope"]!="mcp:read":
                    return None
        if not row or not row["is_active"] or not row["profile_id"]:
            return None
        if not {"mcp:use","calls:read","metrics:read"} <= permissions(row["role"],row["grants"]):
            return None
        return {"id":row["profile_id"],"name":row["username"]}

    def audit_transcript_request(self, *, user_id: int, surface: str,
                                 call_id: int, char_limit: int) -> bool:
        if surface not in ("mcp","webmcp") or call_id<1 or not 1<=char_limit<=6000:
            return False
        with self.db() as con:
            # FOR UPDATE serializes role revocation and transcript reads.
            row=con.execute(
                "SELECT role,grants,is_active FROM panadan_auth.users WHERE id=%s FOR UPDATE",
                (user_id,),
            ).fetchone()
            caps=permissions(row["role"],row["grants"]) if row and row["is_active"] else set()
            if not {"calls:read","calls:transcript:read"} <= caps:
                return False
            con.execute(
                """INSERT INTO panadan_auth.transcript_access_audit
                   (user_id,surface,call_id,char_limit,created_at)
                   VALUES (%s,%s,%s,%s,%s)""",
                (user_id,surface,call_id,char_limit,int(time.time())),
            )
            return True

    def list_transcript_audit(self, limit: int = 100) -> list[dict]:
        with self.db() as con:
            return con.execute(
                """SELECT a.id,u.username,a.surface,a.call_id,a.char_limit,a.created_at
                   FROM panadan_auth.transcript_access_audit a
                   JOIN panadan_auth.users u ON u.id=a.user_id
                   ORDER BY a.id DESC LIMIT %s""",(max(1,min(int(limit),500)),)
            ).fetchall()
