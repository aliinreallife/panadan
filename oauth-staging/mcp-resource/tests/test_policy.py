"""No-network security tests for the isolated Test-only binding."""
import hashlib
import pytest

from policy import STAGING_RESOURCE, permitted_test_identity

CLIENT = "connected-app-test-e2f5508f-e63e-4a7a-8fab-207276bda582"
SUBJECT = "user-test-disposable-test-subject"
SUBJECT_HASH = hashlib.sha256(SUBJECT.encode("utf-8")).hexdigest()


def test_canonical_resource_is_staging_only():
    assert STAGING_RESOURCE == "https://panadan-mcp-oauth-staging.vercel.app/mcp/"
    assert "dan.panafor.com" not in STAGING_RESOURCE


def test_identity_binding_is_explicit_and_pinned():
    details = {"subject": SUBJECT, "client_id": CLIENT}
    assert permitted_test_identity(details, CLIENT, SUBJECT_HASH)
    for obj in [
        None, {}, {"subject": SUBJECT}, {"client_id": CLIENT},
        {"subject": SUBJECT, "client_id": None},
        {"subject": "another", "client_id": CLIENT},
        {"subject": SUBJECT, "client_id": "connected-app-test-11111111-2222-3333-4444-555555555555"},
    ]:
        assert not permitted_test_identity(obj, CLIENT, SUBJECT_HASH)
    assert not permitted_test_identity(details, "", SUBJECT_HASH)
    assert not permitted_test_identity(details, CLIENT, "")
    assert not permitted_test_identity(details, CLIENT, "0" * 63)
    assert not permitted_test_identity(details, "connected-app-live-11111111-2222-3333-4444-555555555555", SUBJECT_HASH)
