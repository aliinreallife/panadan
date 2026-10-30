"""Read-only, non-mutating audit of effective PostgreSQL reporting permissions.

Run while the local VPN relay is up. These checks inspect *effective* grants,
including privileges inherited from PUBLIC or role memberships. They do not
attempt to revoke or grant anything and do not read customer call records.

A clean result is not a substitute for a database administrator reviewing
SECURITY DEFINER functions, role memberships and the account's full access.
"""
from __future__ import annotations

import json
import sys

from . import database


CORE_SQL = """
SELECT current_user AS role,
       current_setting('transaction_read_only') = 'on' AS transaction_read_only,
       has_table_privilege(current_user, 'public.vw_danix_call_info_report', 'SELECT') AS can_select_report,
       has_table_privilege(current_user, 'public.vw_danix_call_info_report', 'INSERT') AS can_insert_report,
       has_table_privilege(current_user, 'public.vw_danix_call_info_report', 'UPDATE') AS can_update_report,
       has_table_privilege(current_user, 'public.vw_danix_call_info_report', 'DELETE') AS can_delete_report,
       has_table_privilege(current_user, 'public.vw_danix_call_info_report', 'TRUNCATE') AS can_truncate_report,
       has_database_privilege(current_database(), 'CREATE') AS can_create_database_objects,
       has_database_privilege(current_database(), 'TEMPORARY') AS can_create_temporary_objects
"""
SCHEMA_SQL = """
SELECT COUNT(*)::integer AS writable_schemas
FROM pg_catalog.pg_namespace n
WHERE n.nspname <> 'information_schema'
  AND LEFT(n.nspname, 3) <> 'pg_'
  AND has_schema_privilege(n.oid, 'CREATE')
"""
RELATION_SQL = """
SELECT COUNT(*)::integer AS writable_relations
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f')
  AND n.nspname <> 'information_schema'
  AND LEFT(n.nspname, 3) <> 'pg_'
  AND (
    has_table_privilege(c.oid, 'INSERT')
    OR has_table_privilege(c.oid, 'UPDATE')
    OR has_table_privilege(c.oid, 'DELETE')
    OR has_table_privilege(c.oid, 'TRUNCATE')
  )
"""


def inspect_permissions() -> dict:
    """All three statements are SELECT, executed in a READ ONLY transaction."""
    with database.connect() as conn:
        result = dict(conn.execute(CORE_SQL).fetchone())
        result.update(conn.execute(SCHEMA_SQL).fetchone())
        result.update(conn.execute(RELATION_SQL).fetchone())
    result["blocking"] = [
        label for label, bad in (
            ("Reporting transaction is not read-only", not result["transaction_read_only"]),
            ("Reporting view is not selectable", not result["can_select_report"]),
            ("Reporting view can be modified", any(result[k] for k in (
                "can_insert_report", "can_update_report", "can_delete_report", "can_truncate_report"
            ))),
            ("Account can create permanent database objects", result["can_create_database_objects"]),
            ("Account has CREATE on a non-system schema", result["writable_schemas"] > 0),
            ("Account has write grants on non-system relations", result["writable_relations"] > 0),
        ) if bad
    ]
    result["advisories"] = (
        ["Account can create temporary objects; ask the DBA whether this is necessary"]
        if result["can_create_temporary_objects"] else []
    )
    result["strict_report_read_only"] = not result["blocking"]
    return result


def main() -> int:
    try:
        result = inspect_permissions()
    except Exception as exc:
        # Do not print exception text: it may include connection details or SQL.
        sqlstate = getattr(exc, "sqlstate", None)
        code = f" SQLSTATE={sqlstate}" if sqlstate else ""
        print(
            f"Unable to inspect effective database permissions "
            f"({type(exc).__name__}{code}). Check the VPN, reporting view and "
            "database permissions. No credentials or queries were logged.",
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["blocking"]:
        print("FAIL: effective privileges are broader than the reporting-only policy. Ask the database administrator to review them.", file=sys.stderr)
        return 1
    print("PASS: effective permissions checked; no permanent-object writes were detected. See advisories and audit limitations.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
