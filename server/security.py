"""Local session authentication, per-user capabilities, and revocable service tokens.

SQLite is for Panadan identities only. Never use it to store customer reporting rows.
"""
import hashlib
import hmac
import json
import re
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

# Independently delegated browser administration; not REST/MCP data grants.
NATIVE_PANEL_GRANTS = {
    'system:read': ('وضعیت سیستم', 'مشاهده سلامت سامانه و وضعیت همگام‌سازی، بدون تغییر زیرساخت.'),
    'activity:read': ('فعالیت کاربران', 'مشاهده فراداده فعالیت و رویدادهای همه کاربران؛ بدون متن مکالمه یا توکن.'),
    'operators:manage': ('مدیریت کارشناسان', 'تغییر مقصد و تیم کارشناسان؛ نیازمند مجوز گزارش و ستون کارشناس.'),
    'api:docs': ('مستندات API', 'مشاهده مستندات فنی API؛ به خودی خود مجوز داده نیست.'),
    'connect:read': ('راهنمای اتصال', 'مشاهده راهنمای اتصال دستیارها؛ بدون اعطای مجوز MCP یا داده.'),
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
                CREATE TABLE IF NOT EXISTS authkit_sessions (
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
            c.execute("""CREATE TABLE IF NOT EXISTS authkit_accounts (
                user_id INTEGER PRIMARY KEY,
                issuer TEXT NOT NULL,
                subject TEXT NOT NULL,
                email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                panel_grants TEXT NOT NULL DEFAULT '[]',
                created_at INTEGER NOT NULL,
                last_login INTEGER NOT NULL,
                UNIQUE(issuer,subject)
            )""")
            account_columns = {r['name'] for r in c.execute('PRAGMA table_info(authkit_accounts)')}
            if 'requested_at' not in account_columns:
                c.execute('ALTER TABLE authkit_accounts ADD COLUMN requested_at INTEGER')
            if 'request_note' not in account_columns:
                c.execute('ALTER TABLE authkit_accounts ADD COLUMN request_note TEXT')
            c.execute('''CREATE TABLE IF NOT EXISTS mcp_client_grants (
                user_id INTEGER NOT NULL,
                client_id TEXT NOT NULL,
                capabilities TEXT NOT NULL,
                fields TEXT NOT NULL,
                approved_at INTEGER NOT NULL,
                PRIMARY KEY(user_id,client_id)
            )''')
            # Optional WorkOS login handoff requires an explicitly attested
            # email for each Panadan user. This is contact metadata only;
            # Panadan retains all passwords, sessions, roles and permissions.
            c.execute("""CREATE TABLE IF NOT EXISTS oauth_verified_emails (
                user_id INTEGER PRIMARY KEY,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                attested_by INTEGER NOT NULL,
                attested_at INTEGER NOT NULL,
                evidence_ref TEXT NOT NULL
            )""")
            # A signed OAuth token may announce a new client without giving
            # it access. User approval remains necessary on the dashboard.
            c.execute("""CREATE TABLE IF NOT EXISTS mcp_client_requests (
                user_id INTEGER NOT NULL,
                client_id TEXT NOT NULL,
                first_seen INTEGER NOT NULL,
                last_seen INTEGER NOT NULL,
                PRIMARY KEY(user_id,client_id)
            )""")
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

    def create_session(self, uid: int, *, auth_source: str = 'local') -> tuple[str, str]:
        raw, csrf = secrets.token_urlsafe(40), secrets.token_urlsafe(32)
        with self.db() as c:
            if auth_source not in ('local', 'authkit'):
                raise ValueError('Unknown session authentication source')
            table = 'authkit_sessions' if auth_source == 'authkit' else 'sessions'
            c.execute(f'INSERT INTO {table}(token_hash,user_id,csrf,expires_at) VALUES(?,?,?,?)',
                      (digest(raw), uid, csrf, int(time.time()) + SESSION_SECONDS))
        return raw, csrf

    def session(self, raw: str | None, *, auth_source: str = 'local'):
        if not raw: return None
        if auth_source not in ('local', 'authkit'):
            return None
        table = 'authkit_sessions' if auth_source == 'authkit' else 'sessions'
        with self.db() as c:
            row = c.execute(f'''SELECT s.user_id,s.csrf,u.username,u.role,u.grants,u.field_grants
                               FROM {table} s JOIN users u ON u.id=s.user_id
                               WHERE s.token_hash=? AND s.expires_at>? AND u.is_active=1''',
                            (digest(raw), int(time.time()))).fetchone()
        return dict(row) if row else None

    def logout(self, raw: str | None):
        if raw:
            with self.db() as c:
                c.execute('DELETE FROM sessions WHERE token_hash=?', (digest(raw),))
                c.execute('DELETE FROM authkit_sessions WHERE token_hash=?', (digest(raw),))

    def prepare_authkit_admin(self, uid: int, issuer: str, subject: str, *, multi_user: bool = False) -> None:
        """Cut over only the pinned local admin, preserving all historical rows.

        No password is accepted in native mode. Old users are disabled, not
        deleted. Replace only the known Standalone subject or the native one.
        """
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            admin = c.execute("SELECT role,is_active FROM users WHERE id=?", (uid,)).fetchone()
            if not admin or admin["role"] != "admin" or not admin["is_active"]:
                raise ValueError("Pinned local administrator must be active")
            old = c.execute("SELECT subject FROM oauth_identities WHERE issuer=? AND user_id=?",
                            (issuer, uid)).fetchone()
            owner = c.execute("SELECT user_id FROM oauth_identities WHERE issuer=? AND subject=?",
                              (issuer, subject)).fetchone()
            if (old and old["subject"] not in (subject, f"panadan-user-{uid}")) or (
                    owner and owner["user_id"] != uid):
                raise ValueError("Native OAuth identity requires administrator review")
            if multi_user:
                # Existing native accounts retain explicitly assigned status.
                # Historical password-only accounts remain disabled.
                c.execute("""UPDATE users SET is_active=0 WHERE id<>?
                    AND (role='admin' OR id NOT IN
                    (SELECT user_id FROM authkit_accounts WHERE issuer=?))""", (uid,issuer))
            else:
                c.execute("UPDATE users SET is_active=0 WHERE id<>?", (uid,))
            if not old or old["subject"] != subject:
                c.execute("DELETE FROM oauth_identities WHERE issuer=? AND user_id=?", (issuer, uid))
                c.execute("INSERT INTO oauth_identities(issuer,subject,user_id,created_at) VALUES(?,?,?,?)",
                          (issuer, subject, uid, int(time.time())))
                c.execute("DELETE FROM mcp_client_grants WHERE user_id=?", (uid,))
                c.execute("DELETE FROM mcp_client_requests WHERE user_id=?", (uid,))

    def native_account(self, uid: int, issuer: str) -> dict | None:
        with self.db() as c:
            row = c.execute("""SELECT a.*,u.is_active FROM authkit_accounts a
                JOIN users u ON u.id=a.user_id
                JOIN oauth_identities i ON i.user_id=u.id AND i.issuer=a.issuer AND i.subject=a.subject
                WHERE a.user_id=? AND a.issuer=? AND u.role<>'admin'""", (uid,issuer)).fetchone()
        if not row:
            return None
        result = dict(row)
        try:
            parsed = json.loads(result['panel_grants'])
            result['panel_grants'] = set(parsed) & set(NATIVE_PANEL_GRANTS) if isinstance(parsed,list) else set()
        except (ValueError, TypeError):
            result['panel_grants'] = set()
        return result

    def native_accounts(self, issuer: str) -> dict[int, dict]:
        with self.db() as c:
            ids = [r['user_id'] for r in c.execute(
                'SELECT user_id FROM authkit_accounts WHERE issuer=?', (issuer,))]
        return {uid: account for uid in ids if (account := self.native_account(uid,issuer)) is not None}

    def provision_native_user(self, issuer: str, subject: str, email: str) -> int:
        """Only call after a verified WorkOS code exchange. Never link by email."""
        if (not issuer or not re.fullmatch(r'user_[A-Za-z0-9]{1,120}', subject)
                or len(email)>254 or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',email)):
            raise ValueError('Invalid verified identity')
        email=email.lower()
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            existing = c.execute("""SELECT a.user_id,a.email,u.is_active,u.role
                FROM authkit_accounts a JOIN users u ON u.id=a.user_id
                JOIN oauth_identities i ON i.user_id=u.id AND i.issuer=a.issuer AND i.subject=a.subject
                WHERE a.issuer=? AND a.subject=?""", (issuer,subject)).fetchone()
            if existing:
                if not existing['is_active'] or existing['role']=='admin' or existing['email']!=email:
                    raise ValueError('Account disabled or identity changed')
                uid=existing['user_id']
                c.execute('UPDATE authkit_accounts SET last_login=? WHERE user_id=?',(int(time.time()),uid))
                return uid
            # A matching legacy subject or email never inherits an old account.
            if c.execute('SELECT 1 FROM oauth_identities WHERE issuer=? AND subject=?',(issuer,subject)).fetchone():
                raise ValueError('Existing identity requires review')
            if c.execute('SELECT 1 FROM authkit_accounts WHERE email=?',(email,)).fetchone():
                raise ValueError('Existing email requires review')
            now=int(time.time())
            cur=c.execute("""INSERT INTO users(username,password_hash,role,grants,field_grants,is_active)
                VALUES(?,?,'reader','[]','[]',1)""",('workos_'+secrets.token_hex(16),password_hash(secrets.token_urlsafe(48))))
            uid=cur.lastrowid
            c.execute("""INSERT INTO authkit_accounts(user_id,issuer,subject,email,created_at,last_login)
                VALUES(?,?,?,?,?,?)""",(uid,issuer,subject,email,now,now))
            c.execute('INSERT INTO oauth_identities(issuer,subject,user_id,created_at) VALUES(?,?,?,?)',(issuer,subject,uid,now))
            return uid

    def request_native_access(self, uid: int, issuer: str, note: str) -> None:
        note=note.strip()
        if len(note)>500 or any(ord(ch)<32 and ch not in '\n\t' for ch in note):
            raise ValueError('Invalid access request')
        with self.db() as c:
            cur=c.execute("""UPDATE authkit_accounts SET requested_at=?,request_note=?
                WHERE user_id=? AND issuer=? AND EXISTS(
                SELECT 1 FROM users u WHERE u.id=authkit_accounts.user_id AND u.is_active=1)""",
                (int(time.time()),note,uid,issuer))
            if cur.rowcount!=1:
                raise ValueError('Account unavailable')

    def update_native_user(self, uid: int, issuer: str, *, actor_id: int,
                           active: bool, caps: list[str], fields: list[str], panels: list[str]) -> None:
        """Owner-only edit. Identity stays immutable; downstream grants are revoked."""
        if uid==actor_id or not set(panels)<=set(NATIVE_PANEL_GRANTS) or len(panels)!=len(set(panels)):
            raise ValueError('Invalid administrative grants')
        if len(caps)!=len(set(caps)):
            raise ValueError('Duplicate capabilities')
        validate_user_grants('reader',caps)
        grants=json.dumps(sorted(caps))
        selected=validate_fields(fields,permissions('reader',grants))
        if 'operators:manage' in panels and ('calls:read' not in caps or 'vw_danix_base_info_users_name' not in selected):
            raise ValueError('Operator management requires operator data access')
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            actor=c.execute("SELECT role,is_active FROM users WHERE id=?",(actor_id,)).fetchone()
            target=c.execute("""SELECT u.role FROM users u JOIN authkit_accounts a ON a.user_id=u.id
                JOIN oauth_identities i ON i.user_id=u.id AND i.issuer=a.issuer AND i.subject=a.subject
                WHERE u.id=? AND a.issuer=?""",(uid,issuer)).fetchone()
            if not actor or actor['role']!='admin' or not actor['is_active'] or not target or target['role']=='admin':
                raise ValueError('Account cannot be edited')
            c.execute("UPDATE users SET role='reader',grants=?,field_grants=?,is_active=? WHERE id=?",
                      (grants,json.dumps(selected),int(active),uid))
            c.execute('UPDATE authkit_accounts SET panel_grants=?,requested_at=NULL,request_note=NULL WHERE user_id=?',
                      (json.dumps(sorted(panels)),uid))
            c.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
            c.execute('DELETE FROM authkit_sessions WHERE user_id=?',(uid,))
            c.execute('DELETE FROM access_tokens WHERE owner_id=?',(uid,))
            c.execute('DELETE FROM mcp_client_grants WHERE user_id=?',(uid,))
            c.execute('DELETE FROM mcp_client_requests WHERE user_id=?',(uid,))

    def attest_workos_email(self, user_id: int, email: str,
                            *, attested_by: int, evidence_ref: str) -> None:
        """Explicit admin attestation; never infer account ownership from email."""
        if not isinstance(email, str):
            raise ValueError('Invalid email address')
        email = email.strip().lower()
        if (len(email) > 254 or not re.fullmatch(
                r'[a-z0-9.!#$%&\'*+/=?^_`{|}~-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+', email)):
            raise ValueError('Invalid email address')
        if (not isinstance(evidence_ref, str) or
                not 8 <= len(evidence_ref.strip()) <= 160 or
                any(ord(ch) < 32 for ch in evidence_ref)):
            raise ValueError('Verification evidence reference is required')
        with self.db() as c:
            admin = c.execute(
                "SELECT role,is_active FROM users WHERE id=?", (attested_by,)
            ).fetchone()
            user = c.execute(
                "SELECT is_active FROM users WHERE id=?", (user_id,)
            ).fetchone()
            if not admin or not admin['is_active'] or admin['role'] != 'admin':
                raise ValueError('Only an active administrator can attest identity')
            if not user or not user['is_active']:
                raise ValueError('User must be active')
            c.execute("""INSERT INTO oauth_verified_emails(
                user_id,email,attested_by,attested_at,evidence_ref
            ) VALUES(?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET
                email=excluded.email, attested_by=excluded.attested_by,
                attested_at=excluded.attested_at,
                evidence_ref=excluded.evidence_ref""",
                (user_id, email, attested_by, int(time.time()), evidence_ref.strip()))

    def workos_verified_email(self, user_id: int) -> str | None:
        with self.db() as c:
            row = c.execute("""SELECT e.email FROM oauth_verified_emails e
                JOIN users u ON u.id=e.user_id
                WHERE e.user_id=? AND u.is_active=1""", (user_id,)).fetchone()
        return row['email'] if row else None

    def list_workos_verified_emails(self) -> list[dict]:
        with self.db() as c:
            return [dict(row) for row in c.execute(
                'SELECT user_id,email,attested_by,attested_at,evidence_ref '
                'FROM oauth_verified_emails ORDER BY user_id')]

    def revoke_workos_email(self, user_id: int) -> None:
        with self.db() as c:
            c.execute('DELETE FROM oauth_verified_emails WHERE user_id=?', (user_id,))
            c.execute('DELETE FROM oauth_identities WHERE user_id=?', (user_id,))
            c.execute('DELETE FROM mcp_client_grants WHERE user_id=?', (user_id,))

    def note_signed_mcp_client(self, user_id: int, client_id: str) -> None:
        """Discovery is NOT consent; only record client IDs from verified JWTs."""
        if (type(client_id) is not str or not 1 <= len(client_id) <= 160 or
                any(ord(ch) < 33 or ord(ch) > 126 for ch in client_id)):
            return
        now = int(time.time())
        with self.db() as c:
            c.execute("""INSERT OR IGNORE INTO mcp_client_requests(
                user_id,client_id,first_seen,last_seen
            ) VALUES(?,?,?,?)""", (user_id,client_id,now,now))
            c.execute("""UPDATE mcp_client_requests SET last_seen=?
                WHERE user_id=? AND client_id=? AND last_seen<?""",
                (now,user_id,client_id,now-3600))

    def list_pending_mcp_clients(self, user_id: int) -> list[dict]:
        with self.db() as c:
            return [dict(row) for row in c.execute(
                """SELECT r.client_id,r.first_seen,r.last_seen
                   FROM mcp_client_requests r
                   LEFT JOIN mcp_client_grants g
                   ON g.user_id=r.user_id AND g.client_id=r.client_id
                   WHERE r.user_id=? AND g.client_id IS NULL
                     AND r.last_seen>? ORDER BY r.last_seen DESC LIMIT 20""",
                (user_id,int(time.time())-30*86400))]

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
            c.execute('DELETE FROM authkit_sessions WHERE user_id=?', (user_id,))
            c.execute('DELETE FROM access_tokens WHERE owner_id=?', (user_id,))
            # Reauthorization is required after a role or status update.
            c.execute('DELETE FROM oauth_identities WHERE user_id=?', (user_id,))
            c.execute('DELETE FROM mcp_client_grants WHERE user_id=?', (user_id,))
            c.execute('DELETE FROM oauth_verified_emails WHERE user_id=?', (user_id,))
            c.execute('DELETE FROM mcp_client_requests WHERE user_id=?', (user_id,))

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
                          {'calls:read','calls:sensitive','metrics:read'}
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
