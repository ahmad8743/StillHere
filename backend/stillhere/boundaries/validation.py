"""Standalone proposed schema validation; domain functions remain authoritative."""

import json
from pathlib import Path

from ..contracts import _validate
from .common import fail

ROOT = Path(__file__).resolve().parents[3] / 'contracts'


def _schema(name):
    return json.loads((ROOT / name).read_text())


def _walk(schema, value, definitions, field='$'):
    from ..contracts import InvalidInput
    if '$ref' in schema:
        reference = schema['$ref']
        if reference.startswith('#/$defs/'):
            return _walk(definitions[reference.split('/')[-1]], value, definitions, field)
        file, definition = reference.split('#/$defs/')
        external = _schema(('parallel/' + file) if file != '../case-service.schema.json' else 'case-service.schema.json')
        return _walk(external['$defs'][definition], value, external['$defs'], field)
    if 'anyOf' in schema:
        for candidate in schema['anyOf']:
            try:
                _walk(candidate, value, definitions, field)
                return
            except InvalidInput:
                pass
        fail(field, 'Value does not match an allowed shape.')
    for child in schema.get('allOf', []):
        _walk(child, value, definitions, field)
    if 'oneOf' in schema:
        matches = 0
        for child in schema['oneOf']:
            try:
                _walk(child, value, definitions, field)
                matches += 1
            except InvalidInput:
                pass
        if matches != 1:
            fail(field, 'Value must match exactly one allowed shape.')
    if 'not' in schema:
        try:
            _walk(schema['not'], value, definitions, field)
        except InvalidInput:
            pass
        else:
            fail(field, 'Value matches a forbidden shape.')
    if 'if' in schema:
        try:
            _walk(schema['if'], value, definitions, field)
            branch = 'then'
        except InvalidInput:
            branch = 'else'
        _walk(schema.get(branch, {}), value, definitions, field)
    shallow = {k: v for k, v in schema.items() if k not in ('properties', 'items', 'additionalProperties',
                                                           'allOf', 'oneOf', 'if', 'then', 'else', 'not')}
    shallow['properties'] = {key: {} for key in schema.get('properties', {})}
    extra = schema.get('additionalProperties', True)
    shallow['additionalProperties'] = False if extra is False else True
    _validate(shallow, value, field)
    if schema.get('type') == 'integer' and type(value) is not int:
        fail(field, 'Expected an integer, not a float or Boolean.')
    if isinstance(value, dict):
        for key, child in value.items():
            candidate = schema.get('properties', {}).get(key, extra if isinstance(extra, dict) else {})
            _walk(candidate, child, definitions, field + '.' + key)
    if isinstance(value, list):
        for child in value:
            _walk(schema.get('items', {}), child, definitions, field + '[]')


def validate(name, value):
    from .common import detached
    detached(value)
    definitions = _schema('parallel/domain-boundaries.schema.json')['$defs']
    _walk(definitions[name], value, definitions)


def validate_finance_bundle(value):
    validate_finance_value('ForecastBundle', value)
    source = value['input_case_version']
    for projection in [value['baseline'], *value['scenarios']]:
        if projection['input_case_version'] != source:
            fail('$.previous_forecasts', 'Every projection must retain its calculation version.')


def validate_finance_value(name, value):
    definitions = _schema('parallel/finance.schema.json')['$defs']
    _walk(definitions[name], value, definitions)
