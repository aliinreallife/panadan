"""Local session authentication, per-user capabilities, and revocable service tokens.

SQLite is for Panadan identities only. Never use it to store customer reporting rows.
"""
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from pathlib import Path

SESSION_SECONDS = 8 * 3600
LOGIN_FAILURES: dict[str, list[float]] = {}
CAPABILITIES = ('calls:read', 'calls:sensitive', 'metrics:read', 'tokens:manage', 'mcp:use', 'users:manage')
ROLE_GRANTS = {
    'admin': CAPABILITIES,
    'analyst': ('calls:read', 'metrics:read', 'mcp:use'),
    'reader': ('calls:read',),
    'metrics': ('metrics:read',),
}


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return salt.hex() + ':' + key.hex()


def password_check(password: str, stored: str) -> bool:
    try:
        salt, _ = stored.split(':', 1)
        return hmac.compare_digest(password_hash(password, bytes.fromhex(salt)), stored)
    except (ValueError, TypeError):
        return False


def permissions(role: str, overrides: str | None = None) -> set[str]:
    if role == 'admin':
        return set(CAPABILITIES)
    try:
        if overrides is not None:
            parsed = json.loads(overrides)
            return set(parsed) & set(CAPABILITIES) - {'users:manage'}
    except (ValueError, TypeError):
        pass
    return set(ROLE_GRANTS.get(role, ()))


