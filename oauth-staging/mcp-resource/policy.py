"""Fail-closed, synthetic-only user/client binding for Stytch Test MCP.

The bearer must have *already passed* OAuthVerifier.verify_details().
Never infer any grant from client-controlled tool arguments or unverified JWT.
"""
from __future__ import annotations

import hashlib
import hmac
import re

STAGING_RESOURCE = "https://panadan-mcp-oauth-staging.vercel.app/mcp/"
STYTCH_TEST_ISSUER = "https://viridian-faucet-2753.customers.stytch.dev"
CLIENT_PATTERN = re.compile(r"connected-app-test-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z", re.I)
SUBJECT_HASH_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


def permitted_test_identity(
    verified_details: dict | None,
    expected_client: str,
    expected_subject_sha256: str,
) -> bool:
    """Require a pinned client and user binding; no configuration means no access."""
    if not isinstance(verified_details, dict):
        return False
    client = verified_details.get("client_id")
    subject = verified_details.get("subject")
    if (not isinstance(client, str) or not CLIENT_PATTERN.fullmatch(client)
            or not isinstance(subject, str) or not subject
            or not isinstance(expected_client, str) or not CLIENT_PATTERN.fullmatch(expected_client)
            or not isinstance(expected_subject_sha256, str)
            or not SUBJECT_HASH_PATTERN.fullmatch(expected_subject_sha256)):
        return False
    digest = hashlib.sha256(subject.encode("utf-8")).hexdigest()
    return (hmac.compare_digest(client, expected_client)
            and hmac.compare_digest(digest, expected_subject_sha256))
