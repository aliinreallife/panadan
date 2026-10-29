"""Conservative, bounded transcript projection for external AI tools.

This is not guaranteed anonymization. The transcript may still contain spoken
names or sensitive statements. An administrator must explicitly authorize it.
"""
from __future__ import annotations

import re

MAX_TRANSCRIPT_CHARS = 6000
_PHONE = re.compile(r'(?<![\d۰-۹])(?:\+?98|\+?۹۸|0|۰)?[9۹][\d۰-۹]{9}(?![\d۰-۹])')
_EMAIL = re.compile(r'(?<![\w.@])[-\w.+]+@[-\w.]+\.[A-Za-z]{2,}(?![\w.-])')
_URL = re.compile(r'(?i)https?://[^\s<>]+')
_IBAN = re.compile(r'(?i)\bIR[0-9]{24}\b')


def transcript_for_ai(record: dict | None, *, limit: int = MAX_TRANSCRIPT_CHARS,
                      offset: int = 0) -> dict | None:
    """Return a scrubbed partial transcript, never customer fields or raw SQL."""
    if record is None:
        return None
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or limit > MAX_TRANSCRIPT_CHARS:
        raise ValueError('Invalid transcript limit')
    if type(offset) is not int or not 0 <= offset <= 2147483646:
        raise ValueError('Invalid transcript offset')
    text = str(record.get('transcription') or '')
    # Bound return size even if the database view contains a huge transcript.
    text = text[:limit]
    text = _EMAIL.sub('[ایمیل حذف شد]', text)
    text = _PHONE.sub('[شماره تلفن حذف شد]', text)
    text = _URL.sub('[لینک حذف شد]', text)
    text = _IBAN.sub('[شماره شبا حذف شد]', text)
    return {
        'call_id': record['id'],
        'text': text[:limit],
        'has_more': bool(record.get('total_chars', 0) > offset + len(str(record.get('transcription') or ''))),
        'next_offset': offset + len(str(record.get('transcription') or '')),
        'offset': offset,
        'truncated': bool(record.get('total_chars', 0) > offset + len(str(record.get('transcription') or ''))),
        'source_chars': int(record.get('total_chars', 0)),
        'presentation': 'Panadan AI excerpt (redacted)',
        'privacy_notice': 'Names and other private details spoken in the call may remain. Treat as confidential.',
    }
