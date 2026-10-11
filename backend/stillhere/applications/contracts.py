"""Validate proposed C06 shapes without extending the shared/public schema."""

import json
from pathlib import Path

from ..contracts import InvalidInput, _validate as validate_primitive, canonical_json, validate as validate_shared

SCHEMA = json.loads((Path(__file__).resolve().parents[3] / 'contracts/parallel/applications.schema.json').read_text())


def validate(name, value):
    try:
        canonical_json(value)
    except (TypeError, ValueError, RecursionError):
        raise InvalidInput('$', 'Input must contain finite JSON values.') from None
    _walk(SCHEMA['$defs'][name], value, '$')


def _walk(schema, value, path):
    if '$ref' in schema:
        reference = schema['$ref']
        if reference.startswith('#/$defs/'):
            return _walk(SCHEMA['$defs'][reference.split('/')[-1]], value, path)
        if reference.startswith('../case-service.schema.json#/$defs/'):
            try:
                return validate_shared(reference.split('/')[-1], value)
            except InvalidInput as error:
                raise InvalidInput(path + error.field[1:], str(error)) from None
        raise ValueError('Unsupported schema reference.')
    if 'anyOf' in schema:
        for candidate in schema['anyOf']:
            try:
                _walk(candidate, value, path)
                return
            except InvalidInput:
                pass
        raise InvalidInput(path, 'Value does not match an allowed shape.')
    # Reuse C01's primitive/required/unknown-field checks, resolving children here.
    shallow = {k: v for k, v in schema.items() if k not in ('items', 'properties', 'additionalProperties')}
    shallow['properties'] = {key: {} for key in schema.get('properties', {})}
    extra = schema.get('additionalProperties', True)
    shallow['additionalProperties'] = False if extra is False else True
    validate_primitive(shallow, value, path)
    if isinstance(value, list):
        if len(value) < schema.get('minItems', 0):
            raise InvalidInput(path, 'Too few records.')
        for index, item in enumerate(value):
            _walk(schema.get('items', {}), item, f'{path}[{index}]')
    if isinstance(value, dict):
        for key, child in value.items():
            if key in schema.get('properties', {}):
                _walk(schema['properties'][key], child, f'{path}.{key}')
            elif isinstance(extra, dict):
                _walk(extra, child, f'{path}.{key}')
