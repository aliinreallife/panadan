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
OPERATOR_COLUMN = 'vw_danix_base_info_users_name'
UNSPECIFIED = '__unspecified__'
PUBLIC_COLUMNS = (
    'id', 'CALLDATE', 'tellstate', 'tellside', 'aicallinfostate',
    'voice_length', 'possibility_of_sale_ai', 'deal_value',
    'vw_danix_base_info_users_name',
)
# Detail-only metadata; do not expand list/stats or sensitive source fields.
# Observed clock correlation strongly suggests seconds after Tehran midnight;
# Event meaning (started/answered/ended) is not yet verified upstream.
DETAIL_COLUMNS = ('call_time',)
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


def _operator_match(names: list[str], args: list):
    """Return fixed, parameterized predicate for locally assigned operators."""
    names = list(dict.fromkeys(names))
    included = [n for n in names if n != UNSPECIFIED]
    missing = UNSPECIFIED in names
    column = '"' + OPERATOR_COLUMN + '"'
    empty = f'({column} IS NULL OR BTRIM({column}) = \'\')'
    if included and missing:
        args.append(included)
        return f'({column} = ANY(%s) OR {empty})'
    if included:
        args.append(included)
        return f'{column} = ANY(%s)'
    if missing:
        return empty
    return 'FALSE'


def filters(after: date | None, before: date | None, state: str | None,
            created_after: datetime | None = None, created_before: datetime | None = None,
            call_type: str | None = None, operator: str | None = None,
            operator_names: list[str] | None = None, *,
            direction: str | None = None, filter_mode: str = 'all',
            any_operator_groups: list[list[str]] | None = None,
            selected_facets: dict[str, list[str]] | None = None):
    """Date range always AND; selected categorical filters can use AND or OR.

    Directory assignments are report facets, not row-level authorization.
    This function must never be reused to implement security policy.
    """
    if filter_mode not in ('all', 'any'):
        raise ValueError('Invalid filter mode')
    date_parts, date_args, selections, select_args = [], [], [], []
    if after:
        date_parts.append('"CALLDATE" >= %s')
        date_args.append(after)
    if before:
        date_parts.append('"CALLDATE" <= %s')
        date_args.append(before)

    # Odoo create_date is strongly inferred to be UTC-naive.
    # This optional legacy API filter stays supported, but is removed from UI.
    from datetime import timezone
    for op, value in [('>=', created_after), ('<=', created_before)]:
        if value:
            if value.tzinfo is None:
                value = value.replace(tzinfo=ZoneInfo('Asia/Tehran'))
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
            date_parts.append(f'"create_date" {op} %s')
            date_args.append(value)

    for column, value in [('aicallinfostate', state),
                          ('tellstate', call_type), ('tellside', direction)]:
        if value:
            # tellside may be a numeric enum; the UI sends string option values.
            # Compare its textual representation without guessing enum mappings.
            selections.append(f'"{column}"::text = %s' if column == 'tellside'
                              else f'"{column}" = %s')
            select_args.append(value)

    if selected_facets is not None and operator:
        # Fixed context (operator profile), never widened by OR report choices.
        if operator == UNSPECIFIED:
            date_parts.append(_operator_match([UNSPECIFIED], date_args))
        else:
            date_parts.append('"' + OPERATOR_COLUMN + '" = %s')
            date_args.append(operator)
    elif operator == UNSPECIFIED:
        selections.append(_operator_match([UNSPECIFIED], select_args))
    elif operator:
        selections.append('"' + OPERATOR_COLUMN + '" = %s')
        select_args.append(operator)

    if operator_names is not None:
        selections.append(_operator_match(operator_names, select_args))
    if any_operator_groups is not None:
        for group in any_operator_groups:
            selections.append(_operator_match(group, select_args))

    # Dashboard multi-select: values within each dimension are OR, and
    # selected dimensions are OR together. Fixed legacy 'operator' stays AND
    # when an explicit multi-select query is used (operator profile context).
    if selected_facets is not None:
        allowed = {
            'operators': OPERATOR_COLUMN, 'states': 'aicallinfostate',
            'call_types': 'tellstate', 'directions': 'tellside',
        }
        if set(selected_facets) - set(allowed):
            raise ValueError('Unknown report filter')
        for key, values in selected_facets.items():
            if not isinstance(values, list) or len(values) > 20 or any(
                not isinstance(v, str) or not v or len(v) > (180 if key == 'operators' else 60)
                for v in values
            ):
                raise ValueError('Invalid report filter values')
            if not values:
                continue
            if key == 'operators':
                selections.append(_operator_match(values, select_args))
            else:
                column = allowed[key]
                predicate = f'"{column}"::text = ANY(%s)' if key == 'directions' else f'"{column}" = ANY(%s)'
                selections.append(predicate)
                select_args.append(list(dict.fromkeys(values)))
        filter_mode = 'any'

    if selections:
        separator = ' OR ' if filter_mode == 'any' else ' AND '
        date_parts.append('(' + separator.join(selections) + ')')
    return (' WHERE ' + ' AND '.join(date_parts)) if date_parts else '', date_args + select_args


