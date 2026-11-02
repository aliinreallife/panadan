"""Staging-only authenticated MCP profile tool for PostgreSQL-backed accounts.

Never identify the caller from an MCP tool parameter or a client-supplied _meta
field. Both auth modes must validate transport credentials and check the
mapped user's current account permissions against Panadan-owned PG18.
"""
from __future__ import annotations

from typing import NotRequired, TypedDict

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations


class Profile(TypedDict):
    id: str
    name: NotRequired[str]


def resolve_profile(headers: dict[str, str], store, oauth_config, oauth_verifier) -> Profile:
    authorization = headers.get("authorization", "")
    token = authorization[7:] if authorization.startswith("Bearer ") else ""
    if not token or len(token) > 256:
        raise PermissionError("Authenticated profile unavailable")
    if oauth_config.mode == "oauth":
        subject = oauth_verifier.verify(token) if oauth_verifier is not None else None
        profile = (
            store.mcp_profile(oauth_issuer=oauth_config.issuer, oauth_subject=subject)
            if subject else None
        )
    else:
        profile = store.mcp_profile(legacy_token=token)
    if (not isinstance(profile, dict)
            or not isinstance(profile.get("id"), str)
            or not profile["id"].startswith("prf_")
            or not profile["id"].strip()):
        raise PermissionError("Authenticated profile unavailable")
    answer: Profile = {"id": profile["id"]}
    label = profile.get("name")
    if isinstance(label, str) and label.strip():
        answer["name"] = label
    return answer


def register_profile_tool(mcp: MCPServer) -> None:
    """Only called from main after the strict disposable PG staging gate."""
    @mcp.tool(
        name="get_profile",
        title="Current authenticated profile",
        description="Return this request's authenticated Panadan profile. No account selector.",
        annotations=ToolAnnotations(
            read_only_hint=True, destructive_hint=False, open_world_hint=False
        ),
        meta={"openai/profile": True},
        structured_output=True,
    )
    def get_profile(ctx: Context) -> Profile:
        from .main import store, oauth_config, oauth_verifier
        return resolve_profile(ctx.headers or {}, store, oauth_config, oauth_verifier)
