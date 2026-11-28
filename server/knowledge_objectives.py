"""Curated synthetic objective catalog and bounded structured configuration."""

from dataclasses import dataclass
import re


FILTERED_CALL = "filtered_call"
VALIDATED_KNOWLEDGE = "validated_knowledge"
CATALOG_REVISION = 1
_KEY = re.compile(r"[a-z][a-z0-9_]{0,39}\Z")
_KINDS = frozenset({"text", "integer", "boolean", "decimal", "reference"})
_CONTEXT = ("destination", "travel_date", "offer_basis", "currency", "confidence_reason")


@dataclass(frozen=True, slots=True)
class OutputField:
    key: str
    kind: str
    required: bool = False


@dataclass(frozen=True, slots=True)
class ObjectiveTemplate:
    key: str
    name: str
    input_kind: str
    output: tuple[OutputField, ...]
    context: tuple[str, ...]


TEMPLATES = (
    ObjectiveTemplate("customer_questions", "پرسش‌های مشتری", FILTERED_CALL, (
        OutputField("question", "text", True), OutputField("topic", "text"), OutputField("question_type", "text"),
    ), ("destination", "travel_date")),
    ObjectiveTemplate("customer_needs", "نیازها و ترجیحات مشتری", FILTERED_CALL, (
        OutputField("preference", "text", True), OutputField("constraint", "text"), OutputField("priority", "text"),
    ), ("destination", "travel_date")),
    ObjectiveTemplate("customer_concerns", "نگرانی‌های مشتری", FILTERED_CALL, (
        OutputField("concern", "text", True), OutputField("subject", "text"), OutputField("stated_reason", "text"),
    ), ("destination", "offer_basis")),
    ObjectiveTemplate("purchase_barriers", "موانع خرید", FILTERED_CALL, (
        OutputField("barrier", "text", True), OutputField("stage", "text"), OutputField("verified_outcome", "text"),
    ), ("destination", "offer_basis")),
    ObjectiveTemplate("destination_intelligence", "شناخت مقصد", FILTERED_CALL, (
        OutputField("destination", "text", True), OutputField("intent", "text"), OutputField("condition", "text"),
    ), ("travel_date", "offer_basis")),
    ObjectiveTemplate("price_sensitivity", "حساسیت به قیمت", FILTERED_CALL, (
        OutputField("stated_reaction", "text", True), OutputField("budget_min", "decimal"),
        OutputField("budget_max", "decimal"), OutputField("currency", "text"),
    ), ("destination", "currency", "offer_basis")),
    ObjectiveTemplate("content_opportunities", "فرصت‌های محتوا", VALIDATED_KNOWLEDGE, (
        OutputField("topic", "text", True), OutputField("knowledge_reference", "reference", True),
        OutputField("audience", "text"), OutputField("format", "text"),
    ), ("destination", "confidence_reason")),
)


def checked_key(value: str) -> str:
    if type(value) is not str or not _KEY.fullmatch(value):
        raise ValueError("Invalid configuration key")
    return value


def checked_text(value: str, *, limit: int) -> str:
    if type(value) is not str or not value.strip() or len(value) > limit or "\x00" in value:
        raise ValueError("Invalid configuration text")
    return value.strip()


def _field_schema(field: OutputField):
    kind = field.kind
    if kind == "text":
        schema = {"type": "string", "minLength": 1, "maxLength": 400}
    elif kind == "integer":
        schema = {"type": "integer", "minimum": -1_000_000_000, "maximum": 1_000_000_000}
    elif kind == "boolean":
        schema = {"type": "boolean"}
    elif kind == "decimal":
        schema = {"type": "string", "pattern": r"^-?[0-9]{1,18}(\.[0-9]{1,6})?$"}
    else:
        schema = {"type": "string", "pattern": r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"}
    if not field.required:
        schema["type"] = [schema["type"], "null"]
    return schema


def output_schema(fields: tuple[OutputField, ...]) -> dict:
    """Compile a small reviewed vocabulary instead of accepting arbitrary schemas."""
    if type(fields) is not tuple or not 1 <= len(fields) <= 12:
        raise ValueError("Objective must define 1–12 output fields")
    properties = {}
    required = []
    for field in fields:
        if (type(field) is not OutputField or type(field.kind) is not str
                or field.kind not in _KINDS or type(field.required) is not bool):
            raise ValueError("Unsupported objective output field")
        key = checked_key(field.key)
        if key in properties:
            raise ValueError("Duplicate objective output field")
        properties[key] = _field_schema(field)
        if field.required:
            required.append(key)
    if not required:
        raise ValueError("An objective needs at least one required output field")
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


def context_schema(fields: tuple[str, ...]) -> dict:
    if (type(fields) is not tuple or any(type(field) is not str or field not in _CONTEXT for field in fields)
            or len(set(fields)) != len(fields)):
        raise ValueError("Unsupported objective context")
    return {"type": "object", "properties": {key: _field_schema(OutputField(key, "text")) for key in fields},
            "additionalProperties": False}


def template_definition(template: ObjectiveTemplate) -> dict:
    return {"output": output_schema(template.output), "context": context_schema(template.context)}


def resolve_objective(*, template_key: str | None, fields: tuple[OutputField, ...] | None, context: tuple[str, ...] | None):
    """Choose a pinned curated template or a simple custom call objective."""
    if template_key is None:
        return FILTERED_CALL, output_schema(fields), context_schema(context if context is not None else ())
    checked_key(template_key)
    template = next((item for item in TEMPLATES if item.key == template_key), None)
    if template is None:
        raise ValueError("Unknown objective template")
    return (template.input_kind, output_schema(fields if fields is not None else template.output),
            context_schema(context if context is not None else template.context))
