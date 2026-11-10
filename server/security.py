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

from .field_permissions import capability_fields, effective_fields, validate_fields

SESSION_SECONDS = 8 * 3600
LOGIN_THROTTLE_WINDOW = 600  # rolling 10-minute observation window
LOGIN_THROTTLE_THRESHOLD = 6
LOGIN_THROTTLE_MAX_DELAY = 60  # bounded backoff to limit account-lockout DoS
LOGIN_FAILURES: dict[str, list[float]] = {}
CAPABILITIES = ('calls:read', 'calls:sensitive', 'calls:transcript:read', 'metrics:read', 'tokens:manage', 'mcp:use', 'users:manage')
ROLE_GRANTS = {
    'admin': CAPABILITIES,
    'analyst': ('calls:read', 'metrics:read', 'mcp:use'),
    'reader': ('calls:read',),
    'metrics': ('metrics:read',),
}

MCP_PREREQUISITES = frozenset(('calls:read', 'metrics:read'))


def validate_user_grants(role: str, caps: list[str] | None) -> None:
    """Reject contradictory MCP grants; never silently grant prerequisites."""
    if role not in ROLE_GRANTS:
        raise ValueError('Unknown role')
    if caps is None:
        return
    selected = set(caps)
    if (selected - set(CAPABILITIES)
            or (role != 'admin' and selected & {'users:manage', 'tokens:manage'})):
        raise ValueError('Invalid user privileges')
    if role != 'admin' and 'mcp:use' in selected and not (MCP_PREREQUISITES & selected):
        raise ValueError('MCP requires at least one reporting permission')
    if role != 'admin' and (selected & {'calls:sensitive', 'calls:transcript:read'}) and 'calls:read' not in selected:
        raise ValueError('Sensitive call details and transcript require calls:read')



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
            granted = set(parsed) & set(CAPABILITIES) - {'users:manage', 'tokens:manage'}
            # Existing inconsistent rows cannot advertise effective MCP
            # permission until explicitly fixed by an administrator.
            if 'mcp:use' in granted and not (MCP_PREREQUISITES & granted):
                granted.discard('mcp:use')
            if 'calls:read' not in granted:
                granted.discard('calls:sensitive')
                granted.discard('calls:transcript:read')
            return granted
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
                ('users', 'field_grants', 'TEXT'),
                ('access_tokens', 'field_grants', 'TEXT'),
                ('access_tokens', 'cap_grants', 'TEXT'),
                ('users', 'is_active', 'INTEGER NOT NULL DEFAULT 1'),
                ('access_tokens', 'owner_id', 'INTEGER'),
            ]:
                existing = {r['name'] for r in c.execute(f'PRAGMA table_info({table})')}
                if col not in existing:
                    c.execute(f'ALTER TABLE {table} ADD COLUMN {col} {definition}')
            c.execute('''CREATE TABLE IF NOT EXISTS mcp_client_grants (
                user_id INTEGER NOT NULL,
                client_id TEXT NOT NULL,
                capabilities TEXT NOT NULL,
                fields TEXT NOT NULL,
                approved_at INTEGER NOT NULL,
                PRIMARY KEY(user_id,client_id)
            )''')
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
            c.execute("""CREATE TABLE IF NOT EXISTS transcript_access_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                surface TEXT NOT NULL CHECK (surface IN ('mcp', 'webmcp')),
                call_id INTEGER NOT NULL,
                char_limit INTEGER NOT NULL,
                created_at INTEGER NOT NULL
            )""")
            c.execute('CREATE INDEX IF NOT EXISTS transcript_audit_user_time ON transcript_access_audit(user_id,created_at)')
            c.execute("""CREATE TABLE IF NOT EXISTS activity_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                surface TEXT NOT NULL CHECK(surface IN ('dashboard','api','mcp','auth')),
                action TEXT NOT NULL,
                http_status INTEGER NOT NULL,
                duration_ms INTEGER NOT NULL,
                created_at INTEGER NOT NULL
            )""")
            c.execute('CREATE INDEX IF NOT EXISTS activity_events_time ON activity_events(created_at)')
            c.execute('CREATE INDEX IF NOT EXISTS activity_events_user_time ON activity_events(user_id,created_at)')
            # Persistent per-username throttle: no passwords, cleartext usernames,
            # network addresses, or credentials are stored in this table.
            c.execute("""CREATE TABLE IF NOT EXISTS login_throttle (
                username_hash TEXT PRIMARY KEY,
                failure_count INTEGER NOT NULL,
                window_started INTEGER NOT NULL,
                next_allowed INTEGER NOT NULL
            )""")
            c.execute('CREATE INDEX IF NOT EXISTS login_throttle_expiry ON login_throttle(window_started)')
            # Operator directory contains only administrative metadata.
            # It is NOT a reporting-data copy and is NOT yet used to grant access.
            c.execute("""CREATE TABLE IF NOT EXISTS operator_directory (
                operator_name TEXT PRIMARY KEY,
                destination TEXT,
                team TEXT,
                updated_at INTEGER NOT NULL
            )""")
            # Verified numeric operator IDs are an explicit authorization
            # boundary, unlike the display-name operator_directory.
            # No implicit grants, not even for admin users. Binding changes
            # require an active admin + manual source-ID confirmation.
            c.execute("""CREATE TABLE IF NOT EXISTS user_operator_scopes (
                user_id INTEGER NOT NULL,
                operator_id INTEGER NOT NULL CHECK(
                    operator_id BETWEEN 1 AND 999999999),
                verified_by INTEGER NOT NULL,
                verified_at INTEGER NOT NULL,
                PRIMARY KEY(user_id,operator_id),
                FOREIGN KEY(user_id) REFERENCES users(id)
            )""")
            c.execute('CREATE INDEX IF NOT EXISTS user_operator_scopes_operator '
                      'ON user_operator_scopes(operator_id)')
            # Local permission changes are audit-recorded in the same SQLite
            # transaction. Do not put customer data or access tokens here.
            c.execute("""CREATE TABLE IF NOT EXISTS operator_scope_audit (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_user_id INTEGER,
                target_user_id INTEGER NOT NULL,
                operator_id INTEGER NOT NULL,
                action TEXT NOT NULL CHECK(action IN ('grant','revoke','reset')),
                event_at INTEGER NOT NULL
            )""")
            c.execute('CREATE INDEX IF NOT EXISTS operator_scope_audit_target '
                      'ON operator_scope_audit(target_user_id,event_at)')
            # Sensitive full-field reads require a durable pre-read audit.
            # No customer data, transcript or secret is stored in this log.
            c.execute("""CREATE TABLE IF NOT EXISTS sensitive_mirror_access_audit (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                call_id INTEGER NOT NULL CHECK(call_id BETWEEN 1 AND 999999999),
                surface TEXT NOT NULL CHECK(surface IN ('dashboard','api')),
                event_at INTEGER NOT NULL
            )""")
            c.execute('CREATE INDEX IF NOT EXISTS sensitive_mirror_access_user_time '
                      'ON sensitive_mirror_access_audit(user_id,event_at)')
            # Never silently trust orphaned/disabled accounts from migrated
            # stores; runtime reads additionally verify active capabilities.
            c.execute("""DELETE FROM user_operator_scopes
                WHERE NOT EXISTS (
                    SELECT 1 FROM users u
                    WHERE u.id=user_operator_scopes.user_id AND u.is_active=1
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

    @staticmethod
    def _login_throttle_key(username: str) -> str:
        # Valid local usernames have at most 80 characters. Long/invalid
        # identifiers share a bounded invalid lane rather than enabling
        # unbounded storage of attacker-controlled long strings.
        return digest(username if 0 < len(username) <= 80 else '<invalid-login-identifier>')

    def login_is_throttled(self, username: str, *, now: int | None = None) -> bool:
        """Persistent throttle, independent of proxy IP and worker restarts."""
        now = int(time.time()) if now is None else now
        with self.db() as c:
            row = c.execute(
                'SELECT window_started,next_allowed FROM login_throttle WHERE username_hash=?',
                (self._login_throttle_key(username),)
            ).fetchone()
        return bool(row and row['window_started'] > now - LOGIN_THROTTLE_WINDOW
                    and row['next_allowed'] > now)

    def record_login_failure(self, username: str, *, now: int | None = None) -> None:
        """Record one failure atomically, with capped exponential delay."""
        now = int(time.time()) if now is None else now
        key = self._login_throttle_key(username)
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('DELETE FROM login_throttle WHERE window_started <= ?',
                      (now - LOGIN_THROTTLE_WINDOW,))
            row = c.execute(
                'SELECT failure_count,window_started FROM login_throttle WHERE username_hash=?',
                (key,)
            ).fetchone()
            count = int(row['failure_count']) + 1 if row else 1
            started = int(row['window_started']) if row else now
            delay = (min(LOGIN_THROTTLE_MAX_DELAY,
                         2 ** min(count - LOGIN_THROTTLE_THRESHOLD, 6))
                     if count >= LOGIN_THROTTLE_THRESHOLD else 0)
            c.execute("""INSERT INTO login_throttle
                         (username_hash,failure_count,window_started,next_allowed)
                         VALUES(?,?,?,?)
                         ON CONFLICT(username_hash) DO UPDATE SET
                           failure_count=excluded.failure_count,
                           window_started=excluded.window_started,
                           next_allowed=excluded.next_allowed""",
                      (key, count, started, now + delay))

    def clear_login_failures(self, username: str) -> None:
        with self.db() as c:
            c.execute('DELETE FROM login_throttle WHERE username_hash=?',
                      (self._login_throttle_key(username),))

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
            row = c.execute('''SELECT s.user_id,s.csrf,u.username,u.role,u.grants,u.field_grants
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
            return [dict(r) for r in c.execute('SELECT id,username,role,grants,field_grants,is_active FROM users ORDER BY id')]

    def operator_assignments(self) -> dict[str, dict]:
        with self.db() as c:
            return {row['operator_name']: {
                'destination':row['destination'] or 'نامشخص',
                'team':row['team'] or 'نامشخص',
            } for row in c.execute(
                'SELECT operator_name,destination,team FROM operator_directory'
            )}

    def set_operator_assignment(self, operator_name: str, destination: str,
                                team: str) -> None:
        """Manage local metadata; never change the source reporting database."""
        if (not operator_name or len(operator_name)>180
                or any(ord(ch)<32 for ch in operator_name)):
            raise ValueError('Invalid operator')
        for field in (destination,team):
            if len(field)>80 or any(ord(ch)<32 for ch in field):
                raise ValueError('Invalid destination or team')
        destination = destination.strip()
        team = team.strip()
        with self.db() as c:
            if not destination and not team:
                c.execute('DELETE FROM operator_directory WHERE operator_name=?',(operator_name,))
            else:
                c.execute(
                    """INSERT INTO operator_directory(operator_name,destination,team,updated_at)
                    VALUES(?,?,?,?) ON CONFLICT(operator_name)
                    DO UPDATE SET destination=excluded.destination,
                    team=excluded.team,updated_at=excluded.updated_at""",
                    (operator_name,destination or None,team or None,int(time.time()))
                )

    @staticmethod
    def _operator_scope_id(value: int) -> int:
        if type(value) is not int or not 1 <= value <= 999_999_999:
            raise ValueError('Invalid verified operator ID')
        return value

    def authorize_operator_scope(
        self, *, admin_id: int, user_id: int, operator_id: int,
        source_identity_verified: bool = False,
    ) -> None:
        """Admin records an independently confirmed stable Odoo operator ID.

        Approval requires proof outside this code; the boolean is an explicit
        operator attestation, NOT automatic inference from a display name.
        No HTTP or MCP method currently exposes this administrative operation.
        """
        operator_id = self._operator_scope_id(operator_id)
        if (type(admin_id) is not int or admin_id <= 0
                or type(user_id) is not int or user_id <= 0
                or source_identity_verified is not True):
            raise ValueError('Explicit verified source identity is required')
        with self.db() as c:
            actor = c.execute(
                "SELECT role,is_active FROM users WHERE id=?", (admin_id,)
            ).fetchone()
            target = c.execute(
                "SELECT role,grants,is_active FROM users WHERE id=?", (user_id,)
            ).fetchone()
            if not actor or not actor['is_active'] or actor['role'] != 'admin':
                raise PermissionError('Active administrator required')
            if (not target or not target['is_active']
                    or 'calls:read' not in permissions(target['role'],target['grants'])):
                raise PermissionError('Active call-reader target required')
            current = int(time.time())
            c.execute(
                """INSERT INTO user_operator_scopes(
                    user_id,operator_id,verified_by,verified_at)
                   VALUES(?,?,?,?)
                   ON CONFLICT(user_id,operator_id)
                   DO UPDATE SET verified_by=excluded.verified_by,
                                 verified_at=excluded.verified_at""",
                (user_id,operator_id,admin_id,current),
            )
            c.execute(
                """INSERT INTO operator_scope_audit
                   (actor_user_id,target_user_id,operator_id,action,event_at)
                   VALUES(?,?,?,'grant',?)""",
                (admin_id,user_id,operator_id,current),
            )
            # Revocation/session change must be immediately effective to any
            # later call; tokens/sessions are resolved again on every request.

    def revoke_operator_scope(
        self, *, admin_id: int, user_id: int, operator_id: int,
    ) -> None:
        operator_id = self._operator_scope_id(operator_id)
        if type(admin_id) is not int or admin_id <= 0 or type(user_id) is not int or user_id <= 0:
            raise ValueError('Invalid scope revocation')
        with self.db() as c:
            actor = c.execute(
                "SELECT role,is_active FROM users WHERE id=?", (admin_id,)
            ).fetchone()
            if not actor or not actor['is_active'] or actor['role'] != 'admin':
                raise PermissionError('Active administrator required')
            existing = c.execute(
                "SELECT 1 FROM user_operator_scopes WHERE user_id=? AND operator_id=?",
                (user_id,operator_id),
            ).fetchone()
            if existing:
                c.execute(
                    "DELETE FROM user_operator_scopes WHERE user_id=? AND operator_id=?",
                    (user_id,operator_id),
                )
                c.execute(
                    """INSERT INTO operator_scope_audit
                       (actor_user_id,target_user_id,operator_id,action,event_at)
                       VALUES(?,?,?,'revoke',?)""",
                    (admin_id,user_id,operator_id,int(time.time())),
                )

    def verified_operator_ids(self, user_id: int) -> list[int]:
        """Default deny, including admins; never infer grants from UI labels."""
        if type(user_id) is not int or user_id <= 0:
            raise ValueError('Invalid local principal')
        with self.db() as c:
            user = c.execute(
                "SELECT role,grants,is_active FROM users WHERE id=?", (user_id,)
            ).fetchone()
            if (not user or not user['is_active']
                    or 'calls:read' not in permissions(user['role'],user['grants'])):
                return []
            rows = c.execute(
                """SELECT operator_id FROM user_operator_scopes
                   WHERE user_id=? ORDER BY operator_id LIMIT 201""",
                (user_id,),
            ).fetchall()
        # Fail closed on overflow. Never return just the first 200 IDs.
        if len(rows) > 200:
            raise ValueError('Verified operator scope exceeds supported size')
        return [int(row['operator_id']) for row in rows]

    def authorize_sensitive_mirror_attempt(
        self, *, user_id: int, call_id: int, surface: str,
    ) -> list[int]:
        """Recheck active capabilities and grants; audit BEFORE any PG read.

        This is an application authorization bridge for the current SQLite
        auth authority. It never accepts user-supplied operator scopes. A
        failure to persist the audit refuses the sensitive read.
        """
        if (type(user_id) is not int or user_id <= 0
                or type(call_id) is not int or not 1 <= call_id <= 999999999
                or surface not in ('dashboard', 'api')):
            raise ValueError('Invalid sensitive mirror audit request')
        with self.db() as c:
            user = c.execute(
                "SELECT role,grants,is_active FROM users WHERE id=?", (user_id,)
            ).fetchone()
            if (not user or not user['is_active']
                    or not {'calls:read', 'calls:sensitive',
                            'calls:transcript:read'} <= permissions(
                                user['role'], user['grants'])):
                raise PermissionError('Sensitive call privileges required')
            rows = c.execute(
                "SELECT operator_id FROM user_operator_scopes "
                "WHERE user_id=? ORDER BY operator_id LIMIT 201",
                (user_id,),
            ).fetchall()
            if not rows:
                raise PermissionError('No verified source operator scope')
            if len(rows) > 200:
                raise ValueError('Verified operator scope exceeds supported size')
            permitted = [int(row['operator_id']) for row in rows]
            # Audit each authorized attempt, including an ID that may not
            # exist, to prevent a silent raw-data read on logging failures.
            c.execute(
                """INSERT INTO sensitive_mirror_access_audit
                   (user_id,call_id,surface,event_at) VALUES(?,?,?,?)""",
                (user_id,call_id,surface,int(time.time())),
            )
        return permitted

    def list_verified_operator_assignments(self, *, admin_id: int) -> list[dict]:
        """Administrative metadata only; never customer rows or raw Odoo data."""
        if type(admin_id) is not int or admin_id <= 0:
            raise PermissionError('Active administrator required')
        with self.db() as c:
            actor = c.execute(
                "SELECT role,is_active FROM users WHERE id=?", (admin_id,)
            ).fetchone()
            if not actor or not actor['is_active'] or actor['role'] != 'admin':
                raise PermissionError('Active administrator required')
            rows = c.execute(
                """SELECT s.user_id, u.username, s.operator_id, s.verified_by,
                          s.verified_at
                   FROM user_operator_scopes AS s
                   JOIN users AS u ON u.id=s.user_id
                   WHERE u.is_active=1
                   ORDER BY u.username, s.operator_id LIMIT 1001"""
            ).fetchall()
        # Explicit bound: never silently truncate an administrative list.
        if len(rows) > 1000:
            raise ValueError('Too many operator approvals to list')
        return [dict(row) for row in rows]

    def create_user(self, username: str, password: str, role: str, caps: list[str] | None = None, *, fields: list[str] | None = None):
        if not username or len(username) > 80 or not username.replace('_','').replace('-','').isalnum():
            raise ValueError('Invalid username')
        if len(password) < 14: raise ValueError('Password must be at least 14 characters')
        validate_user_grants(role, caps)
        grants = json.dumps(sorted(set(caps))) if caps is not None and role != 'admin' else None
        selected = validate_fields(fields, permissions(role, grants)) if fields is not None else None
        with self.db() as c:
            cur = c.execute('INSERT INTO users(username,password_hash,role,grants,field_grants) VALUES(?,?,?,?,?)',
                            (username, password_hash(password), role, grants,
                             json.dumps(selected) if selected is not None else None))
            return cur.lastrowid

    def update_user(self, user_id: int, role: str, caps: list[str] | None, active: bool, actor_id: int, *, fields: list[str] | None = None):
        validate_user_grants(role, caps)
        if int(user_id) == actor_id and (not active or role != 'admin'):
            raise ValueError('Cannot deactivate or demote your own admin account')
        grants = json.dumps(sorted(set(caps))) if caps is not None and role != 'admin' else None
        with self.db() as c:
            user = c.execute('SELECT id,role,is_active,field_grants FROM users WHERE id=?', (user_id,)).fetchone()
            if not user: raise ValueError('Unknown user')
            count = c.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND is_active=1").fetchone()[0]
            if user['role'] == 'admin' and user['is_active'] and count <= 1 and (role != 'admin' or not active):
                raise ValueError('Cannot remove the last active administrator')
            new_caps = permissions(role, grants)
            if fields is not None:
                chosen = validate_fields(fields, new_caps)
                stored_fields = json.dumps(chosen)
            elif user['field_grants'] is not None:
                chosen = sorted(effective_fields(new_caps, user['field_grants']))
                stored_fields = json.dumps(chosen)
            else:
                stored_fields = None  # preserve legacy default within new capabilities
            c.execute('UPDATE users SET role=?,grants=?,field_grants=?,is_active=? WHERE id=?',
                      (role, grants, stored_fields, int(active), user_id))
            # A role change or disable must invalidate all outstanding sessions/tokens.
            c.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))
            c.execute('DELETE FROM access_tokens WHERE owner_id=?', (user_id,))
            # Reauthorization is required after a role or status update.
            c.execute('DELETE FROM oauth_identities WHERE user_id=?', (user_id,))
            c.execute('DELETE FROM mcp_client_grants WHERE user_id=?', (user_id,))
            # Revocation clears individually verified numeric operator scopes.
            assigned = c.execute(
                'SELECT operator_id FROM user_operator_scopes WHERE user_id=?',
                (user_id,),
            ).fetchall()
            if assigned:
                c.executemany(
                    """INSERT INTO operator_scope_audit
                       (actor_user_id,target_user_id,operator_id,action,event_at)
                       VALUES(?,?,?,'reset',?)""",
                    [(actor_id,user_id,row['operator_id'],int(time.time()))
                     for row in assigned],
                )
            c.execute('DELETE FROM user_operator_scopes WHERE user_id=?', (user_id,))

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
            if 'mcp:use' not in caps or not ({'calls:read', 'metrics:read'} & caps):
                raise ValueError('User needs MCP and one reporting permission')
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
        return 'mcp:use' in caps and bool({'calls:read', 'metrics:read'} & caps)

    def authorized_transcript_actor(self, *, oauth_issuer: str | None = None,
                                    oauth_subject: str | None = None,
                                    legacy_token: str | None = None) -> int | None:
        """Re-check one specific MCP caller from trusted credentials, never client-supplied IDs."""
        if bool(legacy_token) == bool(oauth_subject):
            return None
        with self.db() as c:
            if oauth_subject is not None:
                row = c.execute(
                    """SELECT u.id,u.role,u.grants,u.is_active
                       FROM oauth_identities i JOIN users u ON u.id=i.user_id
                       WHERE i.issuer=? AND i.subject=?""",
                    (oauth_issuer, oauth_subject),
                ).fetchone()
            else:
                if not legacy_token or len(legacy_token) > 256:
                    return None
                row = c.execute(
                    """SELECT u.id,u.role,u.grants,u.is_active
                       FROM access_tokens t JOIN users u ON u.id=t.owner_id
                       WHERE t.token_hash=? AND t.scope='mcp:read'
                       AND t.expires_at>?""",
                    (digest(legacy_token), int(time.time())),
                ).fetchone()
        if not row or not row['is_active']:
            return None
        caps = permissions(row['role'], row['grants'])
        if not {'mcp:use', 'calls:read', 'calls:transcript:read'} <= caps:
            return None
        return int(row['id'])

    def audit_transcript_request(self, *, user_id: int, surface: str,
                                 call_id: int, char_limit: int) -> bool:
        """Log every authorized transcript retrieval, without arbitrary quotas.

        The per-request chunk size protects HTTP performance. The user may
        fetch all remaining chunks, regardless of conversation length.
        """
        if surface not in ('mcp', 'webmcp') or call_id < 1 or not 1 <= char_limit <= 6000:
            return False
        now = int(time.time())
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT role,grants,field_grants,is_active FROM users WHERE id=?',(user_id,)).fetchone()
            caps = permissions(row['role'], row['grants']) if row and row['is_active'] else set()
            if (not {'calls:read', 'calls:transcript:read'} <= caps or
                    'transcription' not in effective_fields(caps, row['field_grants'])):
                return False
            c.execute(
                'INSERT INTO transcript_access_audit(user_id,surface,call_id,char_limit,created_at) VALUES(?,?,?,?,?)',
                (user_id, surface, call_id, char_limit, now)
            )
            return True

    def user_access(self, user_id: int) -> dict | None:
        """Current effective user fields and capabilities, not cached claims."""
        with self.db() as c:
            row = c.execute(
                'SELECT id,role,grants,field_grants,is_active FROM users WHERE id=?',
                (user_id,),
            ).fetchone()
        if not row or not row['is_active']:
            return None
        caps = permissions(row['role'], row['grants'])
        return {'user_id': int(row['id']), 'capabilities': caps,
                'fields': effective_fields(caps, row['field_grants'])}

    def client_grants(self, user_id: int, client_id: str) -> dict | None:
        if not isinstance(client_id, str) or not 1 <= len(client_id) <= 160:
            return None
        with self.db() as c:
            row = c.execute(
                'SELECT capabilities,fields FROM mcp_client_grants '
                'WHERE user_id=? AND client_id=?', (user_id, client_id)
            ).fetchone()
        if row is None:
            return None
        try:
            caps = json.loads(row['capabilities'])
            fields = json.loads(row['fields'])
            if (type(caps) is not list or type(fields) is not list or
                    not all(type(v) is str for v in caps + fields)):
                return None
            return {'capabilities': frozenset(caps),
                    'fields': frozenset(fields)}
        except (TypeError, ValueError):
            return None

    def approve_mcp_client(self, user_id: int, client_id: str,
                           caps: list[str], fields: list[str]) -> None:
        """Explicit logged-in user's approval for one trusted OAuth client ID."""
        if (type(client_id) is not str or not 1 <= len(client_id) <= 160 or
                any(ord(ch) < 33 or ord(ch) > 126 for ch in client_id)):
            raise ValueError('Invalid OAuth client identifier')
        access = self.user_access(user_id)
        if access is None or 'mcp:use' not in access['capabilities']:
            raise ValueError('MCP not available for this account')
        allowed_caps = access['capabilities'] & {
            'mcp:use', 'calls:read', 'metrics:read', 'calls:transcript:read'}
        if (type(caps) is not list or len(set(caps)) != len(caps) or
                not set(caps) <= allowed_caps):
            raise ValueError('Invalid delegated capabilities')
        if 'mcp:use' not in caps:
            raise ValueError('Client requires MCP consent')
        if 'calls:transcript:read' in caps and 'calls:read' not in caps:
            raise ValueError('Transcript delegation requires calls:read')
        selected = validate_fields(fields, access['capabilities'])
        if not set(selected) <= access['fields']:
            raise ValueError('Delegated fields exceed user access')
        if not set(selected) <= capability_fields(set(caps)):
            raise ValueError('Delegated fields require matching approved capability')
        with self.db() as c:
            c.execute(
                'INSERT INTO mcp_client_grants(user_id,client_id,capabilities,fields,approved_at) '
                'VALUES(?,?,?,?,?) ON CONFLICT(user_id,client_id) DO UPDATE SET '
                'capabilities=excluded.capabilities,fields=excluded.fields,'
                'approved_at=excluded.approved_at',
                (user_id, client_id, json.dumps(sorted(caps)),
                 json.dumps(selected), int(time.time()))
            )

    def revoke_mcp_client(self, user_id: int, client_id: str) -> None:
        with self.db() as c:
            c.execute('DELETE FROM mcp_client_grants WHERE user_id=? AND client_id=?',
                      (user_id, client_id))

    def list_mcp_clients(self, user_id: int) -> list[dict]:
        with self.db() as c:
            return [dict(row) for row in c.execute(
                'SELECT client_id,capabilities,fields,approved_at '
                'FROM mcp_client_grants WHERE user_id=? ORDER BY approved_at DESC',
                (user_id,))]

    def mcp_access(self, user_id: int, *, legacy_token: str | None = None,
                   oauth_client: str | None = None) -> dict | None:
        """Request-time intersection of user, token and app-approved grants."""
        access = self.user_access(user_id)
        if access is None or 'mcp:use' not in access['capabilities']:
            return None
        approved = None
        if legacy_token:
            with self.db() as c:
                row = c.execute(
                    'SELECT t.field_grants,t.cap_grants FROM access_tokens t '
                    'WHERE t.owner_id=? AND t.token_hash=? AND t.scope=? '
                    'AND t.expires_at>?',
                    (user_id, digest(legacy_token), 'mcp:read', int(time.time()))
                ).fetchone()
            if row is None:
                return None
            try:
                caps = (frozenset(json.loads(row['cap_grants']))
                        if row['cap_grants'] is not None else
                        frozenset({'mcp:use','calls:read','metrics:read',
                                   'calls:transcript:read'}))
                fields = (frozenset(json.loads(row['field_grants']))
                          if row['field_grants'] is not None else
                          capability_fields({'calls:read','calls:sensitive','metrics:read'}))
                approved = {'capabilities': caps, 'fields': fields}
            except (TypeError, ValueError):
                return None
        elif oauth_client:
            approved = self.client_grants(user_id, oauth_client)
            if approved is None:
                approved = {'capabilities': frozenset(), 'fields': frozenset()}
        else:
            return None
        effective_caps = access['capabilities'] & approved['capabilities']
        effective_fields = access['fields'] & approved['fields'] & capability_fields(effective_caps)
        return {'user_fields': access['fields'],
                'user_capabilities': access['capabilities'],
                'approved_fields': approved['fields'],
                'approved_capabilities': approved['capabilities'],
                'fields': effective_fields,
                'capabilities': effective_caps}


    def api_token_access(self, user_id: int, raw: str, scope: str) -> dict | None:
        """Intersect an authenticated API token's original grants with live policy.

        Historical NULL snapshots keep legacy API tokens functional until
        an explicitly reviewed rotation; new tokens cannot silently expand.
        """
        if (scope not in ('api:read', 'api:sensitive') or
                not raw or len(raw) > 256):
            return None
        access = self.user_access(user_id)
        if access is None:
            return None
        with self.db() as c:
            row = c.execute(
                'SELECT scope,field_grants,cap_grants FROM access_tokens '
                'WHERE owner_id=? AND token_hash=? AND expires_at>?',
                (user_id, digest(raw), int(time.time()))
            ).fetchone()
        if not row or (row['scope'] != scope and not (
                scope == 'api:read' and row['scope'] == 'api:sensitive')):
            return None
        try:
            capabilities = set(access['capabilities'])
            if row['cap_grants'] is not None:
                stored_caps = json.loads(row['cap_grants'])
                if (type(stored_caps) is not list or
                        any(type(v) is not str for v in stored_caps)):
                    return None
                capabilities &= set(stored_caps)
            fields = set(access['fields'])
            if row['field_grants'] is not None:
                stored_fields = json.loads(row['field_grants'])
                if (type(stored_fields) is not list or
                        any(type(v) is not str for v in stored_fields) or
                        len(stored_fields) != len(set(stored_fields))):
                    return None
                fields &= set(stored_fields)
            if scope == 'api:read':
                capabilities &= {'calls:read', 'metrics:read'}
            elif not {'calls:read', 'calls:sensitive'} <= capabilities:
                return None
            fields &= capability_fields(capabilities)
            return {'capabilities': frozenset(capabilities),
                    'fields': frozenset(fields)}
        except (TypeError, ValueError):
            return None

    def actor_for_token(self, raw: str, scope: str) -> int | None:
        """Resolve owner from an already-authenticated service token, or None."""
        if not raw or len(raw) > 256 or scope not in ('mcp:read','api:read','api:sensitive'):
            return None
        with self.db() as c:
            row = c.execute(
                """SELECT u.id,u.role,u.grants,u.is_active,t.scope
                   FROM access_tokens t JOIN users u ON u.id=t.owner_id
                   WHERE t.token_hash=? AND t.expires_at>?""",
                (digest(raw),int(time.time())),
            ).fetchone()
        if not row or not row['is_active'] or (
            row['scope'] != scope and not (scope == 'api:read' and row['scope'] == 'api:sensitive')
        ):
            return None
        return int(row['id'])

    def actor_for_oauth(self, issuer: str, subject: str) -> int | None:
        if not issuer or not subject:
            return None
        with self.db() as c:
            row=c.execute(
                """SELECT u.id,u.role,u.grants,u.is_active
                   FROM oauth_identities i JOIN users u ON u.id=i.user_id
                   WHERE i.issuer=? AND i.subject=?""",
                (issuer,subject),
            ).fetchone()
        return int(row['id']) if row and row['is_active'] else None

    def record_activity(self, *, user_id: int | None, surface: str, action: str,
                        http_status: int, duration_ms: int) -> None:
        """Append safe request metadata only. No body, URL params or secrets."""
        if surface not in ('dashboard','api','mcp','auth') or not 1 <= len(action) <= 120:
            raise ValueError('Invalid audit event')
        if not 100 <= http_status <= 599:
            raise ValueError('Invalid HTTP status')
        with self.db() as c:
            c.execute(
                """INSERT INTO activity_events
                   (user_id,surface,action,http_status,duration_ms,created_at)
                   VALUES(?,?,?,?,?,?)""",
                (user_id,surface,action,http_status,max(0,min(duration_ms,600000)),int(time.time())),
            )
            # 90-day retention prevents unbounded growth; no customer data stored.
            c.execute('DELETE FROM activity_events WHERE created_at<?',
                      (int(time.time())-90*86400,))

    def activity_report(self, *, days: int = 14, user_id: int | None = None,
                        surface: str | None = None, errors_only: bool = False,
                        limit: int = 100) -> dict:
        if not 1 <= days <= 90 or not 1 <= limit <= 250:
            raise ValueError('Invalid report range')
        if surface and surface not in ('dashboard','api','mcp','auth'):
            raise ValueError('Invalid activity surface')
        where=['a.created_at>=?']
        params=[int(time.time())-days*86400]
        if user_id is not None:
            where.append('a.user_id=?');params.append(user_id)
        if surface:
            where.append('a.surface=?');params.append(surface)
        if errors_only:
            where.append('a.http_status>=400')
        clause=' WHERE '+' AND '.join(where)
        with self.db() as c:
            daily=[dict(row) for row in c.execute(
                """SELECT strftime('%Y-%m-%d',a.created_at,'unixepoch') AS day,
                   COUNT(*) AS total,
                   SUM(CASE WHEN a.http_status>=400 THEN 1 ELSE 0 END) AS errors
                   FROM activity_events a""" + clause + " GROUP BY day ORDER BY day", params
            )]
            surfaces=[dict(row) for row in c.execute(
                """SELECT a.surface AS name,COUNT(*) AS total
                   FROM activity_events a""" + clause + " GROUP BY a.surface ORDER BY total DESC", params
            )]
            actions=[dict(row) for row in c.execute(
                """SELECT a.action AS name,COUNT(*) AS total
                   FROM activity_events a""" + clause + " GROUP BY a.action ORDER BY total DESC LIMIT 8", params
            )]
            users=[dict(row) for row in c.execute(
                """SELECT COALESCE(u.username,'ناشناس') AS name,COUNT(*) AS total
                   FROM activity_events a LEFT JOIN users u ON u.id=a.user_id""" +
                clause + " GROUP BY a.user_id ORDER BY total DESC LIMIT 8",params
            )]
            active_users=c.execute(
                'SELECT COUNT(DISTINCT a.user_id) FROM activity_events a' +
                clause + ' AND a.user_id IS NOT NULL',params
            ).fetchone()[0]
            recent=[dict(row) for row in c.execute(
                """SELECT a.id,COALESCE(u.username,'ناشناس') AS username,a.surface,
                   a.action,a.http_status,a.duration_ms,a.created_at
                   FROM activity_events a LEFT JOIN users u ON u.id=a.user_id""" +
                clause + " ORDER BY a.id DESC LIMIT ?",(*params,limit)
            )]
        total=sum(item['total'] for item in surfaces)
        failed=sum(item['errors'] for item in daily)
        return {'total':total,'errors':failed,'active_users':active_users,
                'days':daily,'surfaces':surfaces,
                'actions':actions,'users':users,'recent':recent}

    def list_transcript_audit(self, limit: int = 100) -> list[dict]:
        with self.db() as c:
            return [dict(r) for r in c.execute(
                """SELECT a.id,u.username,a.surface,a.call_id,a.char_limit,a.created_at
                   FROM transcript_access_audit a JOIN users u ON u.id=a.user_id
                   ORDER BY a.id DESC LIMIT ?""",
                (max(1,min(int(limit),500)),)
            )]

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
            owner = c.execute('SELECT role,grants,field_grants,is_active FROM users WHERE id=?', (owner_id,)).fetchone()
            if not owner or not owner['is_active']: raise ValueError('Inactive owner')
            grants = permissions(owner['role'], owner['grants'])
            required = ({'calls:read', 'metrics:read'} if scope == 'api:read' else
                        {'calls:read', 'calls:sensitive'} if scope == 'api:sensitive' else
                        {'mcp:use'})
            allowed = (bool(grants & required) if scope == 'api:read' else
                       (required <= grants and bool({'calls:read','metrics:read'} & grants))
                       if scope == 'mcp:read' else required <= grants)
            if not allowed:
                raise ValueError('Owner has insufficient permissions')
            # Snapshot the authority of every NEW token. Later grant changes
            # must not expand a previously issued REST or MCP credential.
            scope_caps = ({'mcp:use','calls:read','metrics:read','calls:transcript:read'}
                          if scope == 'mcp:read' else
                          {'calls:read','calls:sensitive','calls:transcript:read','metrics:read'}
                          if scope == 'api:sensitive' else
                          {'calls:read','metrics:read'})
            snapshot_caps = grants & scope_caps
            snapshot_fields = (effective_fields(grants, owner['field_grants'])
                               & capability_fields(snapshot_caps))
            fields = json.dumps(sorted(snapshot_fields))
            granted_caps = json.dumps(sorted(snapshot_caps))
            cur = c.execute('''INSERT INTO access_tokens(name,token_hash,scope,created_at,expires_at,owner_id,field_grants,cap_grants)
                               VALUES(?,?,?,?,?,?,?,?)''',
                            (name[:80], digest(raw), scope, now, now + days*86400, owner_id, fields, granted_caps))
            return cur.lastrowid, raw

    def verify_token(self, raw: str, scope: str, capability: str | None = None) -> bool:
        if not raw or len(raw) > 256: return False
        with self.db() as c:
            row = c.execute('''SELECT t.id,t.scope,t.cap_grants,u.role,u.grants,u.is_active
                               FROM access_tokens t JOIN users u ON u.id=t.owner_id
                               WHERE t.token_hash=? AND t.expires_at>?''', (digest(raw), int(time.time()))).fetchone()
            grants = permissions(row['role'], row['grants']) if row and row['is_active'] else set()
            # NULL snapshots are pre-existing tokens; keep those working
            # until an explicitly approved rotation. Invalid JSON fails closed.
            if row and row['cap_grants'] is not None:
                try:
                    issued = json.loads(row['cap_grants'])
                    if type(issued) is not list or any(type(x) is not str for x in issued):
                        grants = set()
                    else:
                        grants &= set(issued)
                except (TypeError, ValueError):
                    grants = set()
            matching = bool(row and (row['scope'] == scope or
                            (scope == 'api:read' and row['scope'] == 'api:sensitive')))
            valid = bool(matching and (
                ({'calls:read','metrics:read'} & grants) if scope == 'api:read' else
                {'calls:read','calls:sensitive'} <= grants if scope == 'api:sensitive' else
                ('mcp:use' in grants and bool({'calls:read','metrics:read'} & grants)) if scope == 'mcp:read' else False
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
