"""Small, bounded validator for the independent output contract (no SDK)."""

import json
import re
from datetime import datetime
from pathlib import Path


SCHEMA = json.loads((Path(__file__).resolve().parents[3] / "contracts/parallel/outputs.schema.json").read_text())
MAX_BYTES = 65536
MAX_NODES = 2048
MAX_DEPTH = 8
PREPARATION_TTL_SECONDS = 300


class OutputValidationError(ValueError):
    """Safe, fixed diagnostic; never reflects untrusted payload values."""

    def __init__(self, code, field, message):
        self.code = code
        self.field = field
        super().__init__(message)

    @property
    def issue(self):
        return {"code": self.code, "field": self.field, "message": str(self), "retryable": False}


def fail(field, message, code="invalid_output"):
    raise OutputValidationError(code, field, message)


def instant(value, field):
    if not isinstance(value, str) or len(value) > 40 or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?(Z|\+00:00)", value
    ):
        fail(field, "Use an RFC 3339 UTC instant.")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        fail(field, "Use a valid UTC instant.")


def bounded_json(value):
    """Check before serialization: cycles, oversized containers and nesting are bounded."""
    stack = [(value, 0)]
    count = 0
    characters = 0
    while stack:
        child, depth = stack.pop()
        count += 1
        if depth > MAX_DEPTH or count + len(stack) > MAX_NODES:
            fail("$", "Output exceeds the nesting or node limit.", "output_limit")
        if type(child) is dict:
            if len(child) + count + len(stack) > MAX_NODES:
                fail("$", "Output exceeds the node limit.", "output_limit")
            for key, item in child.items():
                if type(key) is not str:
                    fail("$", "Output must use JSON string keys.")
                characters += len(key)
                stack.append((item, depth + 1))
        elif type(child) is list:
            if len(child) + count + len(stack) > MAX_NODES:
                fail("$", "Output exceeds the node limit.", "output_limit")
            stack.extend((item, depth + 1) for item in child)
        elif type(child) is str:
            characters += len(child)
        elif child is not None and type(child) not in (int, float, bool):
            fail("$", "Output must contain finite JSON values.")
        if characters > MAX_BYTES:
            fail("$", "Output exceeds the byte limit.", "output_limit")
    try:
        encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError, OverflowError, RecursionError):
        fail("$", "Output must contain finite bounded JSON values.")
    if len(encoded.encode("utf-8")) > MAX_BYTES:
        fail("$", "Output exceeds the byte limit.", "output_limit")


def validate_shape(name, value):
    """Validate only this package's schema vocabulary; semantic checks are separate."""
    bounded_json(value)
    _validate(SCHEMA["$defs"][name], value, "$")
    if name == "Id":
        safe_id(value, "$")


def _validate(schema, value, field):
    if "$ref" in schema:
        name = schema["$ref"].split("/")[-1]
        _validate(SCHEMA["$defs"][name], value, field)
        if name == "Id":
            safe_id(value, field)
        return
    expected = schema.get("type")
    kinds = {"object": dict, "array": list, "string": str, "integer": int,
             "boolean": bool, "null": type(None)}
    if expected and type(value) not in tuple(kinds[k] for k in ([expected] if isinstance(expected, str) else expected)):
        fail(field, "Output has the wrong JSON type.")
    if "enum" in schema and value not in schema["enum"]:
        fail(field, "Output contains an unsupported choice.")
    if type(value) is dict:
        properties = schema.get("properties", {})
        if any(key not in value for key in schema.get("required", [])):
            fail(field, "Output is missing a required field.")
        if schema.get("additionalProperties") is False and any(key not in properties for key in value):
            fail(field, "Output contains an unexpected field.")
        for key, child in value.items():
            if key in properties:
                _validate(properties[key], child, field + "." + key)
    elif type(value) is list:
        if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", MAX_NODES):
            fail(field, "Output collection is outside the allowed bounds.", "output_limit")
        if schema.get("uniqueItems") and len({json.dumps(child, sort_keys=True) for child in value}) != len(value):
            fail(field, "Output selections must be unique.")
        for index, child in enumerate(value):
            _validate(schema.get("items", {}), child, f"{field}[{index}]")
    elif type(value) is str:
        if not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", MAX_BYTES):
            fail(field, "Output text is outside the allowed bounds.", "output_limit")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            fail(field, "Output text has an invalid format.")
        if schema.get("format") == "date-time":
            instant(value, field)
    elif type(value) is int:
        if not schema.get("minimum", 0) <= value <= schema.get("maximum", 2**63 - 1):
            fail(field, "Output number is outside the allowed bounds.")


def plain_text(value, field):
    # Text stays inert even when a renderer is introduced. Do not accept markup,
    # code fences, active URI schemes or hidden control/bidi formatting.
    if (any(char in value for char in "<>`")
            or re.search(r"(?:javascript|vbscript|data)\s*:", value, re.I)
            or any(ord(char) < 32 and char not in "\n\t" for char in value)
            or any(127 <= ord(char) <= 159 or 0x202A <= ord(char) <= 0x202E
                   or 0x2066 <= ord(char) <= 0x2069 for char in value)):
        fail(field, "Output must be plain display text without executable markup or hidden controls.")


def safe_id(value, field):
    plain_text(value, field)
    if any(character.isspace() for character in value):
        fail(field, "Output identities must not contain whitespace.")


def identity(snapshot):
    if type(snapshot) is not dict:
        fail("$.snapshot", "An authorized snapshot object is required.")
    validate_shape("SnapshotIdentity", {key: snapshot.get(key) for key in
                                       ("contract_version", "case_id", "case_version")})
    return snapshot["case_id"], snapshot["case_version"]


def validate_preparation(snapshot, prepared, now):
    case_id, version = identity(snapshot)
    if prepared["case_id"] != case_id or prepared["input_case_version"] != version:
        fail("$.input_case_version", "Prepared output belongs to a different snapshot; prepare again.", "stale_output")
    age = (instant(now, "$.now") - instant(prepared["prepared_at"], "$.prepared_at")).total_seconds()
    if age < 0 or age > PREPARATION_TTL_SECONDS:
        fail("$.prepared_at", "Prepared output is future-dated or expired; prepare again.", "stale_output")
