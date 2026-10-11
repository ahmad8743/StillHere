"""Bounded proposal helpers. No storage, environment, clock or provider access."""

import hashlib
from copy import deepcopy

from ..contracts import InvalidInput, canonical_json
from ..planner.validation import check, instant


def fail(field, message):
    raise InvalidInput(field, message)


def version(value):
    if type(value) is not int or value < 1:
        fail('$.input_case_version', 'Expected a positive integer case version.')
    return value


def ids(values, *, limit=256):
    if not isinstance(values, list) or len(values) > limit:
        fail('$.references', 'Expected a bounded reference list.')
    for value in values:
        check('Id', value)
    if len(set(values)) != len(values):
        fail('$.references', 'References must be unique.')
    return sorted(values)


def identity(kind, value):
    return kind + '_' + hashlib.sha256(canonical_json(value).encode()).hexdigest()[:48]


def detached(value):
    try:
        encoded = canonical_json(value)
    except (TypeError, ValueError, RecursionError):
        fail('$', 'Expected finite JSON input.')
    if len(encoded.encode()) > 2_000_000:
        fail('$', 'Boundary input exceeds the bounded size.')
    return deepcopy(value)


def times(occurred_at, received_at):
    if instant(occurred_at) > instant(received_at):
        fail('$.occurred_at', 'Report time cannot follow backend receipt time.')
