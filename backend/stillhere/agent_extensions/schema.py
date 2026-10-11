"""Reviewed standalone proposal, inlined before SDK/provider transport."""

import copy
import json
from pathlib import Path

from ..contracts import InvalidInput, _validate, canonical_json

SCHEMA = json.loads((Path(__file__).resolve().parents[3] / "contracts/parallel/agent-extensions.schema.json").read_text())


def inline_schema(name):
    def expand(value):
        if type(value) is dict:
            if "$ref" in value:
                return expand(SCHEMA["$defs"][value["$ref"].removeprefix("#/$defs/")])
            return {key: expand(child) for key, child in value.items()}
        if type(value) is list:
            return [expand(child) for child in value]
        return value
    return expand(copy.deepcopy(SCHEMA["$defs"][name]))


def validate(name, value):
    bounded(value, 65536)
    _validate(inline_schema(name), value, "$")


def bounded(value, limit):
    # Check before serialization/recursive schema walking, including cyclic data.
    stack = [(value, 0)]
    nodes = characters = 0
    while stack:
        child, depth = stack.pop()
        nodes += 1
        if depth > 24 or nodes + len(stack) > 8192:
            raise InvalidInput("$", "Extension JSON exceeds nesting or node bounds.")
        if type(child) is dict:
            if len(child) + nodes + len(stack) > 8192 or any(type(key) is not str for key in child):
                raise InvalidInput("$", "Extension JSON requires bounded string keys.")
            characters += sum(len(key) for key in child)
            stack.extend((item, depth + 1) for item in child.values())
        elif type(child) is list:
            if len(child) + nodes + len(stack) > 8192:
                raise InvalidInput("$", "Extension JSON exceeds node bounds.")
            stack.extend((item, depth + 1) for item in child)
        elif type(child) is str:
            characters += len(child)
        elif child is not None and type(child) not in (bool, int, float):
            raise InvalidInput("$", "Extension JSON contains an unsupported value.")
        if characters > limit:
            raise InvalidInput("$", "Extension JSON exceeds its size bound.")
    try:
        encoded = canonical_json(value)
    except (ValueError, TypeError, RecursionError):
        raise InvalidInput("$", "Extension JSON must be finite and bounded.") from None
    if len(encoded) > limit:
        raise InvalidInput("$", "Extension JSON exceeds its size bound.")
