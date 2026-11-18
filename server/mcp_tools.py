"""Panadan read-only MCP tools with request-time user AND app authorization.

Every data-bearing tool verifies the credential, resolves its actual owner,
checks current capabilities and applies column-level projection. The AI
cannot supply another user's ID or claim additional permissions.
"""
from datetime import date, timedelta

from mcp.server.mcpserver import MCPServer, Context
from mcp.types import ToolAnnotations

from . import database
from .mcp_inputs import MCPInputError, date_window, page, optional_text, compare_values
from .field_permissions import (
    REPORT_FIELDS, REPORT_DESCRIPTIONS, explain_field, project_call,
    project_metrics, permitted_fields_for_capability,
)

mcp = MCPServer(
    "Panadan", version="0.8.0",
    instructions="First call get_my_access to learn effective permissions and suggested tools. "
                 "Use list_recent_calls for call listings, get_call_metrics for totals, "
                 "get_daily_call_counts for a bounded daily trend, and "
                 "compare_call_metrics for equal-length period comparisons. "
                 "For unavailable fields use explain_access; never invent values, "
                 "assume operator filters are tenant authorization, request secrets, "
                 "or attempt SQL writes. A human administrator grants access.",
)

REPORT_READ_ONLY = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, open_world_hint=False)
AUDITED_DISCLOSURE = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, open_world_hint=False)


def _access(ctx: Context) -> dict | None:
    # The HTTP gate verifies bearer tokens before any MCP handler. Recheck
    # them here as well: tests and future transports must not bypass auth.
    from .main import store, oauth_config, oauth_verifier
    auth = (ctx.headers or {}).get("authorization", "")
    raw = auth[7:] if auth.startswith("Bearer ") else ""
    if not raw:
        return None
    if oauth_config.mode == "oauth":
        details = oauth_verifier.verify_details(raw) if oauth_verifier else None
        if not details:
            return None
        actor = store.actor_for_oauth(oauth_config.issuer, details["subject"])
        if actor is None or not hasattr(store, "mcp_access"):
            return None
        return store.mcp_access(actor, oauth_client=details.get("client_id"))
    actor = store.actor_for_token(raw, "mcp:read")
    if actor is None or not hasattr(store, "mcp_access"):
        return None
    return store.mcp_access(actor, legacy_token=raw)


def _allowed(ctx: Context, capability: str, field: str | None = None):
    access = _access(ctx)
    if not access or capability not in access["capabilities"]:
        return None
    if field and field not in access["fields"]:
        return None
    return access


def _filters_permitted(access: dict, *, after="", before="", state="",
                       operator="", destination="", team="") -> bool:
    allowed = access["fields"]
    return not (
        ((after or before) and "CALLDATE" not in allowed)
        or (state and "aicallinfostate" not in allowed)
        or ((operator or destination or team)
            and "vw_danix_base_info_users_name" not in allowed)
    )


@mcp.tool(title="My Panadan access", annotations=REPORT_READ_ONLY)
def get_my_access(ctx: Context) -> dict:
    """Explain the fields and capabilities delegated to THIS authenticated AI."""
    access = _access(ctx)
    if access is None:
        return {"error": "permission_denied"}
    return {
        "schema_version": 1,
        "actor": "self",
        "capabilities": sorted(access["capabilities"] & {
            "calls:read", "metrics:read", "calls:transcript:read", "mcp:use"}),
        "columns": [
            {"id": key, "label": REPORT_DESCRIPTIONS[key][0]}
            for key in REPORT_FIELDS if key in access["fields"]
        ],
        "note": "This is this AI's effective access, not every permission owned by the user.",
        "can_request_more_access": True,
        "my_consent_page": "/dashboard/mcp-apps",
        "suggested_tools": sorted(
            ({"list_recent_calls", "get_call_summary"}
             if "calls:read" in access["capabilities"] else set())
            | ({"get_call_metrics"}
               if "metrics:read" in access["capabilities"] else set())
            | ({"compare_call_metrics"}
               if "metrics:read" in access["capabilities"]
               and "CALLDATE" in access["fields"] else set())
            | ({"get_daily_call_counts"}
               if "metrics:read" in access["capabilities"]
               and {"id", "CALLDATE"} <= access["fields"] else set())
            | ({"get_available_states"}
               if "aicallinfostate" in access["fields"]
               and {"calls:read", "metrics:read"} & access["capabilities"] else set())
            | ({"get_redacted_call_transcript"}
               if {"calls:transcript:read", "calls:read"} <= access["capabilities"]
               and {"transcription", "id"} <= access["fields"] else set())
        ),
    }


