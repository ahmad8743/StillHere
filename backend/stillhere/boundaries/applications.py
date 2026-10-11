"""Preparation invalidation and honest report acceptance without current rules."""

from copy import deepcopy

from ..applications import update_application, validate
from ..applications.domain import _snapshot, _transition, _validate_saved
from .common import detached, fail, ids, times, version
from .trusted import merge_sources, select_trusted


def _saved(snapshot, application):
    """Validate retained identities/history against the retained graph only.

    This structural/audit check deliberately supplies no current policy claim.
    Current preparation still goes through the applications domain validator.
    """
    validate('ApplicationRecord', application)
    selected = next((a for a in snapshot['plan']['actions'] if a['id'] == application['action_id']), None)
    if selected is None or selected['program_id'] != application['program_id']:
        fail('$.application', 'Retained application must reference its authorized program action.')
    nodes = {item['node_id']: item for item in application['checklist']}
    root = application['root_id']
    visited, heights = set(), {}
    def walk(identifier, trail):
        if identifier not in nodes or identifier in trail or len(trail) >= 8:
            fail('$.application.checklist', 'Retained checklist must be a bounded acyclic graph.')
        if identifier in heights:
            if len(trail) + heights[identifier] > 8:
                fail('$.application.checklist', 'Retained graph supports at most eight levels.')
            return heights[identifier]
        item = nodes[identifier]
        if ((item['operator'] == 'requirement') != (item['requirement'] is not None)
                or (item['operator'] == 'requirement' and item['children'])
                or (item['operator'] != 'requirement' and not item['children'])):
            fail('$.application.checklist', 'Retained graph operators and predicates must agree.')
        visited.add(identifier)
        height = 1 + max((walk(child, trail | {identifier}) for child in item['children']), default=0)
        heights[identifier] = height
        return height
    walk(root, set())
    if visited != set(nodes):
        fail('$.application.checklist', 'All retained requirements must be reachable.')
    path = {'root_id': root, 'nodes': [{
        'id': item['node_id'], **{k: deepcopy(item[k]) for k in ('operator', 'children', 'requirement')}
    } for item in application['checklist']]}
    _validate_saved(application, snapshot, {'source_ids': application['source_ids']}, path)


def invalidate_applications(snapshot, *, target_case_version, changed_fact_keys=None,
                            changed_rule_ids=None, changed_evidence_ids=None, changed_source_ids=None):
    """Preserve reports/evidence observations; mark only relevant preparation pending.

    An availability report does not expire merely because acceptance policy
    changes. affected_evidence_ids identifies records needing acceptance review;
    their reported availability/provenance is retained unchanged.
    """
    snapshot = _snapshot(detached(snapshot))
    version(snapshot['case_version'])
    version(target_case_version)
    if target_case_version < snapshot['case_version']:
        fail('$.target_case_version', 'Invalidation cannot target an older case version.')
    facts = set(ids(changed_fact_keys or []))
    rules = set(ids(changed_rule_ids or []))
    evidence = set(ids(changed_evidence_ids or [], limit=128))
    sources = set(ids(changed_source_ids or []))
    if evidence - {e['id'] for e in snapshot['evidence']}:
        fail('$.changed_evidence_ids', 'Evidence changes must identify retained case records.')
    affected, review = [], set()
    result = deepcopy(snapshot['applications'])
    for app in result:
        _saved(snapshot, app)
        relevant_facts = {'document_issuing_state'} | {
            item['requirement']['key'] for item in app['checklist']
            if item['requirement'] and item['requirement']['kind'] == 'fact'}
        referenced = {eid for item in app['checklist'] for eid in item['evidence_ids']}
        evidence_keys = {item['requirement']['key'] for item in app['checklist']
                         if item['requirement'] and item['requirement']['kind'] == 'evidence'}
        # Include unlinked/newly available metadata sharing a published key.
        referenced |= {e['id'] for e in snapshot['evidence'] if e['requirement_key'] in evidence_keys}
        attributed = set(app['source_ids']) | {sid for item in app['checklist'] for sid in item['source_ids']}
        attributed |= {sid for answer in app['draft_answers'] for sid in answer['source_ids']}
        if facts & relevant_facts or app['rule_id'] in rules or evidence & referenced or sources & attributed:
            app['preparation_state'] = 'pending'
            affected.append(app['id'])
            review |= referenced
            # Draft/checklist remain retained content and explicitly pending.
            app['next_step'] = _pending_step(app)
            validate('ApplicationRecord', app)
    return {'contract_version': '0.1', 'input_case_version': snapshot['case_version'],
            'target_case_version': target_case_version, 'applications': result,
            'affected_application_ids': sorted(affected), 'affected_evidence_ids': sorted(review),
            'evidence': deepcopy(snapshot['evidence']), 'requires_plan_reassessment': bool(affected),
            'household_eligibility': 'unknown', 'external_submission': False}


def _pending_step(application):
    return {'kind': 'check_reported_status' if application['stage_report'] else 'confirm_requirements',
            'message': 'The report is retained. Preparation is pending current rule and evidence review; check the official service for current instructions.',
            'node_ids': [], 'evidence_ids': [], 'source_ids': list(application['source_ids']),
            'basis': 'user_reported' if application['stage_report'] else 'preparation'}


