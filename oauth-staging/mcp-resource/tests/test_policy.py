"""No-network security tests for the isolated Test-only binding."""
import hashlib
import pytest

from policy import STAGING_RESOURCE, STAGING_CIMD_CLIENT_ID, permitted_test_identity

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


def test_opt_in_dynamic_test_clients_are_strictly_subject_bound():
    other_test_client = "connected-app-test-11111111-2222-3333-4444-555555555555"
    details = {"subject": SUBJECT, "client_id": other_test_client}

    # Default remains pinned even for a correctly shaped Stytch Test client ID.
    assert not permitted_test_identity(details, CLIENT, SUBJECT_HASH)
    assert permitted_test_identity(details, CLIENT, SUBJECT_HASH, client_mode="any-test-client")
    assert permitted_test_identity(
        {"subject": SUBJECT, "client_id": CLIENT},
        CLIENT, SUBJECT_HASH, client_mode="any-test-client",
    )

    for unauthorized in [
        None, {},
        {"subject": SUBJECT, "client_id": ""},
        {"subject": SUBJECT, "client_id": None},
        {"subject": SUBJECT, "client_id": "connected-app-live-11111111-2222-3333-4444-555555555555"},
        {"subject": SUBJECT, "client_id": "https://attacker.example/client.json"},
        {"subject": SUBJECT, "client_id": "connected-app-test-ABC"},
        {"subject": SUBJECT + "-not-approved", "client_id": other_test_client},
    ]:
        assert not permitted_test_identity(
            unauthorized, CLIENT, SUBJECT_HASH, client_mode="any-test-client"
        )

    assert not permitted_test_identity(
        details, CLIENT, "0" * 64, client_mode="any-test-client"
    )
    assert not permitted_test_identity(
        details, "", SUBJECT_HASH, client_mode="any-test-client"
    )
    assert not permitted_test_identity(
        details, CLIENT, SUBJECT_HASH, client_mode="unknown"
    )


def test_cimd_client_requires_exact_self_owned_url_and_experimental_mode():
    owned = {"subject": SUBJECT, "client_id": STAGING_CIMD_CLIENT_ID}
    assert not permitted_test_identity(owned, CLIENT, SUBJECT_HASH)
    assert permitted_test_identity(owned, CLIENT, SUBJECT_HASH, client_mode="any-test-client")
    for alternate in (
        STAGING_CIMD_CLIENT_ID + "/",
        STAGING_CIMD_CLIENT_ID.replace("panadan-stytch-oauth-staging", "evil-example"),
        "https://evil.example/metadata.json",
        STAGING_CIMD_CLIENT_ID.replace("https://", "http://"),
    ):
        assert not permitted_test_identity(
            {"subject": SUBJECT, "client_id": alternate},
            CLIENT, SUBJECT_HASH, client_mode="any-test-client"
        )
    assert not permitted_test_identity(
        {"subject": "different-test-member", "client_id": STAGING_CIMD_CLIENT_ID},
        CLIENT, SUBJECT_HASH, client_mode="any-test-client"
    )


def test_explicit_dynamic_client_allowlist_denies_unapproved_clients():
    new_client = "connected-app-test-548c584f-4a24-4fab-9054-84e463e44acc"
    unknown = "connected-app-test-11111111-2222-3333-4444-555555555555"
    details = {"subject": SUBJECT, "client_id": new_client}
    allow = (new_client,)
    assert not permitted_test_identity(details, CLIENT, SUBJECT_HASH)
    assert not permitted_test_identity(details, CLIENT, SUBJECT_HASH,
                                      client_mode="approved-test-clients")
    assert permitted_test_identity(details, CLIENT, SUBJECT_HASH,
                                   client_mode="approved-test-clients",
                                   approved_clients=allow)
    assert permitted_test_identity(
        {"subject": SUBJECT, "client_id": CLIENT}, CLIENT, SUBJECT_HASH,
        client_mode="approved-test-clients", approved_clients=allow)
    for other in (unknown, STAGING_CIMD_CLIENT_ID, "", "connected-app-live-" + "1" * 36):
        assert not permitted_test_identity(
            {"subject": SUBJECT, "client_id": other}, CLIENT, SUBJECT_HASH,
            client_mode="approved-test-clients", approved_clients=allow)
    assert not permitted_test_identity(
        {"subject": "wrong-member", "client_id": new_client},
        CLIENT, SUBJECT_HASH, client_mode="approved-test-clients",
        approved_clients=allow)
    assert not permitted_test_identity(
        details, CLIENT, SUBJECT_HASH, client_mode="approved-test-clients",
        approved_clients=("https://attacker.example/client.json",))
    assert not permitted_test_identity(
        details, CLIENT, SUBJECT_HASH, client_mode="approved-test-clients",
        approved_clients=(new_client,) * 9)
