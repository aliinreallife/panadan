"""Versioned pre-persistence filtering. Only exact filtered text can anchor evidence."""

from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
import re
import unicodedata

from .knowledge_call_contract import validate_call_metadata
from .knowledge_call_source import CallCursor, MAX_TRANSCRIPT_BYTES, SourceCall


REDACTION_VERSION = "call-redaction-v1"
_DIGITS_AND_LETTERS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩يك", "01234567890123456789یک")
_BIDI_OVERRIDE = str.maketrans("", "", "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")
_SEP = r"[ .()\-‐‑–]{0,3}"
_EMAIL_LOCAL = r"\w.!#$%&'*+/=?^\x60{|}~-"

# Typed markers describe what was removed. The v1 rules intentionally do not
# infer names, addresses, or identifiers embedded in arbitrary spoken text.
_SENSITIVE = re.compile(
    r"""(?P<URL>\b(?:https?://|www\.)[^\s<>"'،؛]+)"""
    rf"""|(?P<EMAIL>(?<![@{_EMAIL_LOCAL}])[{_EMAIL_LOCAL}]{{1,254}}@[\w-]{{1,63}}(?:\.[\w-]{{1,63}}){{1,10}})"""
    r"""|(?P<IBAN>(?<!\w)IR[ -]*(?:[0-9][ -]{0,2}){23}[0-9](?![0-9]))"""
    r"""|(?P<ID_LABEL>(?:کد[ ]*ملی|شماره[ ]*(?:گذرنامه|پاسپورت)|national[ ]+id|passport[ ]+(?:number|no\.?))(?:[ ]*[:=][ ]*|[ ]+))"""
    r"""(?P<ID_VALUE>[A-Z]{0,3}[0-9](?:[ -]{0,2}[0-9]){5,17})(?![0-9])"""
    rf"""|(?P<PHONE>(?<![0-9])(?:\+?98{_SEP}|0098{_SEP}|0{_SEP})[1-9](?:{_SEP}[0-9]){{9}}(?![0-9])"""
    r"""|(?<![0-9])9[0-9]{9}(?![0-9]))"""
    r"""|(?P<PAYMENT_ID>(?<![0-9])[0-9]{4}(?:[ -][0-9]{4}){3}(?![0-9]))"""
    r"""|(?P<LONG_NUMBER>(?<![0-9])[0-9]{12,}(?![0-9]))""",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class FilteredTranscript:
    text: str = field(repr=False)
    digest: str
    redaction_version: str

    def excerpt(self, start: int, end: int) -> str:
        """Resolve half-open Unicode code point offsets into this version."""
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(self.text):
            raise ValueError("Invalid filtered evidence span")
        return self.text[start:end]


@dataclass(frozen=True, slots=True)
class PreparedCall:
    cursor: CallCursor
    operator_key: str
    event_at: datetime
    revision_no: int
    operation: str
    metadata: dict[str, int | None]
    representation: FilteredTranscript | None
    outcome: str


def _filtered_text(raw: str) -> str:
    display = unicodedata.normalize("NFKC", raw).translate(_BIDI_OVERRIDE)
    # Detect across invisible format characters, including Persian half-spaces,
    # while keeping them in unaffected output and mapping matches back to text.
    positions = [index for index, char in enumerate(display) if unicodedata.category(char) != "Cf"]
    shadow = "".join(display[index] for index in positions).translate(_DIGITS_AND_LETTERS)
    parts = []
    previous = 0
    for match in _SENSITIVE.finditer(shadow):
        label = match.lastgroup
        start, end = match.span()
        if label == "ID_VALUE":
            start, end = match.span("ID_VALUE")
            label = "ID"
        start, end = positions[start], positions[end - 1] + 1
        parts.extend((display[previous:start], f"[{label}]"))
        previous = end
    parts.append(display[previous:])
    return "".join(parts)


def _prepare_transcript(raw: str | None):
    if raw is None:
        return None, "transcript_missing"
    if type(raw) is not str or "\x00" in raw:
        return None, "transcript_invalid"
    try:
        if len(raw.encode("utf-8")) > MAX_TRANSCRIPT_BYTES:
            return None, "transcript_oversize"
        filtered = _filtered_text(raw)
        encoded = filtered.encode("utf-8")
    except UnicodeError:
        return None, "transcript_invalid"
    if not filtered.strip():
        return None, "transcript_missing"
    if "@" in filtered:
        return None, "transcript_review"
    if len(encoded) > MAX_TRANSCRIPT_BYTES:
        return None, "filtered_oversize"
    return FilteredTranscript(filtered, sha256(encoded).hexdigest(), REDACTION_VERSION), "filtered"


def prepare_call(call: SourceCall) -> PreparedCall:
    """Discard the source payload before any durable or diagnostic boundary."""
    identity = (call.cursor, call.operator_key, call.event_at, call.revision_no)
    if call.is_deleted:
        return PreparedCall(*identity, "tombstone", {}, None, "tombstone")
    metadata = {"duration_seconds": call.duration_seconds}
    try:
        validate_call_metadata(metadata)
    except ValueError:
        return PreparedCall(*identity, "upsert", {}, None, "metadata_invalid")
    if call.transcript_oversize:
        return PreparedCall(*identity, "upsert", metadata, None, "transcript_oversize")
    representation, outcome = _prepare_transcript(call.transcript)
    return PreparedCall(*identity, "upsert", metadata, representation, outcome)