def list_calls(limit: int = 20, offset: int = 0, after: date | None = None,
               before: date | None = None, state: str | None = None,
               created_after: datetime | None = None, created_before: datetime | None = None,
               call_type: str | None = None, operator: str | None = None,
               operator_names: list[str] | None = None, *,
               direction: str | None = None, filter_mode: str = 'all',
               any_operator_groups: list[list[str]] | None = None,
               selected_facets: dict[str, list[str]] | None = None):
    limit = max(1, min(int(limit), 100))
    offset = max(0, min(int(offset), 10000))
    if after and before and after > before: raise ValueError('Invalid date range')
    if state and len(state) > 60: raise ValueError('Invalid state')
    if call_type and len(call_type) > 60: raise ValueError('Invalid call type')
    if direction and len(direction) > 60: raise ValueError('Invalid direction')
    if operator and len(operator) > 180: raise ValueError('Invalid operator')
    if created_after and created_before and created_after > created_before: raise ValueError('Invalid time range')
    where, params = filters(after, before, state, created_after, created_before, call_type, operator, operator_names,
                            direction=direction, filter_mode=filter_mode, any_operator_groups=any_operator_groups,
                            selected_facets=selected_facets)
    q = ('SELECT ' + ','.join('"' + c + '"' for c in PUBLIC_COLUMNS) +
         ' FROM ' + VIEW + where + ' ORDER BY "CALLDATE" DESC NULLS LAST, id DESC LIMIT %s OFFSET %s')
    with connect() as c:
        rows = c.execute(q, (*params, limit, offset)).fetchall()
    return [normalized(r) for r in rows]


def get_call(call_id: int, sensitive: bool = False):
    columns = PUBLIC_COLUMNS + DETAIL_COLUMNS + (SENSITIVE_COLUMNS if sensitive else ())
    q = ('SELECT ' + ','.join('"' + c + '"' for c in columns) + ' FROM ' + VIEW + ' WHERE id=%s LIMIT 1')
    with connect() as c: row = c.execute(q, (call_id,)).fetchone()
    return normalized(row) if row else None


# Only a small read-only context window is added for redaction across page edges.
# If a phone number or email straddles a boundary, both halves are masked.
TRANSCRIPT_REDACTION_OVERLAP = 512


def transcript_excerpt(call_id: int, char_limit: int = 6000,
                       offset: int = 0) -> dict | None:
    """Fetch transcript with small overlapping context, never customer columns.

    The response formatter must strip the overlap *after* recognizing sensitive
    tokens. The SQL still only reads a fixed, parameterized view and returns
    at most char_limit + 2*overlap characters. Pagination has no total cap.
    """
    if type(call_id) is not int or call_id <= 0:
        raise ValueError('Invalid call ID')
    if type(char_limit) is not int or not 1 <= char_limit <= 6000:
        raise ValueError('Invalid transcript length')
    if type(offset) is not int or not 0 <= offset <= 2147483646:
        raise ValueError('Invalid transcript offset')
    window_start = max(0, offset - TRANSCRIPT_REDACTION_OVERLAP)
    before = offset - window_start
    query = ('SELECT id, SUBSTRING("transcription" FROM %s FOR %s) AS transcription, '
             'COALESCE(LENGTH("transcription"), 0) AS total_chars '
             'FROM ' + VIEW + ' WHERE id=%s LIMIT 1')
    with connect() as conn:
        row = conn.execute(query, (window_start + 1,
                                   char_limit + before + TRANSCRIPT_REDACTION_OVERLAP,
                                   call_id)).fetchone()
    if not row:
        return None
    result = normalized(row)
    result['_window_start'] = window_start
    return result


def stats(after: date | None = None, before: date | None = None,
          created_after: datetime | None = None, created_before: datetime | None = None,
          operator: str | None = None, operator_names: list[str] | None = None,
          *, state: str | None = None, call_type: str | None = None,
          direction: str | None = None, filter_mode: str = 'all',
          any_operator_groups: list[list[str]] | None = None,
          selected_facets: dict[str, list[str]] | None = None):
    where, params = filters(after, before, state, created_after, created_before,
                            call_type=call_type, operator=operator, operator_names=operator_names,
                            direction=direction, filter_mode=filter_mode,
                            any_operator_groups=any_operator_groups,
                            selected_facets=selected_facets)
    q = ('SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE "aicallinfostate" = %s) AS sold_out, '
         'COUNT("possibility_of_sale_ai") AS scored_calls, '
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


def directions():
    """Distinct source direction codes. Meaning not yet upstream-verified."""
    with connect() as c:
        rows = c.execute('SELECT DISTINCT "tellside" AS value FROM ' + VIEW +
                         ' WHERE "tellside" IS NOT NULL ORDER BY value LIMIT 100').fetchall()
    return [r['value'] for r in rows]


def call_types():
    """Distinct reporting values for filter controls; no sensitive text."""
    with connect() as c:
        rows = c.execute('SELECT DISTINCT "tellstate" AS value FROM ' + VIEW +
                         ' WHERE "tellstate" IS NOT NULL ORDER BY value LIMIT 100').fetchall()
    return [r['value'] for r in rows]

def operators():
    """Read distinct operator names. Missing values are represented explicitly."""
    with connect() as c:
        rows = c.execute('SELECT DISTINCT "' + OPERATOR_COLUMN +
                         '" AS value FROM ' + VIEW +
                         ' ORDER BY value NULLS FIRST LIMIT 1000').fetchall()
    result = sorted({str(r['value']).strip() for r in rows
                     if r['value'] is not None and str(r['value']).strip()})
    if any(r['value'] is None or not str(r['value']).strip() for r in rows):
        return [UNSPECIFIED, *result]
    return result


def health():
    with connect() as c:
        r = c.execute('SELECT current_database() db, current_user username, ssl.version AS tls '
                      'FROM pg_stat_ssl AS ssl WHERE ssl.pid=pg_backend_pid()').fetchone()
    return normalized(r) if r else {'ok': True}
