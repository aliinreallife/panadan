"""Reviewed synthetic call source and typed metadata contracts."""

SYNTHETIC_ADAPTER = "synthetic-call-v1"
SOURCE_FIELDS = (
    "call_id", "operator_key", "event_at", "changed_at", "revision_no",
    "is_deleted", "duration_seconds", "transcript",
)
MAX_DURATION_SECONDS = 86_400


class UnsupportedCallContract(ValueError):
    """Fixed error suitable for logging without recording source configuration."""


def synthetic_call_contract():
    return {
        "source_identity": "positive_bigint_call_id",
        "operator_identity": "opaque_operator_key",
        "field_allowlist": list(SOURCE_FIELDS),
        "event_timestamp": "event_at_utc_half_open",
        "revision_order": "monotonic_revision_no_per_call",
        "change_cursor": ["changed_at", "call_id"],
        "deletion": "explicit_is_deleted_tombstone",
    }


def require_synthetic_call_contract(*, kind, adapter, state, contract):
    """Deny any unapproved version, adapter or field before collection."""
    if (kind != "database" or adapter != SYNTHETIC_ADAPTER or state != "synthetic"
            or contract != synthetic_call_contract()):
        raise UnsupportedCallContract("Unsupported synthetic call contract")


def call_metadata_schema():
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "duration_seconds": {
                "type": ["integer", "null"],
                "minimum": 0,
                "maximum": MAX_DURATION_SECONDS,
            },
        },
    }


def validate_call_metadata(metadata):
    """Permit absent or unknown duration while rejecting unapproved fields."""
    if type(metadata) is not dict or metadata.keys() - {"duration_seconds"}:
        raise ValueError("Unsupported call metadata")
    duration = metadata.get("duration_seconds")
    if duration is not None and (type(duration) is not int or not 0 <= duration <= MAX_DURATION_SECONDS):
        raise ValueError("Invalid call duration")
