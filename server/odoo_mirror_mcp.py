"""Restricted, staging-only MCP tools for Panadan-owned mirror summaries.

No source Odoo connection, raw SQL, unredacted transcripts or sensitive
MCP tool. Every *individual tool request* revalidates the MCP bearer and
fetches verified operator IDs from the active token owner.
"""
from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager

from mcp.server.mcpserver import MCPServer, Context
from mcp.types import ToolAnnotations

from . import odoo_local_reporting as local

SAFE_MCP = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, open_world_hint=False)


def _token(ctx: Context) -> str | None:
    headers = ctx.headers or {}
    authorization = headers.get("authorization", "")
    if not isinstance(authorization, str) or not authorization.startswith("Bearer "):
        return None
    raw = authorization[7:]
    if not 1 <= len(raw) <= 256 or any(ch.isspace() for ch in raw):
        return None
    return raw


def create_mirror_mcp(auth_store, *, open_reporting: Callable[[], AbstractContextManager]):
    """Build an independent MCPServer; never register tools on live /mcp."""
    mcp = MCPServer(
        "Panadan Local Mirror (isolated staging)",
        version="0.0.0-staging",
        instructions="Read-only scoped summaries from Panadan-owned PG18. No transcripts, names, phones or raw SQL.",
    )

    @mcp.tool(title="Mirror calls (authorized operators)", annotations=SAFE_MCP)
    def list_mirror_calls(ctx: Context, limit: int = 20, after_id: int = 0) -> dict:
        """Page sanitized summaries; operator IDs derive only from the caller."""
        raw = _token(ctx)
        if raw is None or type(limit) is not int or not 1 <= limit <= 100 or (
                type(after_id) is not int or not 0 <= after_id <= 999_999_999):
            return {"error": "invalid_request"}
        try:
            with open_reporting() as conn:
                items = local.list_calls_for_token(
                    conn, auth_store, token=raw, service_scope="mcp:read",
                    after_id=after_id, limit=limit)
            return {
                "items": items,
                "next_after_id": items[-1]["call_id"] if items else after_id,
            }
        except PermissionError:
            return {"error": "permission_denied"}
        except Exception:
            return {"error": "local_mirror_unavailable"}

    @mcp.tool(title="Mirror call summary", annotations=SAFE_MCP)
    def get_mirror_call_summary(call_id: int, ctx: Context) -> dict:
        """Safe current-state metadata only; no transcript or customer info."""
        raw = _token(ctx)
        if raw is None or type(call_id) is not int or not 1 <= call_id <= 999_999_999:
            return {"error": "invalid_request"}
        try:
            with open_reporting() as conn:
                item = local.get_call_for_token(
                    conn, auth_store, token=raw, service_scope="mcp:read",
                    call_id=call_id)
            return item if item is not None else {"error": "not_found"}
        except PermissionError:
            return {"error": "permission_denied"}
        except Exception:
            return {"error": "local_mirror_unavailable"}

    @mcp.tool(title="Mirror call count", annotations=SAFE_MCP)
    def count_mirror_calls(ctx: Context) -> dict:
        """Scoped call count uses the same per-principal operator grants."""
        raw = _token(ctx)
        if raw is None:
            return {"error": "invalid_request"}
        try:
            with open_reporting() as conn:
                count = local.count_calls_for_token(
                    conn, auth_store, token=raw, service_scope="mcp:read")
            return {"count": count}
        except PermissionError:
            return {"error": "permission_denied"}
        except Exception:
            return {"error": "local_mirror_unavailable"}

    return mcp