@mcp.tool(title="Explain missing permission", annotations=REPORT_READ_ONLY)
def explain_access(field: str, ctx: Context) -> dict:
    """Check one fixed, known source field; never query a target person's record."""
    access = _access(ctx)
    if access is None:
        return {"error": "permission_denied"}
    # Do not expose the user's confidential grant list before the app has
    # been approved; unconsented OAuth clients receive a generic reason.
    if not access["approved_capabilities"]:
        return {"field": field if field in REPORT_DESCRIPTIONS else None,
                "allowed": False, "reason": "needs_user_consent"}
    result = explain_field(
        field, access["user_fields"], access["approved_fields"], access["fields"])
    next_step = {
        "needs_admin_grant": "Ask the Panadan administrator to grant this field.",
        "needs_user_consent": "Open Panadan and authorize this field for the AI application.",
        "not_exposable": "This field cannot be exposed by the current server policy.",
        "unknown_or_unavailable": "This field is not available in this reporting version.",
        "allowed": "This field is available to the connected application.",
    }
    result["next_step"] = next_step[result["reason"]]
    if result["reason"] == "needs_user_consent":
        result["my_consent_page"] = "/dashboard/mcp-apps"
    return result


@mcp.tool(title="Recent calls", annotations=REPORT_READ_ONLY)
def list_recent_calls(ctx: Context, limit: int = 10, offset: int = 0,
                      after: str = "", before: str = "", state: str = "",
                      operator: str = "", destination: str = "", team: str = ""):
    """List only fields the current user explicitly delegated to this AI."""
    access = _allowed(ctx, "calls:read")
    if access is None:
        return {"error": "permission_denied", "capability": "calls:read"}
    if not _filters_permitted(access, after=after, before=before, state=state,
                              operator=operator, destination=destination, team=team):
        return {"error": "permission_denied", "reason": "filter_field_restricted"}
    try:
        limit, offset = page(limit, offset)
        after_date, before_date = date_window(after, before)
        state = optional_text(state, "state", max_length=60)
        operator = optional_text(operator, "operator", max_length=180)
        destination = optional_text(destination, "destination", max_length=180)
        team = optional_text(team, "team", max_length=180)
    except MCPInputError as exc:
        return exc.response()
    from .main import directory_operator_names
    names = directory_operator_names(destination or None, team or None)
    rows = database.list_calls(
        limit, offset, after_date, before_date,
        state or None, operator=operator or None, operator_names=names,
        sort_by_date='CALLDATE' in access['fields'],
        sort_by_id='id' in access['fields'])
    visible = permitted_fields_for_capability(access["fields"], "calls:read")
    return [project_call(row, visible) for row in rows]


@mcp.tool(title="Call summary", annotations=REPORT_READ_ONLY)
def get_call_summary(call_id: int, ctx: Context) -> dict:
    """A call's non-sensitive fields, further limited to delegated columns."""
    access = _allowed(ctx, "calls:read", "id")
    if access is None:
        return {"error": "permission_denied", "capability": "calls:read", "field": "id"}
    if type(call_id) is not int or not 1 <= call_id <= 9223372036854775807:
        return {"error": "invalid_argument", "field": "call_id",
                "hint": "Choose a positive integer call ID."}
    row = database.get_call(call_id, sensitive=False)
    if not row:
        return {"error": "not_found"}
    visible = permitted_fields_for_capability(access["fields"], "calls:read")
    return project_call(row, visible)


@mcp.tool(title="Call metrics", annotations=REPORT_READ_ONLY)
def get_call_metrics(ctx: Context, after: str = "", before: str = "",
                     operator: str = "", destination: str = "", team: str = "") -> dict:
    """Return only aggregate outputs whose source fields are delegated."""
    access = _allowed(ctx, "metrics:read")
    if access is None:
        return {"error": "permission_denied", "capability": "metrics:read"}
    if not _filters_permitted(access, after=after, before=before,
                              operator=operator, destination=destination, team=team):
        return {"error": "permission_denied", "reason": "filter_field_restricted"}
    try:
        after_date, before_date = date_window(after, before)
        operator = optional_text(operator, "operator", max_length=180)
        destination = optional_text(destination, "destination", max_length=180)
        team = optional_text(team, "team", max_length=180)
    except MCPInputError as exc:
        return exc.response()
    from .main import directory_operator_names
    row = database.stats(
        after_date, before_date,
        operator=operator or None,
        operator_names=directory_operator_names(destination or None, team or None))
    return project_metrics(row, access["fields"])


