"""Fixed browser projections for scoped call resources and source history."""

from dataclasses import dataclass
import re
from urllib.parse import urlencode
from uuid import UUID

from .knowledge_authorization import AccessDenied


PAGES = frozenset({"resources", "resource", "integrations"})
STATES = frozenset({"active", "stale", "restricted", "deleted", "unknown"})
PAGE_SIZE = 24
_SEARCH_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


@dataclass(frozen=True, slots=True)
class ResourceFilters:
    source: UUID | None = None
    call: str = ""
    state: str = ""
    after: UUID | None = None

    @classmethod
    def parse(cls, source, call, state, after):
        call = call.strip().translate(_SEARCH_DIGITS)
        if (call and not re.fullmatch(r"[1-9][0-9]{0,18}", call)) or (state and state not in STATES):
            raise AccessDenied("Access denied")
        return cls(parse_uuid(source) if source else None, call, state, parse_uuid(after) if after else None)

    def query(self, after=None):
        values = dict(source=self.source, call=self.call, state=self.state, after=after)
        return urlencode({key: value for key, value in values.items() if value})


def parse_uuid(value):
    try:
        key = UUID(value)
    except (TypeError, ValueError, AttributeError):
        raise AccessDenied("Access denied") from None
    if not key.int:
        raise AccessDenied("Access denied")
    return key


_LIST_SOURCE = """SELECT s.id,s.label,s.state,c.rev,c.adapter_version,c.state AS contract_state
    FROM panadan_knowledge.sources s
    LEFT JOIN panadan_knowledge.source_contract_versions c
      ON c.workspace_id=s.workspace_id AND c.source_id=s.id AND c.id=s.current_contract_id
    WHERE s.workspace_id=%s AND panadan_knowledge.resource_granted(s.id,NULL,'resource.list')
    ORDER BY s.label,s.id LIMIT 100"""

_WITH_CURRENT = """FROM panadan_knowledge.resources r
    JOIN panadan_knowledge.resource_revisions v ON v.workspace_id=r.workspace_id AND v.id=r.current_revision_id
    JOIN panadan_knowledge.sources s ON s.workspace_id=r.workspace_id AND s.id=r.source_id
    WHERE r.workspace_id=%s"""
_LIST_SCOPE = """ AND panadan_knowledge.resource_granted(r.source_id,v.operator_scope_id,'resource.list')
    AND (%s::uuid IS NULL OR r.source_id=%s) AND (%s='' OR r.external_id=%s)
    AND (%s='' OR r.availability=%s)"""


def _list(view, workspace, filters):
    sources = view.execute(_LIST_SOURCE, (workspace,)).fetchall()
    if filters.source and not any(source["id"] == filters.source for source in sources):
        raise AccessDenied("Access denied")
    params = (
        workspace, filters.source, filters.source, filters.call,
        filters.call, filters.state, filters.state,
    )
    cursor_at = None
    if filters.after is not None:
        cursor = view.execute("SELECT v.event_at " + _WITH_CURRENT + _LIST_SCOPE + " AND r.id=%s",
                              (*params, filters.after)).fetchone()
        if cursor is None:
            raise AccessDenied("Access denied")
        cursor_at = cursor["event_at"]
    rows = view.execute("""SELECT r.id,r.external_id,r.availability,s.label,v.event_at,v.rev,
            panadan_knowledge.resource_granted(r.source_id,v.operator_scope_id,'resource.read') AS openable """
        + _WITH_CURRENT + _LIST_SCOPE + """
        AND (%s::timestamptz IS NULL OR (v.event_at,r.id)<(%s,%s))
        ORDER BY v.event_at DESC,r.id DESC LIMIT %s""",
        (*params, cursor_at, cursor_at, filters.after, PAGE_SIZE + 1)).fetchall()
    return {
        "sources": sources,
        "resources": rows[:PAGE_SIZE],
        "filters": filters,
        "query": filters.query(after=filters.after),
        "next_page": filters.query(after=rows[PAGE_SIZE-1]["id"]) if len(rows) > PAGE_SIZE else "",
    }


def _detail(view, workspace, resource_id, filters):
    resource = view.execute("""SELECT r.id,r.external_id,r.availability,s.label,v.id AS revision_id,
            v.event_at,v.rev,v.transcript_outcome,
            CASE WHEN r.availability='active' THEN v.normalized_metadata -> 'duration_seconds' END AS duration """
        + _WITH_CURRENT + """
        AND r.id=%s AND panadan_knowledge.resource_granted(r.source_id,v.operator_scope_id,'resource.read')""",
        (workspace, resource_id)).fetchone()
    if resource is None:
        raise AccessDenied("Access denied")
    versions = view.execute("""SELECT rev,operation,availability,observed_at FROM panadan_knowledge.resource_revisions
        WHERE workspace_id=%s AND resource_id=%s
          AND panadan_knowledge.resource_granted(source_id,operator_scope_id,'resource.read')
        ORDER BY rev DESC LIMIT 25""", (workspace, resource_id)).fetchall()
    transcript = view.execute("""SELECT text_payload,expires_at FROM panadan_knowledge.representations
        WHERE workspace_id=%s AND resource_revision_id=%s ORDER BY representation_rev DESC LIMIT 1""",
        (workspace, resource["revision_id"])).fetchone()
    return {"resource": resource, "versions": versions, "transcript": transcript, "query": filters.query(after=filters.after)}


def _integrations(view, workspace):
    sources = view.execute(_LIST_SOURCE, (workspace,)).fetchall()
    scopes = view.execute("""SELECT s.label AS source_label, coalesce(o.label,o.external_operator_key) AS operator_label,
        c.event_start,c.event_end,c.finished,r.state,r.examined,r.accepted,r.unchanged,r.excluded,r.reason_code,r.created_at
        FROM panadan_knowledge.sync_checkpoints c JOIN panadan_knowledge.sources s
          ON s.workspace_id=c.workspace_id AND s.id=c.source_id
        JOIN panadan_knowledge.operator_scopes o ON o.workspace_id=c.workspace_id AND o.id=c.operator_scope_id
        LEFT JOIN LATERAL (
          SELECT state,examined,accepted,unchanged,excluded,reason_code,created_at
          FROM panadan_knowledge.sync_runs r WHERE r.workspace_id=c.workspace_id AND r.checkpoint_id=c.id
          ORDER BY r.created_at DESC LIMIT 1
        ) r ON true
        WHERE c.workspace_id=%s AND panadan_knowledge.resource_granted(c.source_id,c.operator_scope_id,'resource.list')
        ORDER BY r.created_at DESC NULLS LAST,c.event_end DESC,c.id LIMIT 24""", (workspace,)).fetchall()
    return {"sources": sources, "sync_scopes": scopes}


def resource_view(view, workspace, page, resource_id, filters):
    if page == "resources":
        return _list(view, workspace, filters)
    if page == "resource":
        return _detail(view, workspace, resource_id, filters)
    if page == "integrations":
        return _integrations(view, workspace)
    raise AccessDenied("Access denied")
