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
from server.main import mcp_transport_settings


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
            }
    asyncio.run(check())


def test_local_transport_allowed_hosts_and_origins_are_explicit(monkeypatch):
    monkeypatch.delenv('PANADAN_MCP_ALLOWED_HOSTS', raising=False)
    monkeypatch.delenv('PANADAN_MCP_ALLOWED_ORIGINS', raising=False)
    cfg=mcp_transport_settings()
    assert cfg.enable_dns_rebinding_protection is True
    assert 'localhost:*' in cfg.allowed_hosts
    assert '127.0.0.1:*' in cfg.allowed_hosts
    assert 'http://localhost:*' in cfg.allowed_origins


def test_public_host_and_origin_are_opt_in(monkeypatch):
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
