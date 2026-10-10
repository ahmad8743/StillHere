"""Validate the deliberately small JSON Schema vocabulary used by C01."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SCHEMA = json.loads(
    (Path(__file__).resolve().parents[2] / "contracts/case-service.schema.json").read_text()
)
VERSION = "0.1"


class InvalidInput(ValueError):
    def __init__(self, field, message):
        self.field = field
        super().__init__(message)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def validate(name, value):
    """Use the same definitions clients consume; not a general JSON Schema engine."""
    try:
        canonical_json(value)
    except (TypeError, ValueError, RecursionError):
        raise InvalidInput("$", "Input must contain finite JSON values.") from None
    _validate(SCHEMA["$defs"][name], value, "$")


def _validate(schema, value, path):
    if "$ref" in schema:
        return _validate(SCHEMA["$defs"][schema["$ref"].removeprefix("#/$defs/")], value, path)
    if "anyOf" in schema:
        for alternative in schema["anyOf"]:
            try:
                _validate(alternative, value, path)
                break
            except InvalidInput:
                continue
        else:
            raise InvalidInput(path, "Value does not match an allowed shape.")
    expected = schema.get("type")
    checks = {
        "object": isinstance(value, dict), "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": type(value) in (int, float) and value % 1 == 0,
        "boolean": type(value) is bool, "null": value is None,
    }
    if expected and not any(checks[kind] for kind in ([expected] if isinstance(expected, str) else expected)):
        raise InvalidInput(path, f"Expected {expected}.")
    if "enum" in schema and value not in schema["enum"]:
        raise InvalidInput(path, "Value is not an allowed choice.")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                raise InvalidInput(f"{path}.{key}", "Required field is missing.")
        properties = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        for key, child in value.items():
            if key in properties:
                _validate(properties[key], child, f"{path}.{key}")
            elif extra is False:
                raise InvalidInput(f"{path}.{key}", "Unexpected field.")
            elif isinstance(extra, dict):
                _validate(extra, child, f"{path}.{key}")
    if isinstance(value, list):
        if len(value) > schema.get("maxItems", float("inf")):
            raise InvalidInput(path, "Too many selections.")
        if schema.get("uniqueItems") and len({canonical_json(child) for child in value}) != len(value):
            raise InvalidInput(path, "Selections must be unique.")
        for index, child in enumerate(value):
            _validate(schema.get("items", {}), child, f"{path}[{index}]")
    if isinstance(value, str):
        if not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", float("inf")):
            raise InvalidInput(path, "String length is outside the allowed range.")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            raise InvalidInput(path, "String does not match the required format.")
        try:
            if schema.get("format") == "date-time":
                instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if instant.tzinfo is None or instant.utcoffset().total_seconds() != 0:
                    raise ValueError()
            if schema.get("format") == "iana-time-zone":
                ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError):
            raise InvalidInput(path, "Use a valid UTC instant or IANA time zone.") from None
    if type(value) in (int, float) and value < schema.get("minimum", float("-inf")):
        raise InvalidInput(path, "Integer is below the allowed minimum.")


def empty_case(case_id, time_zone, now):
    snapshot = {
        "contract_version": VERSION, "case_id": case_id, "case_version": 1,
        "updated_at": now, "time_zone": time_zone, "household_mode": "synthetic",
        "facts": {}, "needs": [], "evidence": [],
        "resources": {"state": "not_requested", "items": [], "notices": []},
        "plan": {"state": "not_requested", "version": 0, "actions": [], "blockers": [], "questions": []},
        "applications": [],
        "finance": {
            "state": "not_calculated",
            "ledger": {"money_sources": [], "actual_events": [], "expense_commitments": [], "aid": [], "support": []},
            "scenarios": [], "baseline": None, "input_case_version": 1, "computed_at": None,
        },
        "check_in": {"enrolled": False, "status": "not_enrolled", "schedule": None, "last_report": None, "attempts": []},
        "shared_location": None, "follow_ups": [], "conversation": {"turns": []},
        "components": [], "sources": [], "notices": [],
    }
    validate("CaseSnapshot", snapshot)
    return snapshot
