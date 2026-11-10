"""Official MCP SDK v2 protocol smoke and transport-hardening checks.

The legacy Streamable HTTP login/tool/revocation scenario is covered by
test_mcp_http_integration.py. Here we verify v2-native discovery in memory,
without a database connection, external MCP server, VPN or customer content.
"""
import asyncio

import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer

from server.mcp_tools import mcp


def test_mcp_server_is_the_new_official_sdk_class():
    assert isinstance(mcp, MCPServer)


def test_modern_mcp_protocol_tool_discovery():
    async def check():
        async with Client(mcp) as client:
            assert str(client.protocol_version) == "2026-07-28"
            result = await client.list_tools()
            tools = result.tools if hasattr(result, 'tools') else result
            names = {item.name for item in tools}
            assert names == {
                "list_recent_calls", "get_call_summary",
                "get_call_metrics", "get_available_states",
                "get_redacted_call_transcript",
                # Permission discovery returns only the caller's own policy
                # metadata. It never reads customer rows or mutates grants.
                "get_my_access", "explain_access",
            }
            by_name = {item.name: item for item in tools}
            assert {"get_my_access", "explain_access"} <= names
            for name in names - {"get_redacted_call_transcript"}:
                annotations = by_name[name].annotations
                assert annotations is not None
                assert annotations.read_only_hint is True
                assert annotations.destructive_hint is False
                assert annotations.open_world_hint is False
                assert by_name[name].title

            # Disclosure is limited and uses a read-only SOURCE connection,
            # but it also persists a local audit row for every successful read.
            transcript = by_name["get_redacted_call_transcript"]
            assert transcript.annotations is not None
            assert transcript.annotations.read_only_hint is False
            assert transcript.annotations.destructive_hint is False
            assert transcript.annotations.open_world_hint is False
            assert "audit" in transcript.title.lower()
    asyncio.run(check())


def test_local_transport_allowed_hosts_and_origins_are_explicit(monkeypatch, tmp_path):
    monkeypatch.setenv('PANADAN_AUTH_DB',str(tmp_path/'auth.sqlite'))
    from server.main import mcp_transport_settings
    monkeypatch.delenv('PANADAN_MCP_ALLOWED_HOSTS', raising=False)
    monkeypatch.delenv('PANADAN_MCP_ALLOWED_ORIGINS', raising=False)
    cfg=mcp_transport_settings()
    assert cfg.enable_dns_rebinding_protection is True
    assert 'localhost:*' in cfg.allowed_hosts
    assert '127.0.0.1:*' in cfg.allowed_hosts
    assert 'http://localhost:*' in cfg.allowed_origins


def test_public_host_and_origin_are_opt_in(monkeypatch, tmp_path):
    monkeypatch.setenv('PANADAN_AUTH_DB',str(tmp_path/'auth.sqlite'))
    from server.main import mcp_transport_settings
    monkeypatch.setenv('PANADAN_MCP_ALLOWED_HOSTS','reports.example.org:443')
    monkeypatch.setenv('PANADAN_MCP_ALLOWED_ORIGINS','https://reports.example.org')
    cfg=mcp_transport_settings()
    assert 'reports.example.org:443' in cfg.allowed_hosts
    assert 'https://reports.example.org' in cfg.allowed_origins
    monkeypatch.setenv('PANADAN_MCP_ALLOWED_HOSTS','*')
    with pytest.raises(ValueError):
        mcp_transport_settings()
    monkeypatch.setenv('PANADAN_MCP_ALLOWED_HOSTS','reports.example.org:443')
    monkeypatch.setenv('PANADAN_MCP_ALLOWED_ORIGINS','http://public.example.org')
    with pytest.raises(ValueError):
        mcp_transport_settings()