def has_capability(session: dict | None, capability: str) -> bool:
    return bool(session and capability in permissions(session.get('role', ''), session.get('grants')))


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
            for table, col, definition in [
                ('users', 'role', "TEXT NOT NULL DEFAULT 'admin'"),
                ('users', 'grants', 'TEXT'),
                ('users', 'is_active', 'INTEGER NOT NULL DEFAULT 1'),
                ('access_tokens', 'owner_id', 'INTEGER'),
            ]:
                existing = {r['name'] for r in c.execute(f'PRAGMA table_info({table})')}
                if col not in existing:
                    c.execute(f'ALTER TABLE {table} ADD COLUMN {col} {definition}')
            # OAuth subject bindings are separate from browser sessions and
            # legacy API tokens. No personal information from the provider
            # is automatically used to grant reporting permissions.
            c.execute("""CREATE TABLE IF NOT EXISTS oauth_identities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                issuer TEXT NOT NULL,
                subject TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                UNIQUE(issuer, subject),
                UNIQUE(issuer, user_id)
            )""")
            # Previously created tokens were admin-owned; require the existing admin
            # account to remain active for those tokens to work.
            admin = c.execute('SELECT id FROM users WHERE role=? ORDER BY id LIMIT 1', ('admin',)).fetchone()
            if admin:
                c.execute('UPDATE access_tokens SET owner_id=? WHERE owner_id IS NULL', (admin['id'],))

    def bootstrap(self, user: str, password: str | None):
        with self.db() as c:
            if c.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0:
                if not password or len(password) < 14 or 'REPLACE' in password.upper():
                    raise RuntimeError('Set PANADAN_ADMIN_PASSWORD to at least 14 characters for first start.')
                c.execute('INSERT INTO users(username,password_hash,role) VALUES(?,?,?)',
                          (user, password_hash(password), 'admin'))
            # Handles the initial bootstrap after a legacy SQLite migration.
            admin = c.execute('SELECT id FROM users WHERE role=? ORDER BY id LIMIT 1', ('admin',)).fetchone()
            if admin:
                c.execute('UPDATE access_tokens SET owner_id=? WHERE owner_id IS NULL', (admin['id'],))

    def verify_login(self, name: str, password: str) -> int | None:
        with self.db() as c:
            row = c.execute('SELECT id,password_hash,is_active FROM users WHERE username=?', (name,)).fetchone()
        ok = password_check(password, row['password_hash'] if row else _DUMMY_HASH)
        return int(row['id']) if row and row['is_active'] and ok else None

    def create_session(self, uid: int) -> tuple[str, str]:
        raw, csrf = secrets.token_urlsafe(40), secrets.token_urlsafe(32)
        with self.db() as c:
            c.execute('INSERT INTO sessions VALUES(?,?,?,?)',
                      (digest(raw), uid, csrf, int(time.time()) + SESSION_SECONDS))
        return raw, csrf

    def session(self, raw: str | None):
        if not raw: return None
        with self.db() as c:
            row = c.execute('''SELECT s.user_id,s.csrf,u.username,u.role,u.grants
                               FROM sessions s JOIN users u ON u.id=s.user_id
                               WHERE s.token_hash=? AND s.expires_at>? AND u.is_active=1''',
                            (digest(raw), int(time.time()))).fetchone()
        return dict(row) if row else None

    def logout(self, raw: str | None):
        if raw:
            with self.db() as c:
                c.execute('DELETE FROM sessions WHERE token_hash=?', (digest(raw),))

    def list_users(self):
        with self.db() as c:
            return [dict(r) for r in c.execute('SELECT id,username,role,grants,is_active FROM users ORDER BY id')]

    def create_user(self, username: str, password: str, role: str, caps: list[str] | None = None):
        if not username or len(username) > 80 or not username.replace('_','').replace('-','').isalnum():
            raise ValueError('Invalid username')
        if len(password) < 14: raise ValueError('Password must be at least 14 characters')
        if role not in ROLE_GRANTS: raise ValueError('Unknown role')
        if caps is not None and (set(caps) - set(CAPABILITIES) or ('users:manage' in caps and role != 'admin') or ('tokens:manage' in caps and role != 'admin')):
            raise ValueError('Invalid user privileges')
        grants = json.dumps(sorted(set(caps))) if caps is not None and role != 'admin' else None
        with self.db() as c:
            cur = c.execute('INSERT INTO users(username,password_hash,role,grants) VALUES(?,?,?,?)',
                            (username, password_hash(password), role, grants))
            return cur.lastrowid

    def update_user(self, user_id: int, role: str, caps: list[str] | None, active: bool, actor_id: int):
        if role not in ROLE_GRANTS: raise ValueError('Unknown role')
        if caps is not None and (set(caps) - set(CAPABILITIES) or ('users:manage' in caps and role != 'admin') or ('tokens:manage' in caps and role != 'admin')):
            raise ValueError('Invalid user privileges')
        if int(user_id) == actor_id and (not active or role != 'admin'):
            raise ValueError('Cannot deactivate or demote your own admin account')
        grants = json.dumps(sorted(set(caps))) if caps is not None and role != 'admin' else None
        with self.db() as c:
            user = c.execute('SELECT id,role,is_active FROM users WHERE id=?', (user_id,)).fetchone()
            if not user: raise ValueError('Unknown user')
            count = c.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND is_active=1").fetchone()[0]
            if user['role'] == 'admin' and user['is_active'] and count <= 1 and (role != 'admin' or not active):
                raise ValueError('Cannot remove the last active administrator')
            c.execute('UPDATE users SET role=?,grants=?,is_active=? WHERE id=?',
                      (role, grants, int(active), user_id))
            # A role change or disable must invalidate all outstanding sessions/tokens.
            c.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))
            c.execute('DELETE FROM access_tokens WHERE owner_id=?', (user_id,))
            # Reauthorization is required after a role or status update.
            c.execute('DELETE FROM oauth_identities WHERE user_id=?', (user_id,))

    def bind_oauth_identity(self, issuer: str, subject: str, user_id: int) -> int:
        """Administrator-approved binding of an IdP subject to a local account.

        Identity provider usernames/emails never determine Panadan permissions.
        A user must explicitly have permission for the non-sensitive MCP tools.
        """
        if not isinstance(subject, str) or not 1 <= len(subject) <= 256 or subject.strip() != subject:
            raise ValueError('Invalid identity-provider subject')
        if not issuer or len(issuer) > 512:
            raise ValueError('Invalid identity-provider issuer')
        with self.db() as c:
            row = c.execute('SELECT role,grants,is_active FROM users WHERE id=?', (user_id,)).fetchone()
            if not row or not row['is_active']:
                raise ValueError('User must be active')
            caps = permissions(row['role'], row['grants'])
            if not {'mcp:use', 'calls:read', 'metrics:read'} <= caps:
                raise ValueError('User needs MCP, calls and metrics permissions')
            cursor = c.execute(
                'INSERT INTO oauth_identities(issuer,subject,user_id,created_at) VALUES(?,?,?,?)',
                (issuer, subject, user_id, int(time.time())),
            )
            return cursor.lastrowid

    def list_oauth_identities(self, issuer: str) -> list[dict]:
        with self.db() as c:
            return [dict(row) for row in c.execute(
                """SELECT i.id, i.subject, i.created_at, u.username, u.is_active
                   FROM oauth_identities i JOIN users u ON u.id=i.user_id
                   WHERE i.issuer=? ORDER BY i.id DESC""", (issuer,)
            )]

    def revoke_oauth_identity(self, issuer: str, identity_id: int) -> None:
        with self.db() as c:
            c.execute('DELETE FROM oauth_identities WHERE issuer=? AND id=?',
                      (issuer, identity_id))

    def oauth_identity_has_mcp_access(self, issuer: str, subject: str) -> bool:
        with self.db() as c:
            row = c.execute(
                """SELECT u.role,u.grants,u.is_active
                   FROM oauth_identities i JOIN users u ON u.id=i.user_id
                   WHERE i.issuer=? AND i.subject=?""", (issuer, subject)
            ).fetchone()
        if not row or not row['is_active']:
            return False
        caps = permissions(row['role'], row['grants'])
        return {'mcp:use', 'calls:read', 'metrics:read'} <= caps

    def create_token(self, name: str, scope: str, days: int = 30, owner_id: int | None = None) -> tuple[int, str]:
        if scope not in ('api:read', 'api:sensitive', 'mcp:read') or not 1 <= days <= 365:
            raise ValueError('Invalid token scope or expiration')
        raw = 'panadan_' + secrets.token_urlsafe(36)
        now = int(time.time())
        with self.db() as c:
            if owner_id is None:
                admin = c.execute('SELECT id FROM users WHERE role=? AND is_active=1 ORDER BY id LIMIT 1', ('admin',)).fetchone()
                owner_id = admin['id'] if admin else None
            if owner_id is None: raise ValueError('No active token owner')
            owner = c.execute('SELECT role,grants,is_active FROM users WHERE id=?', (owner_id,)).fetchone()
            if not owner or not owner['is_active']: raise ValueError('Inactive owner')
            grants = permissions(owner['role'], owner['grants'])
            required = ({'calls:read', 'metrics:read'} if scope == 'api:read' else
                        {'calls:read', 'calls:sensitive'} if scope == 'api:sensitive' else
                        {'mcp:use', 'calls:read', 'metrics:read'})
            allowed = (bool(grants & required) if scope == 'api:read' else required <= grants)
            if not allowed:
                raise ValueError('Owner has insufficient permissions')
            cur = c.execute('''INSERT INTO access_tokens(name,token_hash,scope,created_at,expires_at,owner_id)
                               VALUES(?,?,?,?,?,?)''',
                            (name[:80], digest(raw), scope, now, now + days*86400, owner_id))
            return cur.lastrowid, raw

    def verify_token(self, raw: str, scope: str, capability: str | None = None) -> bool:
        if not raw or len(raw) > 256: return False
        with self.db() as c:
            row = c.execute('''SELECT t.id,t.scope,u.role,u.grants,u.is_active
                               FROM access_tokens t JOIN users u ON u.id=t.owner_id
                               WHERE t.token_hash=? AND t.expires_at>?''', (digest(raw), int(time.time()))).fetchone()
            grants = permissions(row['role'], row['grants']) if row and row['is_active'] else set()
            matching = bool(row and (row['scope'] == scope or
                            (scope == 'api:read' and row['scope'] == 'api:sensitive')))
            valid = bool(matching and (
                ({'calls:read','metrics:read'} & grants) if scope == 'api:read' else
                {'calls:read','calls:sensitive'} <= grants if scope == 'api:sensitive' else
                {'mcp:use','calls:read','metrics:read'} <= grants if scope == 'mcp:read' else False
            ) and (not capability or capability in grants))
            if valid: c.execute('UPDATE access_tokens SET last_used=? WHERE id=?', (int(time.time()), row['id']))
        return bool(valid)

    def list_tokens(self):
        with self.db() as c:
            return [dict(r) for r in c.execute('''SELECT t.id,t.name,t.scope,t.created_at,t.expires_at,t.last_used,
                                                  u.username owner
                                                  FROM access_tokens t LEFT JOIN users u ON u.id=t.owner_id
                                                  ORDER BY t.id DESC''')]

    def revoke(self, tid: int):
        with self.db() as c: c.execute('DELETE FROM access_tokens WHERE id=?', (tid,))


_DUMMY_HASH = password_hash('random-dummy-password-never-valid')


def is_rate_limited(ip: str) -> bool:
    now = time.monotonic()
    LOGIN_FAILURES[ip] = [t for t in LOGIN_FAILURES.get(ip, []) if now-t < 600]
    return len(LOGIN_FAILURES[ip]) >= 6


def record_failure(ip: str):
    LOGIN_FAILURES.setdefault(ip, []).append(time.monotonic())
