"""Strict validation for the proposed planner boundary, separate from shared contracts."""

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from ..contracts import InvalidInput, canonical_json
from .plans import ORIGIN

DEFINITIONS = json.loads((Path(__file__).resolve().parents[3] /
                          "contracts/parallel/planner.schema.json").read_text())["$defs"]


def fail(field, message):
    raise InvalidInput(field, message)


def instant(value):
    check("PlannerInstant", value)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _check(schema, value, field):
    if "$ref" in schema:
        return _check(DEFINITIONS[schema["$ref"].split("/")[-1]], value, field)
    if "anyOf" in schema:
        for shape in schema["anyOf"]:
            try:
                _check(shape, value, field)
                return
            except InvalidInput:
                pass
        fail(field, "Value does not match an allowed shape.")
    kind = schema.get("type")
    kinds = kind if isinstance(kind, list) else [kind]
    types = {"null": value is None, "boolean": type(value) is bool,
             "integer": type(value) is int, "number": type(value) in (int, float),
             "string": isinstance(value, str), "object": isinstance(value, dict),
             "array": isinstance(value, list)}
    if kind and not any(types[k] for k in kinds):
        fail(field, "Value has an invalid type.")
    if "enum" in schema and not any(type(value) is type(v) and value == v for v in schema["enum"]):
        fail(field, "Value is not an allowed choice.")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        if any(k not in value for k in schema.get("required", [])):
            fail(field, "Required field is missing.")
        for key, child in value.items():
            if key in props:
                _check(props[key], child, field + "." + key)
            elif schema.get("additionalProperties") is False:
                fail(field, "Unexpected field.")
    if isinstance(value, list):
        if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", float("inf")):
            fail(field, "Collection size exceeds the bounded contract.")
        if schema.get("uniqueItems") and len({canonical_json(v) for v in value}) != len(value):
            fail(field, "Collection must contain unique values.")
        for child in value:
            _check(schema.get("items", {}), child, field + "[]")
    if isinstance(value, str):
        if not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", float("inf")):
            fail(field, "String length is invalid.")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            fail(field, "String format is invalid.")
        try:
            if schema.get("format") == "date":
                date.fromisoformat(value)
            if schema.get("format") == "date-time":
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
                    raise ValueError
        except ValueError:
            fail(field, "Use a valid calendar date or UTC instant.")
    if type(value) in (int, float) and not schema.get("minimum", -float("inf")) <= value <= schema.get("maximum", float("inf")):
        fail(field, "Number is outside the allowed range.")


def check(name, value):
    try:
        canonical_json(value)
    except (TypeError, ValueError, RecursionError):
        fail("$", "Input must contain finite JSON values.")
    _check(DEFINITIONS[name], value, "$")


def records(name, values, limit=128, key="id"):
    if not isinstance(values, list) or len(values) > limit:
        fail("$", "Expected a bounded record list.")
    for value in values:
        check(name, value)
    result = {value[key]: value for value in values}
    if len(result) != len(values):
        fail("$", "Record identities must be unique.")
    return result


def actions(plan):
    """Validate owned actions while preserving opaque actions from other domains."""
    check("PlannerPlan", plan)
    if not isinstance(plan, dict) or type(plan.get("version")) is not int or plan["version"] < 0:
        fail("$.plan", "Expected a versioned plan.")
    values = plan.get("actions")
    if not isinstance(values, list) or len(values) > 32:
        fail("$.plan.actions", "Expected at most 32 retained actions.")
    result = {}
    for action in values:
        if not isinstance(action, dict):
            fail("$.plan.actions", "Expected an action record.")
        check("Id", action.get("id"))
        if action["id"] in result:
            fail("$.plan.actions", "Action identities must be unique.")
        result[action["id"]] = action
        if action.get("origin") == ORIGIN:
            check("PlannerAction", action)
    return result


def owned(mapping, identifier):
    action = mapping.get(identifier)
    if action is None or action.get("origin") != ORIGIN:
        fail("$.action_id", "Select an owned planner action from this case.")
    return action


def current(action):
    return action["is_current"] and action["input_freshness"] == "current"


def scope_matches(record, action):
    return record["rule_id"] == action["rule_id"] and record["rule_version"] == action["rule_version"]


def usable(record, as_of):
    return (record["state"] in ("user_reported", "source_supported") and
            record["observed_at"] is not None and instant(record["observed_at"]) <= as_of and
            (record["expires_at"] is None or as_of < instant(record["expires_at"])))


def supported(record, action, node, as_of):
    """Attribution must name a current reviewed source for this exact requirement."""
    allowed = set(node["source_ids"]) & set(action["source_ids"])
    return record["state"] == "source_supported" and any(
        source["id"] in allowed and source["id"] in record["source_ids"] and
        source["freshness"] == "current" and
        instant(source["retrieved_at"]) <= as_of and instant(source["reviewed_at"]) <= as_of and
        (source["updated_at"] is None or instant(source["updated_at"]) <= as_of) and
        as_of < instant(source["expires_at"])
        for source in action["source_records"])
