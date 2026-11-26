"""Synthetic original-transcript grant and disclosure tests; no customer data."""
from types import SimpleNamespace
import pytest
from server.security import Store
from server.transcript_ai import raw_transcript_page, transcript_for_ai

ISSUER="https://synthetic.authkit.app"
OWNER="user_owner123"
MEMBER="user_member123"
CLIENT="https://example.invalid/oauth/client.json"

def test_raw_is_lossless_and_bounded():
    value="  مشتری: 09123456789\nاپراتور: پاسخ  "
    record={"id":1,"transcription":value,"total_chars":len(value),"_window_start":0}
    assert raw_transcript_page(record)["text"]==value
    assert "09123456789" not in transcript_for_ai(record)["text"]
    p1=raw_transcript_page(record,limit=10)
    p2=raw_transcript_page(record,offset=p1["next_offset"])
    assert p1["text"]+p2["text"]==value
    assert not p2["has_more"]
    assert raw_transcript_page(record,offset=100)["text"]==""

def test_explicit_raw_grants_are_independent_and_revocable(tmp_path):
    store=Store(str(tmp_path/"auth.sqlite"))
    store.bootstrap("owner","synthetic-long-password")
    store.prepare_authkit_admin(1,ISSUER,OWNER,multi_user=True)
    uid=store.provision_native_user(ISSUER,MEMBER,"member@example.invalid")
    def edit(raw=False,active=True,caps=None,fields=None):
        store.update_native_user(uid,ISSUER,actor_id=1,active=active,
            caps=caps if caps is not None else ["calls:read","mcp:use"],
            fields=fields if fields is not None else ["id"],panels=[],raw_transcript=raw)
    def consent(raw=False,client=CLIENT):
        store.approve_mcp_client(uid,client,["mcp:use","calls:read"],["id"],
            raw_transcript=raw,native_issuer=ISSUER,native_owner_uid=1)
    def audit(client=None):
        return store.audit_raw_transcript_request(uid=uid,issuer=ISSUER,owner_uid=1,
            call_id=42,char_limit=6000,client_id=client)
    assert not audit()
    assert not audit(CLIENT)
    edit()
    store.note_signed_mcp_client(uid,CLIENT)
    with pytest.raises(ValueError):consent(True)
    edit(True)
    assert audit()
    assert not audit(CLIENT)
    assert "calls:transcript:read" not in store.user_access(uid)["capabilities"]
    assert "transcription" not in store.user_access(uid)["fields"]
    with pytest.raises(ValueError):consent(True)
    store.note_signed_mcp_client(uid,CLIENT)
    consent()
    assert not audit(CLIENT)
    consent(True)
    assert audit(CLIENT)
    assert not audit("other-client")
    assert not store.native_raw_client_allowed(uid,ISSUER,1,"other-client")
    assert not store.native_raw_client_allowed(uid,"https://wrong.invalid",1,CLIENT)
    store.revoke_mcp_client(uid,CLIENT)
    assert not audit(CLIENT)
    assert audit()
    store.note_signed_mcp_client(uid,CLIENT)
    consent(True)
    edit(False)
    assert not audit() and not audit(CLIENT)
    with pytest.raises(ValueError):edit(True,caps=["metrics:read"],fields=["id"])
    with pytest.raises(ValueError):edit(True,fields=[])
    with store.db() as c:
        events=c.execute("SELECT surface,client_id,call_id FROM raw_transcript_access_audit").fetchall()
        assert [(r["surface"],r["client_id"]) for r in events]==[("web",None),("mcp",CLIENT),("web",None)]
        assert all(r["call_id"]==42 for r in events)