@mcp.tool(title="Compare call metrics across two periods", annotations=REPORT_READ_ONLY)
def compare_call_metrics(previous_after: str, previous_before: str,
                         current_after: str, current_before: str,
                         ctx: Context, operator: str = "",
                         destination: str = "", team: str = "") -> dict:
    """Compare equal-length date ranges (YYYY-MM-DD, inclusive). Requires metrics:read
    and delegated CALLDATE for date filtering. Returns only permitted metrics,
    signed absolute differences and percentages (null if previous is zero).
    Each period must be 1-366 days. No operator/tenant access is inferred."""
    access = _allowed(ctx, "metrics:read")
    if access is None:
        return {"error": "permission_denied", "capability": "metrics:read"}
    if "CALLDATE" not in access["fields"]:
        return {"error": "permission_denied", "reason": "filter_field_restricted"}
    if not _filters_permitted(access, operator=operator, destination=destination, team=team):
        return {"error": "permission_denied", "reason": "filter_field_restricted"}
    try:
        previous_start, previous_end = date_window(previous_after, previous_before,
                                                    required=True, max_days=366)
        current_start, current_end = date_window(current_after, current_before,
                                                 required=True, max_days=366)
        operator = optional_text(operator, "operator", max_length=180)
        destination = optional_text(destination, "destination", max_length=180)
        team = optional_text(team, "team", max_length=180)
        if (previous_end - previous_start).days != (current_end - current_start).days:
            raise MCPInputError("periods", "Compare ranges of equal calendar-day length.")
    except MCPInputError as exc:
        return exc.response()

    from .main import directory_operator_names
    names = directory_operator_names(destination or None, team or None)
    def snapshot(first, last):
        row = database.stats(first, last, operator=operator or None, operator_names=names)
        return project_metrics(row, access["fields"])

    previous = snapshot(previous_start, previous_end)
    current = snapshot(current_start, current_end)
    return {
        "schema_version": 1,
        "periods": {
            "previous": {"after": previous_after, "before": previous_before},
            "current": {"after": current_after, "before": current_before},
        },
        "previous": previous,
        "current": current,
        "change": compare_values(previous, current),
        "note": "Only delegated metrics are compared; null percentages mean no nonzero baseline.",
    }


@mcp.tool(title="Daily call counts (up to 31 days)", annotations=REPORT_READ_ONLY)
def get_daily_call_counts(after: str, before: str, ctx: Context,
                          operator: str = "", destination: str = "",
                          team: str = "") -> dict:
    """Time series of total calls by source CALLDATE (YYYY-MM-DD inclusive).
    Requires metrics:read plus both id and CALLDATE field grants. Maximum
    31 days, with zeros for dates that have no matching rows. Operator/team
    filters require their delegated operator field and are NOT tenant security."""
    access = _allowed(ctx, "metrics:read")
    if access is None:
        return {"error": "permission_denied", "capability": "metrics:read"}
    if not {"id", "CALLDATE"} <= access["fields"]:
        return {"error": "permission_denied", "reason": "metric_field_restricted",
                "required_fields": ["id", "CALLDATE"]}
    if not _filters_permitted(access, operator=operator, destination=destination, team=team):
        return {"error": "permission_denied", "reason": "filter_field_restricted"}
    try:
        first, last = date_window(after, before, required=True, max_days=31)
        operator = optional_text(operator, "operator", max_length=180)
        destination = optional_text(destination, "destination", max_length=180)
        team = optional_text(team, "team", max_length=180)
    except MCPInputError as exc:
        return exc.response()

    from .main import directory_operator_names
    rows = database.daily_call_counts(
        first, last, operator=operator or None,
        operator_names=directory_operator_names(destination or None, team or None))
    counts = {row["day"]: int(row["total"]) for row in rows}
    days = (last - first).days + 1
    return {
        "schema_version": 1,
        "after": after, "before": before,
        "total": sum(counts.values()),
        "days": [
            {"date": (first + timedelta(days=i)).isoformat(),
             "total": counts.get((first + timedelta(days=i)).isoformat(), 0)}
            for i in range(days)
        ],
        "note": "Source CALLDATE day buckets. Only aggregate counts, no individual calls.",
    }


@mcp.tool(title="Available call states", annotations=REPORT_READ_ONLY)
def get_available_states(ctx: Context):
    """Enumerate status categories only when delegated the status field."""
    access = _access(ctx)
    if (not access or "aicallinfostate" not in access["fields"]
            or not ({"calls:read", "metrics:read"} & access["capabilities"])):
        return {"error": "permission_denied", "field": "aicallinfostate"}
    return database.statuses()


@mcp.tool(title="Redacted transcript (audited)", annotations=AUDITED_DISCLOSURE)
def get_redacted_call_transcript(call_id: int, ctx: Context, offset: int = 0) -> dict:
    """Read redacted transcript pages only with an explicitly delegated grant."""
    if type(call_id) is not int or call_id < 1 or type(offset) is not int or not 0 <= offset <= 2147483646:
        return {"error": "invalid_call_id"}
    access = _allowed(ctx, "calls:transcript:read", "transcription")
    if access is None or "calls:read" not in access["capabilities"] or "id" not in access["fields"]:
        return {"error": "permission_denied"}

    from .main import store, oauth_config, oauth_verifier
    from .transcript_ai import transcript_for_ai, MAX_TRANSCRIPT_CHARS
    auth = (ctx.headers or {}).get("authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else ""
    if oauth_config.mode == "oauth":
        details = oauth_verifier.verify_details(token) if oauth_verifier else None
        actor = store.authorized_transcript_actor(
            oauth_issuer=oauth_config.issuer,
            oauth_subject=details["subject"] if details else None
        ) if details else None
    else:
        actor = store.authorized_transcript_actor(legacy_token=token)
    if actor is None or not store.audit_transcript_request(
        user_id=actor, surface="mcp", call_id=call_id,
        char_limit=MAX_TRANSCRIPT_CHARS
    ):
        return {"error": "permission_denied"}
    row = database.transcript_excerpt(call_id, MAX_TRANSCRIPT_CHARS, offset)
    return transcript_for_ai(row, offset=offset) or {"error": "not_found"}
