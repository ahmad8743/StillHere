"""Local proposal validation. No shared-schema or persistence dependencies."""

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


SCHEMA = json.loads((Path(__file__).resolve().parents[3] /
                     "contracts/parallel/check-ins.schema.json").read_text())


class CheckInError(ValueError):
    def __init__(self, code, field, message):
        self.code, self.field = code, field
        super().__init__(message)


def instant(value):
    """Accept only timezone-aware UTC instants, matching the shared convention."""
    try:
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)", value):
            raise ValueError()
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None or result.utcoffset().total_seconds() != 0:
            raise ValueError()
        return result
    except (ValueError, TypeError, OverflowError):
        raise CheckInError("invalid_input", "$", "Use a valid UTC timestamp.") from None


def timestamp(value):
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError, RecursionError):
        raise CheckInError("invalid_input", "$", "Use finite JSON data.") from None


def validate(name, value):
    canonical(value)
    _validate(SCHEMA["$defs"][name], value, "$")


def _validate(schema, value, path):
    def fail(message):
        raise CheckInError("invalid_input", path, message)

    if "$ref" in schema:
        return _validate(SCHEMA["$defs"][schema["$ref"].split("/")[-1]], value, path)
    if "anyOf" in schema:
        for alternative in schema["anyOf"]:
            try:
                _validate(alternative, value, path)
                return
            except CheckInError:
                pass
        fail("Value does not match an allowed shape.")
    kind = schema.get("type")
    checks = {"object": isinstance(value, dict), "array": isinstance(value, list),
              "string": isinstance(value, str), "boolean": type(value) is bool,
              "integer": type(value) is int, "number": type(value) in (int, float),
              "null": value is None}
    if kind and not any(checks[k] for k in (kind if isinstance(kind, list) else [kind])):
        fail("Unexpected value type.")
    if "const" in schema and (type(value) is not type(schema["const"]) or value != schema["const"]):
        fail("Value must equal the required constant.")
    if "enum" in schema and value not in schema["enum"]:
        fail("Select an allowed value.")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                raise CheckInError("invalid_input", path + "." + key, "Required field is missing.")
        for key, child in value.items():
            properties = schema.get("properties", {})
            extra = schema.get("additionalProperties", True)
            if key in properties:
                _validate(properties[key], child, path + "." + key)
            elif extra is False:
                fail("Unexpected field: " + key)
            elif isinstance(extra, dict):
                _validate(extra, child, path + "." + key)
        if len(value) > schema.get("maxProperties", math.inf):
            fail("Domain capacity reached; archive through CaseService before continuing.")
    if isinstance(value, list):
        if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", math.inf):
            fail("Array size is outside the allowed range.")
        if schema.get("uniqueItems") and len({canonical(item) for item in value}) != len(value):
            fail("Use unique selections.")
        for index, child in enumerate(value):
            _validate(schema.get("items", {}), child, f"{path}[{index}]")
    if isinstance(value, str):
        if not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", math.inf):
            fail("Text length is outside the allowed range.")
        if "pattern" in schema and not re.fullmatch(schema["pattern"], value):
            fail("Invalid identifier.")
        if schema.get("format") == "date-time":
            instant(value)
        if schema.get("format") == "iana-time-zone":
            try:
                ZoneInfo(value)
            except (ZoneInfoNotFoundError, ValueError):
                fail("Use an IANA time zone.")
    if type(value) in (int, float):
        if not math.isfinite(value) or not schema.get("minimum", -math.inf) <= value <= schema.get("maximum", math.inf):
            fail("Number is outside the allowed range.")