def report_application_only(snapshot, arguments, *, event_id, occurred_at, received_at):
    """Accept stage/correspondence reports without claiming current preparation.

    Evidence edits need current path validation and return clarification through
    CaseService; this bounded path accepts no agency records or policy changes.
    """
    snapshot = _snapshot(detached(snapshot))
    version(snapshot['case_version'])
    arguments = detached(arguments)
    validate('UpdateApplicationArguments', arguments)
    ids([event_id])
    times(occurred_at, received_at)
    if arguments.get('evidence_changes'):
        fail('$.evidence_changes', 'Evidence edits require current rules; submit the stage report separately.')
    if not any(key in arguments for key in ('stage_change', 'correspondence')):
        fail('$.arguments', 'Supply an explicit stage or correspondence report.')
    prior = next((a for a in snapshot['applications'] if a['id'] == arguments['application_id']), None)
    if prior is None:
        fail('$.application_id', 'Select a saved application from this case.')
    _saved(snapshot, prior)
    from ..planner.validation import instant
    if instant(received_at) < instant(prior['prepared_at']):
        fail('$.received_at', 'Backend receipt cannot precede saved preparation.')
    if any(instant(received_at) < instant(entry['received_at']) for entry in prior['history']):
        fail('$.received_at', 'Backend receipt cannot precede retained reports.')
    if any(entry['event_id'] == event_id for entry in prior['history']):
        fail('$.event_id', 'CaseService must resolve accepted replay first.')
    if len(prior['history']) >= 64:
        fail('$.history', 'History capacity reached; retain all original reports.')
    app = deepcopy(prior)
    report = None
    if 'stage_change' in arguments:
        report = _transition(prior, arguments['stage_change'], event_id, occurred_at, received_at)
        app['stage_report'] = report
    correspondence_id = None
    if 'correspondence' in arguments:
        record = arguments['correspondence']
        if len(app['correspondence']) >= 32 or any(c['id'] == record['id'] for c in app['correspondence']):
            fail('$.correspondence', 'Correspondence identity/capacity requires backend reconciliation.')
        allowed = {eid for item in prior['checklist'] for eid in item['evidence_ids']}
        if set(record['evidence_ids']) - allowed:
            fail('$.correspondence.evidence_ids', 'Correspondence must reference retained application evidence.')
        correspondence_id = record['id']
        app['correspondence'].append({**record, 'event_id': event_id, 'observed_at': occurred_at,
                                      'received_at': received_at, 'provenance': 'user_reported'})
        app['correspondence'].sort(key=lambda c: (c['observed_at'], c['id']))
    app['history'].append({'event_id': event_id, 'observed_at': occurred_at, 'received_at': received_at,
                           'stage_change': report, 'correspondence_id': correspondence_id, 'evidence_changes': []})
    app['preparation_state'] = 'pending'
    # input_case_version/prepared_at describe retained preparation, not this report.
    app['next_step'] = _pending_step(app)
    _saved(snapshot, app)
    return {'contract_version': '0.1', 'input_case_version': snapshot['case_version'],
            'event_id': event_id, 'application': app, 'evidence': deepcopy(snapshot['evidence']),
            'changed_evidence_ids': [], 'sources': [], 'requires_plan_reassessment': False,
            'household_eligibility': 'unknown', 'external_submission': False,
            'mode': 'report_only', 'preparation_refreshed': False}


def update_application_boundary(snapshot, arguments, rule_result, *, event_id,
                                occurred_at, received_at, receipt_ids=None, trusted_boundary=None):
    """Current preparation requires domain validation; failure fallback is explicit.

    Only an absent/nonavailable rule result chooses report-only. Malformed or
    mis-scoped available rules are rejected, never swallowed as an outage.
    """
    snapshot = _snapshot(detached(snapshot))
    version(snapshot['case_version'])
    if not isinstance(arguments, dict):
        fail('$.arguments', 'Expected application update arguments.')
    if (rule_result is None or isinstance(rule_result, dict) and rule_result.get('state') != 'available') and receipt_ids:
        fail('$.receipt_ids', 'New agency verification requires current rules and the trusted backend path.')
    if rule_result is None:
        return report_application_only(snapshot, arguments, event_id=event_id,
                                       occurred_at=occurred_at, received_at=received_at)
    from ..knowledge.rules import validate_result
    validate_result(rule_result)
    if rule_result['state'] != 'available':
        query = rule_result['query']
        app = next((a for a in snapshot['applications'] if a['id'] == arguments.get('application_id')), None)
        if (app is None or query['input_case_version'] != snapshot['case_version']
                or query['program_id'] != app['program_id'] or query['as_of'] != received_at
                or query['requested_version'] not in (None, app['rule_version'])):
            fail('$.rule_result', 'Unavailable rule result must match the operation scope and time.')
        return report_application_only(snapshot, arguments, event_id=event_id,
                                       occurred_at=occurred_at, received_at=received_at)
    selected = select_trusted(trusted_boundary, snapshot['case_id'], 'application_receipt', receipt_ids or [])
    from ..planner.validation import instant
    now = instant(received_at)
    trusted_sources = {source['id']: source for source in selected['sources']}
    for receipt in selected['records']:
        for source_id in receipt['source_ids']:
            source = trusted_sources.get(source_id)
            if source is None or source.get('freshness') != 'current' or source.get('retrieved_at') is None:
                fail('$.trusted_boundary.sources', 'Agency receipts require current backend-selected source records.')
            if (instant(source['retrieved_at']) > now
                    or source.get('updated_at') is not None and instant(source['updated_at']) > now
                    or source.get('expires_at') is not None and now >= instant(source['expires_at'])):
                fail('$.trusted_boundary.sources', 'Agency source records must be current at the operation time.')
    snapshot['sources'] = merge_sources(snapshot['sources'], selected['sources'])
    result = update_application(snapshot, arguments, detached(rule_result), event_id=event_id,
                 occurred_at=occurred_at, received_at=received_at, agency_receipts=selected['records'])
    result.update(mode='current_rules', preparation_refreshed=True)
    return result
