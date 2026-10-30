"""Bounded transcript extraction with privacy masking across page boundaries.

This is best-effort redaction, not anonymization. Spoken names, addresses,
unrecognized IDs and unusually long secrets may still be present.
"""
from __future__ import annotations

import re

MAX_TRANSCRIPT_CHARS = 6000
# Context comes from the read-only database query, never from user input.
_PHONE = re.compile(r'(?<![\d۰-۹])(?:\+?98|\+?۹۸|0|۰)?[9۹][\d۰-۹]{9}(?![\d۰-۹])')
_EMAIL = re.compile(r'(?<![\w.@])[-\w.+]+@[-\w.]+\.[A-Za-z]{2,}(?![\w.-])')
_URL = re.compile(r'(?i)https?://[^\s<>]+')
_IBAN = re.compile(r'(?i)\bIR[0-9]{24}\b')
# Long uninterrupted digit sequences may contain other identifiers.
_LONG_DIGITS = re.compile(r'(?<![\d۰-۹])[\d۰-۹]{12,}(?![\d۰-۹])')


def _mask(text: str) -> str:
    """Replace each sensitive character in-place, preserving source offsets.

    Fixed-width replacements are intentional: next_offset is measured in the
    *original* transcription, not the redacted output.
    """
    for pattern in (_URL, _EMAIL, _IBAN, _PHONE, _LONG_DIGITS):
        text = pattern.sub(lambda m: '█' * len(m.group(0)), text)
    return text


def transcript_for_ai(record: dict | None, *, limit: int = MAX_TRANSCRIPT_CHARS,
                      offset: int = 0) -> dict | None:
    """Return only the requested page, after masking its overlapping context."""
    if record is None:
        return None
    if type(limit) is not int or not 1 <= limit <= MAX_TRANSCRIPT_CHARS:
        raise ValueError('Invalid transcript limit')
    if type(offset) is not int or not 0 <= offset <= 2147483646:
        raise ValueError('Invalid transcript offset')

    window_start = record.get('_window_start', offset)
    if type(window_start) is not int or not 0 <= window_start <= offset:
        raise ValueError('Invalid transcript window start')
    before = offset - window_start
    raw_window = str(record.get('transcription') or '')
    total = int(record.get('total_chars') or 0)
    # A caller may seek beyond EOF. Return an empty terminal page; never error
    # or compute a negative page length.
    if before > len(raw_window) and offset < total:
        raise ValueError('Invalid transcript window')
    page_length = max(0, min(limit, len(raw_window) - before))
    # Redact *before* clipping: tokens split over two pages are still detected.
    safe_window = _mask(raw_window)
    excerpt = safe_window[before:before + page_length]
    next_offset = offset + page_length

    return {
        'call_id': record['id'],
        'text': excerpt,
        'has_more': total > next_offset,
        'next_offset': next_offset,
        'offset': offset,
        'truncated': total > next_offset,
        'source_chars': total,
        'presentation': 'Panadan AI excerpt (best-effort redacted)',
        'privacy_notice': 'Masking is not anonymization. Spoken names and private statements can remain.',
    }
