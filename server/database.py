"""Hard-coded, parameterized, read-only Odoo reporting view access."""
from __future__ import annotations
from contextlib import contextmanager
from datetime import date, datetime
from zoneinfo import ZoneInfo
from decimal import Decimal
from typing import Any
import os
import psycopg
from psycopg.rows import dict_row

VIEW = 'public.vw_danix_call_info_report'
PUBLIC_COLUMNS = (
    'id', 'CALLDATE', 'tellstate', 'tellside', 'aicallinfostate',
    'voice_length', 'possibility_of_sale_ai', 'deal_value',
    'vw_danix_base_info_users_name',
)
SENSITIVE_COLUMNS = (
    'call_id','customername','customertell','outcome','ai_recommendation',
    'summary','transcription','tell_state_desc','create_date',
)


def normalized(row: dict) -> dict:
    def conv(v):
        if isinstance(v, (date, datetime)): return v.isoformat()
        if isinstance(v, Decimal): return float(v)
        return v
    return {k: conv(v) for k, v in row.items()}


@contextmanager
def connect():
    with psycopg.connect(
        host=os.getenv('PGHOST', '192.168.3.9'),
        port=int(os.getenv('PGPORT', '5432')),
        dbname=os.getenv('PGDATABASE', 'odoo'),
        user=os.environ['PGUSER'], password=os.environ['PGPASSWORD'],
        sslmode='require', connect_timeout=10,
        options='-c default_transaction_read_only=on -c statement_timeout=12000',
        row_factory=dict_row, autocommit=True,
    ) as conn:
        # Defense in depth: every reporting operation is in an explicit
        # server-enforced READ ONLY transaction, even if the role has broader
        # grants. Local SQLite auth writes are intentionally separate.
        with conn.transaction():
            conn.execute('SET TRANSACTION READ ONLY')
            yield conn


def filters(after: date | None, before: date | None, state: str | None,
            created_after: datetime | None = None, created_before: datetime | None = None,
            call_type: str | None = None):
    parts, args = [], []
    if after: parts.append('"CALLDATE" >= %s'); args.append(after)
    if before: parts.append('"CALLDATE" <= %s'); args.append(before)
    if state: parts.append('"aicallinfostate" = %s'); args.append(state)
    if call_type: parts.append('"tellstate" = %s'); args.append(call_type)
    # Odoo's create_date is a naive UTC timestamp; display times are Asia/Tehran.
    # Convert aware ISO inputs to a UTC-naive timestamp for comparisons.
    from datetime import timezone
    for op, value in [('>=', created_after), ('<=', created_before)]:
        if value:
            if value.tzinfo is None: value = value.replace(tzinfo=ZoneInfo('Asia/Tehran'))
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
            parts.append(f'"create_date" {op} %s')
            args.append(value)
    return (' WHERE ' + ' AND '.join(parts)) if parts else '', args


def list_calls(limit: int = 20, offset: int = 0, after: date | None = None,
               before: date | None = None, state: str | None = None,
               created_after: datetime | None = None, created_before: datetime | None = None,
               call_type: str | None = None):
    limit = max(1, min(int(limit), 100))
    offset = max(0, min(int(offset), 10000))
    if after and before and after > before: raise ValueError('Invalid date range')
    if state and len(state) > 60: raise ValueError('Invalid state')
    if call_type and len(call_type) > 60: raise ValueError('Invalid call type')
    if created_after and created_before and created_after > created_before: raise ValueError('Invalid time range')
    where, params = filters(after, before, state, created_after, created_before, call_type)
    q = ('SELECT ' + ','.join('"' + c + '"' for c in PUBLIC_COLUMNS) +
         ' FROM ' + VIEW + where + ' ORDER BY "CALLDATE" DESC NULLS LAST, id DESC LIMIT %s OFFSET %s')
    with connect() as c:
        rows = c.execute(q, (*params, limit, offset)).fetchall()
    return [normalized(r) for r in rows]


def get_call(call_id: int, sensitive: bool = False):
    columns = PUBLIC_COLUMNS + (SENSITIVE_COLUMNS if sensitive else ())
    q = ('SELECT ' + ','.join('"' + c + '"' for c in columns) + ' FROM ' + VIEW + ' WHERE id=%s LIMIT 1')
    with connect() as c: row = c.execute(q, (call_id,)).fetchone()
    return normalized(row) if row else None


def transcript_excerpt(call_id: int, char_limit: int = 6000,
                       offset: int = 0) -> dict | None:
    """Read one numbered fragment of a call, not an artificial full-call truncation.

    The complete conversation can be fetched in authorized chunks. We never
    query the customer contact columns or change the source database.
    """
    if type(call_id) is not int or call_id <= 0:
        raise ValueError('Invalid call ID')
    if type(char_limit) is not int or not 1 <= char_limit <= 6000:
        raise ValueError('Invalid transcript length')
    if type(offset) is not int or not 0 <= offset <= 1000000:
        raise ValueError('Invalid transcript offset')
    query = ('SELECT id, SUBSTRING("transcription" FROM %s FOR %s) AS transcription, '
             'COALESCE(LENGTH("transcription"), 0) AS total_chars '
             'FROM ' + VIEW + ' WHERE id=%s LIMIT 1')
    with connect() as conn:
        row = conn.execute(query, (offset + 1, char_limit, call_id)).fetchone()
    return normalized(row) if row else None


def stats(after: date | None = None, before: date | None = None,
          created_after: datetime | None = None, created_before: datetime | None = None):
    where, params = filters(after, before, None, created_after, created_before)
    q = ('SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE "aicallinfostate" = %s) AS sold_out, '
         'ROUND(AVG("possibility_of_sale_ai")::numeric, 1) AS avg_ai_score, '
         'ROUND(AVG("voice_length")::numeric, 1) AS avg_voice_length '
         'FROM ' + VIEW + where)
    with connect() as c:
        row = c.execute(q, ('SoldOut', *params)).fetchone()
    return normalized(row)


def statuses():
    with connect() as c:
        rows = c.execute('SELECT DISTINCT "aicallinfostate" AS value FROM ' + VIEW +
                         ' WHERE "aicallinfostate" IS NOT NULL ORDER BY value LIMIT 100').fetchall()
    return [r['value'] for r in rows]


def call_types():
    """Distinct reporting values for filter controls; no sensitive text."""
    with connect() as c:
        rows = c.execute('SELECT DISTINCT "tellstate" AS value FROM ' + VIEW +
                         ' WHERE "tellstate" IS NOT NULL ORDER BY value LIMIT 100').fetchall()
    return [r['value'] for r in rows]

def health():
    with connect() as c:
        r = c.execute('SELECT current_database() db, current_user username, ssl.version AS tls '
                      'FROM pg_stat_ssl AS ssl WHERE ssl.pid=pg_backend_pid()').fetchone()
    return normalized(r) if r else {'ok': True}
