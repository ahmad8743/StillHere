"""Backend-injected selection, never deserialized from household/model input."""

from ..applications import validate as validate_application
from ..planner.validation import records
from .common import detached, fail, ids


class TrustedRecordBoundary:
    """The resolver is a backend-configured capability, not a trust label.

    resolver(case_id, kind, record_ids) -> {records: [...], sources: [...]}
    must select already authorized/verified durable records. No provider is
    implemented here. With no resolver, nonempty requests fail closed. Neither
    this class nor its resolver belongs in a tool schema or household payload.
    """

    def __init__(self, *, resolver=None):
        if resolver is not None and not callable(resolver):
            fail('$.trusted_boundary', 'A backend callable is required.')
        self._resolver = resolver

    def select(self, case_id, kind, record_ids):
        ids([case_id])
        selected = ids(record_ids, limit=128)
        if kind not in ('planner_confirmation', 'application_receipt'):
            fail('$.trusted_boundary', 'Unsupported trusted record kind.')
        if not selected:
            return {'records': [], 'sources': []}
        if self._resolver is None:
            fail('$.trusted_boundary', 'Trusted record acquisition is unavailable.')
        result = detached(self._resolver(case_id, kind, list(selected)))
        if not isinstance(result, dict) or set(result) != {'records', 'sources'}:
            fail('$.trusted_boundary', 'Backend selection must return records and sources.')
        values = result['records']
        if kind == 'planner_confirmation':
            records('PlannerConfirmation', values)
        else:
            if not isinstance(values, list) or len(values) > 128:
                fail('$.trusted_boundary', 'Expected bounded trusted receipts.')
            for record in values:
                validate_application('AgencyReceipt', record)
        if ids([record['id'] for record in values], limit=128) != selected:
            fail('$.trusted_boundary', 'Backend selection must match every requested identity.')
        if any(record['case_id'] != case_id for record in values):
            fail('$.trusted_boundary', 'Trusted records must belong to the authorized case.')
        if not isinstance(result['sources'], list) or len(result['sources']) > 128:
            fail('$.trusted_boundary', 'Expected bounded source records.')
        if any(not isinstance(source, dict) for source in result['sources']):
            fail('$.trusted_boundary', 'Expected source objects.')
        ids([source.get('id') for source in result['sources']], limit=128)
        return result


def select_trusted(boundary, case_id, kind, record_ids):
    if boundary is None:
        boundary = TrustedRecordBoundary()
    if type(boundary) is not TrustedRecordBoundary:
        fail('$.trusted_boundary', 'Use a backend-injected trusted record boundary.')
    return boundary.select(case_id, kind, record_ids)


def merge_sources(existing, trusted):
    merged = {source['id']: detached(source) for source in existing}
    if len(merged) != len(existing):
        fail('$.sources', 'Source identities must be unique.')
    for source in trusted:
        if source['id'] in merged and merged[source['id']] != source:
            fail('$.sources', 'Resolve conflicting source identities in the backend.')
        merged[source['id']] = detached(source)
    return list(merged.values())
