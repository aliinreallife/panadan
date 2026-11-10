"""Read-only preflight for the isolated real-data Odoo mirror staging pilot.

This command does not copy source rows, create a source, enable ingestion,
grant operators, alter DB schema, issue tokens or change a checkpoint.
It requires the explicit isolated staging writer selector; do not run it
in the production web namespace or against a forwarded production DB port.
"""
from __future__ import annotations

import sys

from . import database as odoo
from . import odoo_full_mirror_adapter as full
from . import odoo_full_mirror_pilot as pilot
from . import odoo_mirror_target as target


def preflight() -> dict:
    # Enforce isolated-staging target selection before contacting anything.
    target.validate_staging_writer_config()
    with target.owned_connection() as owned:
        permissions = owned.execute(
            """SELECT
                 has_database_privilege(current_user, current_database(), 'CREATE')
                     AS can_create_db,
                 has_schema_privilege(current_user,'panadan_ingest','CREATE')
                     AS can_create_schema_objects,
                 has_table_privilege(current_user,'panadan_ingest.sources','UPDATE')
                     AS can_enable_sources"""
        ).fetchone()
        if (not permissions or permissions["can_create_db"]
                or permissions["can_create_schema_objects"]
                or permissions["can_enable_sources"]):
            raise PermissionError("Staging ingest writer has excess privileges")
        status = pilot.local_status(owned)

    # The source is opened through the existing READ ONLY transaction, not
    # through the staging/owned PG18 writer credentials. No source rows read.
    with odoo.connect() as source:
        identity = source.execute(
            "SELECT current_database() AS db, current_user AS role, "
            "current_setting('transaction_read_only') AS read_only"
        ).fetchone()
        if (not identity or identity["db"] != "odoo"
                or identity["role"] != "report_user"
                or identity["read_only"] != "on"):
            raise PermissionError("Source is not the approved read-only Odoo account")
        full.validate_schema(source)

    return {
        "isolated_staging_writer": True,
        "target_db": "panadan_ci",
        "target_pg_major": 18,
        "writer_least_privilege": True,
        "odoo_report_only": True,
        "fixed_source_fields": len(full.COLUMN_NAMES),
        "mirror_registered": status["source_registered"],
        "mirror_enabled": status["source_enabled"],
        "staging_records": status["local_records"],
        "staging_revisions": status["local_revisions"],
        "ready_for_reviewed_setup": True,
        "source_modified": False,
        "target_modified": False,
    }


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv:
        print("STAGING PREFLIGHT FAILED: unexpected arguments", file=sys.stderr)
        return 2
    try:
        print("STAGING PREFLIGHT:", preflight())
        return 0
    except Exception as exc:
        # Never print hostnames, DSNs, SQL or source/customer details.
        print(f"STAGING PREFLIGHT FAILED: {type(exc).__name__}",
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
