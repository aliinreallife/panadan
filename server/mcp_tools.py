"""MCP tools are deliberately restricted to safe, non-transcript fields."""
from datetime import date
from mcp.server.fastmcp import FastMCP, Context
from . import database

mcp = FastMCP('Panadan', instructions='Read-only reporting for authorized business users. Transcript excerpts require separate user permissions. No raw SQL or writes.', stateless_http=True, json_response=True, streamable_http_path='/')


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


@mcp.tool()
def get_redacted_call_transcript(call_id: int, ctx: Context, offset: int = 0) -> dict:
    """Get one redacted 6000-character page of a call (use next_offset). Requires separately granted
    calls:transcript:read permission, revalidates caller and records disclosure.
    This tool is READ ONLY and may contain confidential business speech.
    """
    if type(call_id) is not int or call_id < 1 or type(offset) is not int or not 0 <= offset <= 2147483646:
        return {'error': 'invalid_call_id'}
    # Never trust model arguments, MCP _meta or a caller-provided user ID.
    # Re-read the authenticated HTTP credential for this *request* and
    # re-check the account's actual current permissions.
    from .main import store, oauth_config, oauth_verifier
    from .transcript_ai import transcript_for_ai, MAX_TRANSCRIPT_CHARS

    http_request = getattr(ctx.request_context, 'request', None)
    if http_request is None or not hasattr(http_request, 'headers'):
        return {'error': 'permission_denied'}
    authorization = http_request.headers.get('authorization', '')
    token = authorization[7:] if authorization.startswith('Bearer ') else ''
    if oauth_config.mode == 'oauth':
        subject = oauth_verifier.verify(token) if oauth_verifier else None
        actor = store.authorized_transcript_actor(
            oauth_issuer=oauth_config.issuer, oauth_subject=subject,
        ) if subject else None
    else:
        actor = store.authorized_transcript_actor(legacy_token=token)
    if actor is None:
        return {'error': 'permission_denied'}
    if not store.audit_transcript_request(
        user_id=actor, surface='mcp', call_id=call_id,
        char_limit=MAX_TRANSCRIPT_CHARS,
    ):
        return {'error': 'permission_denied'}
    record = database.transcript_excerpt(call_id, MAX_TRANSCRIPT_CHARS, offset)
    return transcript_for_ai(record, offset=offset) or {'error': 'not_found'}
