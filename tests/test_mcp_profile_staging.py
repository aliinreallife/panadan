"""No-network MCP profile identity tests; never use production auth."""
from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from mcp.server.mcpserver import MCPServer

from server.mcp_profile_staging import resolve_profile, register_profile_tool


@dataclass
class StoreSpy:
    data: dict

    def mcp_profile(self, **kwargs):
        self.last_lookup = kwargs
        return self.data.get(kwargs.get("legacy_token") or kwargs.get("oauth_subject"))


class Verifier:
    def verify(self, token):
        return {"valid-oauth": "subject-1", "revoked-oauth": None}.get(token)


def test_register_profile_is_read_only_and_marked_for_openai():
    srv = MCPServer("Synthetic isolated Panadan")
    register_profile_tool(srv)
    item = {t.name: t for t in srv._tool_manager.list_tools()}["get_profile"]
    assert item.meta == {"openai/profile": True}
    assert item.annotations.read_only_hint is True
    assert item.annotations.destructive_hint is False
    assert item.annotations.open_world_hint is False
    schema = item.fn_metadata.output_schema
    assert schema is not None
    assert "id" in schema.get("properties", {})
    assert "id" in schema.get("required", [])
    assert item.fn_metadata.arg_model.model_json_schema()["properties"] == {}


def test_legacy_profile_rebind_and_revocation():
    first = {"id": "prf_AAAA1234", "name": "Synthetic Admin"}
    second = {"id": "prf_BBBB5678", "name": "Synthetic Analyst"}
    db = StoreSpy({"token-a": first, "token-b": second})
    conf = SimpleNamespace(mode="legacy", issuer="")
    a = resolve_profile({"authorization": "Bearer token-a"}, db, conf, None)
    assert a == first
    assert resolve_profile({"authorization": "Bearer token-b"}, db, conf, None) == second
    assert a["id"] != second["id"]
    assert resolve_profile({"authorization": "Bearer token-a"}, db, conf, None)["id"] == a["id"]
    assert db.last_lookup == {"legacy_token": "token-a"}
    del db.data["token-a"]
    with pytest.raises(PermissionError):
        resolve_profile({"authorization": "Bearer token-a"}, db, conf, None)


def test_oauth_profile_is_bound_to_verified_subject():
    db = StoreSpy({"subject-1": {"id": "prf_Stable1"}})
    conf = SimpleNamespace(mode="oauth", issuer="https://idp.example.test")
    actual = resolve_profile({"authorization": "Bearer valid-oauth"}, db, conf, Verifier())
    assert actual == {"id": "prf_Stable1"}
    assert db.last_lookup == {
        "oauth_issuer": "https://idp.example.test",
        "oauth_subject": "subject-1",
    }
    with pytest.raises(PermissionError):
        resolve_profile({"authorization": "Bearer revoked-oauth"}, db, conf, Verifier())


@pytest.mark.parametrize("headers,profile", [
    ({}, None),
    ({"authorization": "Basic token-a"}, None),
    ({"authorization": "Bearer "}, None),
    ({"authorization": "Bearer token-a"}, {"id": "admin"}),
    ({"authorization": "Bearer token-a"}, {"id": ""}),
    ({"authorization": "Bearer token-a"}, {"id": None}),
    ({"authorization": "Bearer token-a"}, {"email": "wrong@example.test"}),
])
def test_missing_invalid_or_unverified_identity_never_returns_placeholder(headers,profile):
    db = StoreSpy({"token-a": profile})
    with pytest.raises(PermissionError):
        resolve_profile(headers, db, SimpleNamespace(mode="legacy", issuer=""), None)


def test_profile_drops_unneeded_contact_and_token_data():
    db = StoreSpy({
        "token-a": {
            "id": "prf_Synthetic1",
            "name": "Visible Name",
            "email": "private@example.test",
            "access_token": "secret",
            "role": "admin",
        }
    })
    result = resolve_profile({"authorization": "Bearer token-a"}, db,
                             SimpleNamespace(mode="legacy", issuer=""), None)
    assert result == {"id": "prf_Synthetic1", "name": "Visible Name"}
