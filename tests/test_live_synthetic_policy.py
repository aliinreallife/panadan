"""Offline policy checks: never contacts Stytch, a VPS, or production records."""
from __future__ import annotations
import hashlib
import importlib.util
from pathlib import Path

FILE = Path(__file__).resolve().parents[1] / "oauth-live/mcp-synthetic/policy.py"
spec = importlib.util.spec_from_file_location("live_synthetic_policy", FILE)
assert spec and spec.loader
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


def test_live_synthetic_never_accepts_missing_binding():
    d = {"subject": "member-live-fake", "client_id": "connected-app-live-fake"}
    digest = hashlib.sha256(d["subject"].encode()).hexdigest()
    assert not policy.approved_live_pilot(d, "", digest)
    assert not policy.approved_live_pilot(d, d["client_id"], "")
    assert not policy.approved_live_pilot(None, d["client_id"], digest)
    assert not policy.approved_live_pilot({"subject": d["subject"]}, d["client_id"], digest)


def test_live_synthetic_requires_exact_signed_subject_and_client():
    d = {"subject": "member-live-fake", "client_id": "connected-app-live-fake"}
    digest = hashlib.sha256(d["subject"].encode()).hexdigest()
    assert policy.approved_live_pilot(d, d["client_id"], digest)
    assert not policy.approved_live_pilot({**d, "subject": "other"}, d["client_id"], digest)
    assert not policy.approved_live_pilot({**d, "client_id": "other"}, d["client_id"], digest)
    assert not policy.approved_live_pilot(d, d["client_id"], digest.upper())
    assert not policy.approved_live_pilot(d, d["client_id"], "0" * 64)


def test_live_synthetic_issuer_and_audience_are_not_production():
    assert policy.LIVE_ISSUER == "https://flame-calf-4073.customers.stytch.com"
    assert policy.SYNTHETIC_RESOURCE == "https://panadan-mcp-live-synthetic.vercel.app/mcp/"
    assert policy.SYNTHETIC_RESOURCE != "https://dan.panafor.com/mcp/"
    assert ".stytch.dev" not in policy.LIVE_ISSUER
