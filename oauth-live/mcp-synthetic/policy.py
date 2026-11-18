"""Explicitly pinned Stytch Live identity for an isolated synthetic MCP demo.

This is NOT Panadan authorization and never supplies customer data. No member
or client is authorized by default. Both live identity binding values must
be set out-of-band after independently reviewing the exact signed token.
"""
from __future__ import annotations

import hashlib
import hmac
import re

LIVE_ISSUER = "https://flame-calf-4073.customers.stytch.com"
LIVE_JWKS = LIVE_ISSUER + "/.well-known/jwks.json"
SYNTHETIC_RESOURCE = "https://panadan-mcp-live-synthetic.vercel.app/mcp/"
REQUIRED_SCOPE = "panadan:mcp:read"
SHA256_HEX = re.compile(r"[a-f0-9]{64}\Z")


def approved_live_pilot(
    verified_details: dict | None, expected_client_id: str, expected_subject_sha256: str
) -> bool:
    """Require signed, already-verified identity plus exact, explicit pilot binding."""
    if not isinstance(verified_details, dict):
        return False
    subject = verified_details.get("subject")
    client = verified_details.get("client_id")
    if not isinstance(subject, str) or not subject or len(subject) > 256:
        return False
    if not isinstance(client, str) or not client or len(client) > 160:
        return False
    if not isinstance(expected_client_id, str) or not expected_client_id:
        return False
    if not isinstance(expected_subject_sha256, str) or not SHA256_HEX.fullmatch(expected_subject_sha256):
        return False
    if not hmac.compare_digest(client, expected_client_id):
        return False
    return hmac.compare_digest(
        hashlib.sha256(subject.encode("utf-8")).hexdigest(), expected_subject_sha256
    )
