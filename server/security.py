"""Local dashboard sessions and hashed, scoped API/MCP tokens."""
import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from pathlib import Path

SESSION_SECONDS = 8 * 3600
LOGIN_FAILURES: dict[str, list[float]] = {}


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return salt.hex() + ':' + key.hex()


def password_check(password: str, stored: str) -> bool:
    try:
        s, k = stored.split(':', 1)
        return hmac.compare_digest(password_hash(password, bytes.fromhex(s)), stored)
    except (ValueError, TypeError):
        return False


class Store:
    def __init__(self, path: str):
        self.path = str(Path(path))
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def db(self):
        con = sqlite3.connect(self.path, timeout=5)
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA busy_timeout=5000')
        return con

    def _init(self):
        with self.db() as c:
            c.execute('PRAGMA journal_mode=WAL')
            c.executescript('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL,
                    csrf TEXT NOT NULL, expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS access_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL, token_hash TEXT UNIQUE NOT NULL,
                    scope TEXT NOT NULL CHECK (scope IN ('api:read', 'api:sensitive', 'mcp:read')),
                    created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
                    last_used INTEGER
                );
            ''')

    def bootstrap(self, user: str, password: str | None):
        with self.db() as c:
            count = c.execute('SELECT COUNT(*) FROM users').fetchone()[0]
            if not count:
                if not password or len(password) < 14 or 'REPLACE' in password.upper():
                    raise RuntimeError('Set PANADAN_ADMIN_PASSWORD to at least 14 characters for first start.')
                c.execute('INSERT INTO users(username,password_hash) VALUES(?,?)', (user, password_hash(password)))

    def verify_login(self, name: str, password: str) -> int | None:
        with self.db() as c:
            row = c.execute('SELECT id,password_hash FROM users WHERE username=?', (name,)).fetchone()
        # Always run KDF to reduce username enumeration timing.
        ok = password_check(password, row['password_hash'] if row else _DUMMY_HASH)
        return int(row['id']) if row and ok else None

    def create_session(self, uid: int) -> tuple[str, str]:
        raw, csrf = secrets.token_urlsafe(40), secrets.token_urlsafe(32)
        with self.db() as c:
            c.execute('INSERT INTO sessions VALUES(?,?,?,?)', (digest(raw), uid, csrf, int(time.time()) + SESSION_SECONDS))
        return raw, csrf

    def session(self, raw: str | None):
        if not raw: return None
        with self.db() as c:
            row = c.execute('SELECT user_id,csrf FROM sessions WHERE token_hash=? AND expires_at>?',
                            (digest(raw), int(time.time()))).fetchone()
        return dict(row) if row else None

    def logout(self, raw: str | None):
        if raw:
            with self.db() as c: c.execute('DELETE FROM sessions WHERE token_hash=?', (digest(raw),))

    def create_token(self, name: str, scope: str, days: int = 30) -> tuple[int, str]:
        if scope not in ('api:read','api:sensitive','mcp:read') or not 1 <= days <= 365:
            raise ValueError('Invalid token scope or expiration')
        raw = 'panadan_' + secrets.token_urlsafe(36)
        now = int(time.time())
        with self.db() as c:
            cur = c.execute('INSERT INTO access_tokens(name,token_hash,scope,created_at,expires_at) VALUES(?,?,?,?,?)',
                            (name[:80], digest(raw), scope, now, now + days * 86400))
            tid = cur.lastrowid
        return tid, raw

    def verify_token(self, raw: str, scope: str) -> bool:
        if not raw or len(raw) > 256: return False
        with self.db() as c:
            row = c.execute('SELECT id,scope FROM access_tokens WHERE token_hash=? AND expires_at>?',
                            (digest(raw), int(time.time()))).fetchone()
            valid = bool(row and (row['scope'] == scope or (scope == 'api:read' and row['scope'] == 'api:sensitive')))
            if valid: c.execute('UPDATE access_tokens SET last_used=? WHERE id=?', (int(time.time()), row['id']))
        return valid

    def list_tokens(self):
        with self.db() as c:
            return [dict(r) for r in c.execute('SELECT id,name,scope,created_at,expires_at,last_used FROM access_tokens ORDER BY id DESC')]

    def revoke(self, tid: int):
        with self.db() as c: c.execute('DELETE FROM access_tokens WHERE id=?', (tid,))


_DUMMY_HASH = password_hash('random-dummy-password-never-valid')


def is_rate_limited(ip: str) -> bool:
    now = time.monotonic()
    LOGIN_FAILURES[ip] = [t for t in LOGIN_FAILURES.get(ip, []) if now - t < 600]
    return len(LOGIN_FAILURES[ip]) >= 6


def record_failure(ip: str):
    LOGIN_FAILURES.setdefault(ip, []).append(time.monotonic())
