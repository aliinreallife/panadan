"""MCP tools are deliberately restricted to safe, non-transcript fields."""
from datetime import date
from mcp.server.fastmcp import FastMCP
from . import database

mcp = FastMCP('Panadan', instructions='Read-only reporting for authorized business users. No raw SQL or private transcripts.', stateless_http=True, json_response=True, streamable_http_path='/')


@mcp.tool()
def list_recent_calls(limit: int = 10, offset: int = 0, after: str = '', before: str = '', state: str = '') -> list[dict]:
    """List summary metadata for calls; no customer phone numbers or transcripts."""
    return database.list_calls(limit, offset, date.fromisoformat(after) if after else None,
                               date.fromisoformat(before) if before else None, state or None)


@mcp.tool()
def get_call_summary(call_id: int) -> dict:
    """Fetch non-sensitive reporting fields for one call ID."""
    return database.get_call(call_id, sensitive=False) or {'error': 'not_found'}


@mcp.tool()
def get_call_metrics(after: str = '', before: str = '') -> dict:
    """Aggregate counts, reported SoldOut states and averages for a date range."""
    return database.stats(date.fromisoformat(after) if after else None,
                          date.fromisoformat(before) if before else None)


@mcp.tool()
def get_available_states() -> list[str]:
    """List available AI call status labels."""
    return database.statuses()
