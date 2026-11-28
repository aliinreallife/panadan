"""Mixed-script canaries for the synthetic collection privacy boundary."""

from dataclasses import asdict, replace
from datetime import datetime, timezone
from hashlib import sha256

import pytest

from server.knowledge_call_privacy import REDACTION_VERSION, prepare_call
from server.knowledge_call_source import CallCursor, MAX_TRANSCRIPT_BYTES, SourceCall


NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)
BASE_CALL = SourceCall(CallCursor(NOW, 17), "operator-a", NOW, 3, False, 42, None, False)


@pytest.mark.parametrize(("raw", "expected"), [
    ("تلفن ۰۹۱۲‑٣٤٥‑۶۷۸۹ برای پیگیری.", "تلفن [PHONE] برای پیگیری."),
    ("+۹۸ (۹۱۲) ۳۴۵-۶۷۸۹ یا ۰۰۹۸۲۱۱۲۳۴۵۶۷۸", "[PHONE] یا [PHONE]"),
    ("شماره ۰۹۱۲\u200f۳۴۵\u200c۶۷۸۹", "شماره [PHONE]"),
    ("Email: canary+demo@example.invalid", "Email: [EMAIL]"),
    ("Email: canary$demo@example.invalid", "Email: [EMAIL]"),
    ("Email: user\u200c@demo.invalid", "Email: [EMAIL]"),
    ("Share https://example.invalid/user/canary?private=demo، سپس تماس", "Share [URL]، سپس تماس"),
    ("شبا IR ۹۹۰۰ ۰۰۰۰ ۰۰۰۰ ۰۰۰۰ ۰۰۰۰ ۰۰۱۲", "شبا [IBAN]"),
    ("کد ملی: ۱۲۳۴۵۶۷۸۹۰", "کد ملی: [ID]"),
    ("كد ملي ١٢٣٤٥٦٧٨٩٠", "كد ملي [ID]"),
    ("passport number: XY12345678", "passport number: [ID]"),
    ("کارت ١٢٣٤-۱۲۳۴-1234-۱۲۳۴، شمارهٔ داخلی ۱۷", "کارت [PAYMENT_ID]، شمارهٔ داخلی ۱۷"),
    ("شناسهٔ بدون برچسب ۱۲۳۴۵۶۷۸۹۰۱۲", "شناسهٔ بدون برچسب [LONG_NUMBER]"),
    ("هزینهٔ رفت‌وبرگشت ۱۲٬۴۰۰٬۰۰۰ تومان، تاریخ ۱۴۰۵/۰۸/۱۰", "هزینهٔ رفت‌وبرگشت ۱۲٬۴۰۰٬۰۰۰ تومان، تاریخ ۱۴۰۵/۰۸/۱۰"),
])
def test_redaction_removes_canaries_preserves_allowed_context_and_hashes_exact_output(raw, expected):
    call = prepare_call(replace(BASE_CALL, transcript=raw))
    assert call.outcome == "filtered"
    assert call.representation.text == expected
    assert call.representation.digest == sha256(expected.encode("utf-8")).hexdigest()
    assert call.representation.redaction_version == REDACTION_VERSION
    assert call.metadata == {"duration_seconds": 42}
    assert "text" not in repr(call)


def test_evidence_excerpt_is_anchored_to_filtered_code_points():
    text = prepare_call(replace(BASE_CALL, transcript="✈😀 تماس با ۰۹۱۲۳۴۵۶۷۸۹ برای بلیط")).representation
    start = text.text.index("[PHONE]")
    assert text.excerpt(start, start + len("[PHONE]")) == "[PHONE]"
    for bad in ((-1, 1), (0, 0), (0, len(text.text) + 1), (False, 1)):
        with pytest.raises(ValueError, match="Invalid filtered evidence span"):
            text.excerpt(*bad)


@pytest.mark.parametrize(("overrides", "outcome"), [
    ({"transcript": "\x00synthetic-private-canary"}, "transcript_invalid"),
    ({"transcript": "\ud800synthetic-private-canary"}, "transcript_invalid"),
    ({"transcript": "synthetic-private-canary @ disallowed"}, "transcript_review"),
    ({"transcript": " \n\t "}, "transcript_missing"),
    ({"transcript": "س" * (MAX_TRANSCRIPT_BYTES // 2 + 1)}, "transcript_oversize"),
    ({"transcript_oversize": True}, "transcript_oversize"),
    ({"duration_seconds": -1, "transcript": "synthetic-private-canary"}, "metadata_invalid"),
    ({"transcript": "synthetic-private-canary", "is_deleted": True}, "tombstone"),
])
def test_unsafe_or_unavailable_input_has_an_explicit_metadata_only_result(overrides, outcome):
    raw = replace(BASE_CALL, **overrides)
    prepared = prepare_call(raw)
    assert prepared.outcome == outcome and prepared.representation is None
    assert "synthetic-private-canary" not in repr(asdict(prepared))
    assert prepared.cursor == raw.cursor
    if outcome == "tombstone":
        assert prepared.operation == "tombstone" and prepared.metadata == {}


def test_transformed_text_is_also_bounded():
    # Compatibility normalization can expand a short input into longer text.
    text = "\ufdfa" * (MAX_TRANSCRIPT_BYTES // 3)
    prepared = prepare_call(replace(BASE_CALL, transcript=text))
    assert prepared.outcome == "filtered_oversize" and prepared.representation is None
