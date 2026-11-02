"""Safe pre-migration report: can the source view support incremental sync?

Uses only fixed read-only catalog SELECTs, a bounded ID sample, and optional
EXPLAIN without ANALYZE. No customer rows, ID values, transcripts or SQL plans
are printed. Never assumes that creation dates detect edits/deletions.
"""
from __future__ import annotations

import argparse
import json
import sys
from . import database

COLUMN_SQL = """
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = %s AND table_name = %s
ORDER BY ordinal_position
"""
KIND_SQL = """
SELECT c.relkind::text AS relation_kind
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname = %s AND c.relname = %s
"""
# Materialization bounds all inspection to the newest N rows by source ID.
# These rows remain inside PostgreSQL; only aggregate values are returned.
SAMPLE_SQL = """
WITH recent AS MATERIALIZED (
    SELECT id, create_date
    FROM public.vw_danix_call_info_report
    ORDER BY id DESC
    LIMIT %s
), ordered AS (
    SELECT id, create_date,
           LAG(create_date) OVER (ORDER BY id ASC) AS previous_create
    FROM recent
)
SELECT COUNT(*) AS sampled_rows,
       COUNT(id) AS nonnull_ids,
       COUNT(DISTINCT id) AS distinct_ids,
       COUNT(create_date) AS creation_dates_present,
       COUNT(*) FILTER (WHERE create_date < previous_create)
           AS creation_order_inversions
FROM ordered
"""
# This uses the query planner ONLY, not EXPLAIN ANALYZE (no row scan).
PLAN_SQL = "EXPLAIN (FORMAT JSON) SELECT * FROM public.vw_danix_call_info_report"

# Candidate *detection* only. A field's presence never authorizes a live
# sync: write_at/write_date may reflect changes on the base call row while
# missing updates to joined tables in this reporting view.
UPDATE_CANDIDATES = (
    'sync_updated_at', 'updated_at', 'write_at', 'write_date',
    'modified_at', 'last_modified'
)
DELETE_CANDIDATES = ('deleted_at', 'is_deleted', 'deleted', 'active')
VALID_KINDS = {'v': 'view', 'm': 'materialized view', 'r': 'table',
               'p': 'partitioned table', 'f': 'foreign table'}


def inspect(*, sample: int = 100, explain: bool = True) -> dict:
    if type(sample) is not int or not 0 <= sample <= 300:
        raise ValueError('sample must be an integer between 0 and 300')
    schema, view = database.VIEW.split('.', 1)
    with database.connect() as conn:
        columns = conn.execute(COLUMN_SQL, (schema, view)).fetchall()
        kind = conn.execute(KIND_SQL, (schema, view)).fetchone()
        if not kind or not columns:
            raise RuntimeError('Reporting view metadata not readable')
        sampled = (dict(conn.execute(SAMPLE_SQL, (sample,)).fetchone())
                   if sample else None)
        estimate = None
        if explain:
            # If planning fails, report that condition rather than turn a
            # successful catalog/sample inspection into a failed command.
            try:
                raw = conn.execute(PLAN_SQL).fetchone()
                plan = raw.get('QUERY PLAN') if raw else None
                if isinstance(plan, str):
                    plan = json.loads(plan)
                node = plan[0].get('Plan') if isinstance(plan, list) and plan else None
                if isinstance(node, dict):
                    rows = node.get('Plan Rows')
                    width = node.get('Plan Width')
                    estimate = {
                        'planner_rows_estimate': rows if isinstance(rows, int) and rows >= 0 else None,
                        'planner_width_estimate_bytes': width if isinstance(width, int) and width >= 0 else None,
                    }
            except Exception:
                estimate = None

    metadata = {r['column_name']: r for r in columns}
    present = set(metadata)
    return {
        'source': database.VIEW,
        'relation_kind': VALID_KINDS.get(kind['relation_kind'], 'other'),
        'column_count': len(columns),
        'identity_candidate': 'id' if 'id' in present else None,
        'identity_column_type': metadata['id']['data_type'] if 'id' in present else None,
        'creation_marker': 'create_date' if 'create_date' in present else None,
        'update_marker_candidates': [name for name in UPDATE_CANDIDATES if name in present],
        'update_marker_details': [
            {'name': name, 'data_type': metadata[name]['data_type'],
             'nullable': metadata[name]['is_nullable'] == 'YES'}
            for name in UPDATE_CANDIDATES if name in present
        ],
        'deletion_marker_candidates': [name for name in DELETE_CANDIDATES if name in present],
        'sample': sampled,
        'plan_estimate': estimate,
        'readiness': {
            'can_page_by_id': 'candidate_only' if 'id' in present else 'missing',
            'can_detect_updates': 'unverified' if any(v in present for v in UPDATE_CANDIDATES)
                                 else 'no_visible_update_marker',
            'can_detect_deletes': 'unverified' if any(v in present for v in DELETE_CANDIDATES)
                                 else 'no_visible_deletion_marker',
        },
        'limitations': [
            'Sampled row count is not the full source row count.',
            'Planner row/width estimates are not actual counts or storage sizes.',
            'ID presence and short-sample uniqueness do not prove global unique/stable/monotonic identity.',
            'create_date does not track updates or deletion by itself.',
            'Even a visible update marker must reflect every change to the joined view row.',
            'Hard deletion cannot be inferred incrementally from a read-only view without tombstones/change feed.',
            'No source call IDs, customer names, numbers, transcripts, or individual timestamps are output.',
        ],
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sample', type=int, default=100,
                   help='0 skips row sampling; default 100; max 300')
    p.add_argument('--no-explain', action='store_true',
                   help='skip planner-only non-executing estimate')
    args = p.parse_args(argv)
    try:
        result = inspect(sample=args.sample, explain=not args.no_explain)
    except ValueError:
        print('Invalid sync audit options', file=sys.stderr)
        return 2
    except Exception as exc:
        code = getattr(exc, 'sqlstate', None)
        safe_state = code if isinstance(code, str) and len(code) == 5 and code.isalnum() else 'unknown'
        print(f'Sync-readiness audit failed: {type(exc).__name__} SQLSTATE={safe_state}',
              file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
