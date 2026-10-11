"""Pure C06 functions: metadata and Boolean drafts, no external or durable effects.

Caller must authorize/project the case, select published rules and supply trusted
receipt records outside tool arguments. These functions cannot confer authority.
"""

import copy
from datetime import datetime

from ..contracts import InvalidInput, VERSION, canonical_json
from ..knowledge.rules import validate_result as validate_rules
from .contracts import validate

STAGE_RANK = {'draft': 0, 'ready_to_submit': 1, 'submitted': 2, 'under_review': 3,
              'needs_evidence': 3, 'approved': 4, 'denied': 4, 'withdrawn': 4}
TERMINAL = {'approved', 'denied', 'withdrawn'}


def _instant(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def _reject(field, message):
    raise InvalidInput(field, message)


def _index(records, field):
    try:
        indexed = {record['id']: record for record in records}
    except (KeyError, TypeError):
        _reject(field, 'Each record needs an identity.')
    if len(indexed) != len(records):
        _reject(field, 'Record identities must be unique.')
    return indexed


def _snapshot(snapshot):
    """Accept a full case but validate only the necessary, explicitly projected fields.

    Extra fields on facts/evidence/applications are rejected by their contracts;
    unrelated case and plan/action fields are excluded without being inspected.
    """
    keys = ('contract_version', 'case_id', 'case_version', 'facts', 'evidence', 'applications', 'sources')
    try:
        projection = {key: snapshot[key] for key in keys}
        action_keys = ('id', 'program_id', 'rule_id', 'rule_version', 'path_id', 'status', 'is_current', 'input_freshness')
        projection['plan'] = {'actions': [
            {key: action[key] for key in action_keys}
            for action in snapshot['plan']['actions'] if 'program_id' in action]}
    except (KeyError, TypeError):
        _reject('$.snapshot', 'A complete authorized application projection is required.')
    validate('AuthorizedApplicationSnapshot', projection)
    for key in ('evidence', 'applications', 'sources'):
        _index(projection[key], '$.snapshot.' + key)
    _index(projection['plan']['actions'], '$.snapshot.plan.actions')
    known_sources = {source['id'] for source in projection['sources']}
    for key, fact in projection['facts'].items():
        if not set(fact['source_ids']) <= known_sources:
            _reject('$.snapshot.facts.' + key, 'Fact attribution references an unknown source.')
    for record in projection['evidence']:
        if not set(record['source_ids']) <= known_sources:
            _reject('$.snapshot.evidence.source_ids', 'Evidence attribution references an unknown source.')
        if record['state'] in ('available', 'missing') and record['provenance'] not in ('user_reported', 'source_supported'):
            _reject('$.snapshot.evidence.provenance', 'Known availability needs reported or supported provenance.')
        if record['state'] == 'unknown' and record['provenance'] != 'unknown':
            _reject('$.snapshot.evidence.provenance', 'Unknown evidence must remain unknown.')
        if record['state'] in ('conflicting', 'stale') and record['provenance'] != record['state']:
            _reject('$.snapshot.evidence.provenance', 'Unresolved evidence must retain its provenance state.')
        if record['provenance'] == 'source_supported' and not record['source_ids']:
            _reject('$.snapshot.evidence.source_ids', 'Source-supported evidence requires attribution.')
    return projection


def _selection(snapshot, arguments, rule_result, now):
    validate('PrepareApplicationArguments', arguments)
    validate_rules(rule_result)
    query = rule_result['query']
    if query['input_case_version'] != snapshot['case_version']:
        _reject('$.rule_result.query.input_case_version', 'Rule input case version is stale.')
    if query['as_of'] != now:
        _reject('$.rule_result.query.as_of', 'Rules must be resolved at the caller-supplied operation time.')
    if query['program_id'] != arguments['program_id']:
        _reject('$.arguments.program_id', 'Rules must match the selected program.')
    issuer = snapshot['facts'].get('document_issuing_state', {})
    if (issuer.get('state') not in ('user_reported', 'source_supported')
            or issuer.get('observed_at') is None or _instant(issuer['observed_at']) > _instant(now)
            or issuer.get('value') != query['issuing_state']):
        _reject('$.snapshot.facts.document_issuing_state', 'Use an explicit current document issuing jurisdiction.')
    if rule_result['state'] != 'available':
        _reject('$.rule_result.state', 'Preparation requires current, unambiguous published rules; retain prior data on failure.')
    rule = rule_result['rules'][0]
    if rule['version'] != arguments['rule_version']:
        _reject('$.arguments.rule_version', 'Select the exact published rule version.')
    moment = _instant(now)
    if (not _instant(rule['reviewed_at']) <= moment < _instant(rule['review_expires_at'])
            or rule['effective_from'] is not None and moment < _instant(rule['effective_from'])
            or rule['effective_to'] is not None and moment >= _instant(rule['effective_to'])):
        _reject('$.rule_result.rules', 'Expired or future rules cannot prepare current content.')
    for source in rule_result['sources']:
        if (source['freshness'] != 'current'
                or not _instant(source['reviewed_at']) <= moment < _instant(source['expires_at'])):
            _reject('$.rule_result.sources', 'Rule sources must be current at the operation time.')
    paths = {path['id']: path for path in rule['paths']}
    if arguments['path_id'] not in paths:
        _reject('$.arguments.path_id', 'Path reference is not published in the selected rule.')
    actions = _index(snapshot['plan']['actions'], '$.snapshot.plan.actions')
    action = actions.get(arguments['action_id'])
    if action is None or any(action[k] != v for k, v in (
            ('program_id', rule['program_id']), ('rule_id', rule['id']),
            ('rule_version', rule['version']), ('path_id', arguments['path_id']))):
        _reject('$.arguments.action_id', 'Select a case action matching this published program, rule and path.')
    if not action['is_current'] or action['input_freshness'] != 'current' or action['status'] == 'skipped':
        _reject('$.arguments.action_id', 'Reassess removed, stale or skipped actions before preparation.')
    return rule, paths[arguments['path_id']]


def _agency_outcome(snapshot, application_id, rule, receipts, now):
    """Only caller-verified, household-specific records can support agency outcomes.

    A public page/source, user decision notice, task completion or draft is never
    a receipt. The caller is responsible for verification; schema labels alone
    cannot establish trust and these records must never be model arguments.
    """
    _index(receipts, '$.agency_receipts')
    sources = _index(snapshot['sources'], '$.snapshot.sources')
    applicable = []
    for receipt in receipts:
        validate('AgencyReceipt', receipt)
        if (receipt['case_id'] != snapshot['case_id'] or receipt['application_id'] != application_id
                or receipt['program_id'] != rule['program_id']):
            _reject('$.agency_receipts', 'Trusted receipts must be scoped to this case, application and program.')
        if not _instant(receipt['observed_at']) <= _instant(receipt['verified_at']) <= _instant(now):
            _reject('$.agency_receipts', 'Receipt observation and verification times must precede this operation.')
        for identifier in receipt['source_ids']:
            source = sources.get(identifier, {})
            if (source.get('verification_state') != 'agency_record_verified'
                    or source.get('data_mode') not in ('live', 'cached')
                    or source.get('issuer') != rule['issuer']
                    or source.get('scope') != {'case_id': snapshot['case_id'], 'application_id': application_id,
                                               'program_id': rule['program_id']}):
                _reject('$.agency_receipts.source_ids', 'Outcomes need verified household agency records, not public rule pages.')
        applicable.append(receipt)
    if not applicable:
        return None
    latest = max(_instant(record['observed_at']) for record in applicable)
    winners = [record for record in applicable if _instant(record['observed_at']) == latest]
    if len({record['stage'] for record in winners}) > 1:
        _reject('$.agency_receipts', 'Conflicting official outcomes require caller reconciliation.')
    return copy.deepcopy(sorted(winners, key=lambda record: record['id'])[-1])


def _fact_answer(fact, now):
    if not fact:
        return 'unknown', None, None, []
    state, observed, value = fact['state'], fact['observed_at'], fact['value']
    if state in ('unknown', 'conflicting', 'stale'):
        return state, None, observed, list(fact['source_ids'])
    if observed is None or _instant(observed) > _instant(now):
        return 'unknown', None, observed, list(fact['source_ids'])
    if type(value) is not bool:
        return 'unknown', None, observed, list(fact['source_ids'])
    if state == 'source_supported' and not fact['source_ids']:
        return 'unknown', None, observed, []
    return state, value, observed, list(fact['source_ids'])


def _leaf_answer(snapshot, requirement, now):
    key, kind = requirement['key'], requirement['kind']
    if kind in ('action', 'authority_confirmation'):
        # No unfinished dependency links or policy/household outcome inference.
        return 'unknown', None, None, [], []
    if kind == 'evidence':
        records = [record for record in snapshot['evidence'] if record['requirement_key'] == key]
        if not records:
            return 'unknown', None, None, [], []
        ids = [record['id'] for record in records]
        sources = sorted({source for record in records for source in record['source_ids']})
        states = {record['state'] for record in records}
        observed = max((record['observed_at'] for record in records if record['observed_at']), default=None)
        if 'conflicting' in states or {'available', 'missing'} <= states:
            return 'conflicting', None, observed, ids, sources
        if any(record['observed_at'] is None or _instant(record['observed_at']) > _instant(now) for record in records):
            return 'unknown', None, observed, ids, sources
        if 'stale' in states:
            return 'stale', None, observed, ids, sources
        if 'unknown' in states:
            return 'unknown', None, observed, ids, sources
        provenance = 'source_supported' if all(record['provenance'] == 'source_supported' for record in records) else 'user_reported'
        return provenance, states == {'available'}, observed, ids, sources
    state, value, observed, sources = _fact_answer(snapshot['facts'].get(key), now)
    return state, value, observed, [], sources


def _combine(operator, states):
    if operator == 'any_of' and 'satisfied' in states:
        return 'satisfied'
    if operator == 'all_of' and 'missing' in states:
        return 'missing'
    for unresolved in ('conflicting', 'stale', 'unknown'):
        if unresolved in states:
            return unresolved
    return 'satisfied' if operator == 'all_of' else 'missing'


def _content(snapshot, path, now):
    nodes = {node['id']: node for node in path['nodes']}
    evaluated, answers = {}, []

    def walk(identifier):
        if identifier in evaluated:
            return evaluated[identifier]['state']
        node = nodes[identifier]
        requirement = node['requirement']
        if requirement:
            provenance, value, observed, evidence_ids, fact_sources = _leaf_answer(snapshot, requirement, now)
            state = ('satisfied' if value is requirement['expected'] else 'missing') if value is not None else provenance
            answers.append({'node_id': identifier, 'fact_key': requirement['key'], 'label': requirement['label'],
                            'answer': 'Yes' if value is True else 'No' if value is False else '',
                            'state': provenance, 'observed_at': observed, 'evidence_ids': evidence_ids,
                            'source_ids': sorted(set(node['source_ids']) | set(fact_sources))})
        else:
            state = _combine(node['operator'], [walk(child) for child in node['children']])
            provenance, observed, evidence_ids, fact_sources = 'unknown', None, [], []
        evaluated[identifier] = {'node_id': identifier, 'operator': node['operator'], 'children': list(node['children']),
                                 'requirement': copy.deepcopy(requirement), 'state': state, 'provenance': provenance,
                                 'observed_at': observed, 'fact_key': requirement['key'] if requirement else None,
                                 'evidence_ids': evidence_ids, 'source_ids': sorted(set(node['source_ids']) | set(fact_sources))}
        return state

    walk(path['root_id'])
    return [evaluated[node['id']] for node in path['nodes']], answers


def _frontier(application):
    nodes = {item['node_id']: item for item in application['checklist']}
    def walk(identifier):
        node = nodes[identifier]
        if node['requirement']:
            return [node] if node['state'] != 'satisfied' else []
        if node['operator'] == 'any_of' and node['state'] == 'satisfied':
            return []
        active = node['children']
        if node['operator'] == 'any_of' and node['state'] != 'missing':
            active = [child for child in active if nodes[child]['state'] != 'missing']
        return [leaf for child in active for leaf in walk(child)]
    outstanding = walk(application['root_id'])
    return list({node['node_id']: node for node in outstanding}.values())


def _next_step(application):
    report, outcome = application['stage_report'], application['agency_outcome']
    sources = list(application['source_ids'])
    def step(kind, message, basis='preparation', nodes=()):
        return {'kind': kind, 'message': message, 'node_ids': [node['node_id'] for node in nodes],
                'evidence_ids': sorted({identifier for node in nodes for identifier in node['evidence_ids']}),
                'source_ids': sources, 'basis': basis}
    if outcome:
        sources = sorted(set(sources) | set(outcome['source_ids']))
        official = 'submitted' if outcome['stage'] == 'received' else outcome['stage']
        if report and report['stage'] != official:
            return step('clarify_stage', 'The household report and verified agency record differ. Review their times and clarify; neither record is overwritten.', 'agency_supported')
        if outcome['stage'] in TERMINAL:
            return step('review_agency_decision', 'Review the verified agency decision and its official instructions. No funds or eligibility determination are created here.', 'agency_supported')
        if outcome['stage'] == 'needs_evidence':
            return step('gather_evidence', 'Review the verified agency request and its official instructions; provide evidence only through the official service.', 'agency_supported', _frontier(application))
    if application['correspondence'] and application['correspondence'][-1]['kind'] in ('evidence_request', 'decision_notice'):
        return step('review_correspondence', 'Review the reported correspondence at the official service. A reported notice does not verify an agency decision.', 'user_reported')
    if report and (report['stage'] in TERMINAL
                   or report['stage'] in {'submitted', 'under_review'} and application['preparation_state'] != 'pending'):
        return step('check_reported_status', 'Check the status through the official service. This stage is household-reported; agency receipt or decision remains separately recorded.', 'user_reported')
    outstanding = _frontier(application)
    # Later evidence is visible but does not block the preparation/start phase.
    starting = [node for node in outstanding if node['requirement']['timing'] == 'before_start']
    if any(node['state'] in ('conflicting', 'stale') for node in starting):
        return step('clarify_evidence', 'Clarify conflicting or stale evidence availability before relying on this draft.', nodes=starting)
    if any(node['state'] == 'missing' for node in starting):
        return step('gather_evidence', 'Review missing starting evidence and source-supported alternatives with the issuing agency.', nodes=starting)
    if starting:
        return step('confirm_requirements', 'Confirm unresolved starting requirements with the issuing agency. Unknown answers remain blank.', nodes=starting)
    if ((report and report['stage'] == 'needs_evidence')
            or (outcome and outcome['stage'] == 'needs_evidence')):
        return step('gather_evidence', 'Review requested evidence and the official instructions; provide it only through the official service.',
                    'agency_supported' if outcome else 'user_reported', outstanding)
    if outcome and outcome['stage'] in ('received', 'under_review'):
        return step('check_agency_status', 'Check the next step through the official service using the separately verified agency record.', 'agency_supported')
    if report and report['stage'] in ('submitted', 'under_review'):
        return step('check_reported_status', 'Check the household-reported application status at the official service.', 'user_reported')
    return step('review_draft', 'Review the draft and confirm full applicable requirements at the official service. Published coverage is partial; the household performs any external submission.')


def _script(application, rule, path):
    sources = list(rule['source_ids'])
    lines = [{'kind': 'opening', 'text': 'I am preparing for this application route and would like to confirm its requirements.',
              'node_ids': [], 'source_ids': sources}]
    for node in _frontier(application):
        requirement = node['requirement']
        timing = {'before_start': 'before starting', 'during_application': 'during the application', 'before_receipt': 'before receiving assistance'}[requirement['timing']]
        lines.append({'kind': 'question', 'text': 'Please confirm ' + timing + ': ' + requirement['label'] + '. Which accepted alternatives are available?',
                      'node_ids': [node['node_id']], 'source_ids': list(node['source_ids'])})
    lines.append({'kind': 'review', 'text': 'Please confirm the complete requirements, current fees, timing, and the official next step. I will enter any identity details only through the official service.',
                  'node_ids': [], 'source_ids': sources})
    return lines


def prepare_application(snapshot, arguments, rule_result, *, prepared_at, agency_receipts=()):
    """Return a source-attributed draft proposal; never mark an external submission.

    Raises InvalidInput for stale/unavailable rules or invalid references. The
    returned record can be committed only after CaseService validates it again.
    """
    snapshot = _snapshot(snapshot)
    receipts = list(agency_receipts)
    validate('PrepareApplicationInput', {'snapshot': snapshot, 'arguments': arguments, 'rule_result': rule_result,
                                        'prepared_at': prepared_at, 'agency_receipts': receipts})
    if any(record['id'] == arguments['application_id'] for record in snapshot['applications']):
        _reject('$.arguments.application_id', 'Application already exists; use its update path to preserve history.')
    rule, path = _selection(snapshot, arguments, rule_result, prepared_at)
    checklist, answers = _content(snapshot, path, prepared_at)
    application = {'id': arguments['application_id'], 'action_id': arguments['action_id'], 'program_id': rule['program_id'],
                   'rule_id': rule['id'], 'rule_version': rule['version'], 'path_id': path['id'], 'root_id': path['root_id'],
                   'official_url': path['official_url'], 'input_case_version': snapshot['case_version'], 'prepared_at': prepared_at,
                   'preparation_state': 'provisional', 'stage_report': None,
                   'agency_outcome': _agency_outcome(snapshot, arguments['application_id'], rule, receipts, prepared_at),
                   'checklist': checklist, 'draft_answers': answers, 'correspondence': [], 'history': [], 'source_ids': list(rule['source_ids'])}
    application['next_step'] = _next_step(application)
    application['call_script'] = _script(application, rule, path)
    result = {'contract_version': VERSION, 'input_case_version': snapshot['case_version'], 'application': application,
              'sources': copy.deepcopy(rule_result['sources']), 'household_eligibility': 'unknown', 'external_submission': False}
    validate('ApplicationPreparationResult', result)
    return result


def _transition(application, change, event_id, occurred_at, received_at):
    previous = application['stage_report']
    correction = change['corrects_event_id']
    if correction is not None:
        if previous is None or correction != previous['event_id']:
            _reject('$.arguments.stage_change.corrects_event_id', 'A correction must reference the active stage report event.')
    elif previous:
        old, new = previous['stage'], change['stage']
        if _instant(occurred_at) < _instant(previous['observed_at']):
            _reject('$.occurred_at', 'An older report requires an explicit stage correction.')
        if old != new and (old in TERMINAL or STAGE_RANK[new] < STAGE_RANK[old] and not (old == 'needs_evidence' and new == 'submitted')):
            _reject('$.arguments.stage_change', 'Backward or terminal-stage changes require an explicit correction reference.')
    return {**copy.deepcopy(change), 'event_id': event_id, 'observed_at': occurred_at, 'received_at': received_at,
            'provenance': 'user_reported'}



def _validate_saved(application, snapshot, rule, path):
    nodes = {node['id']: node for node in path['nodes']}
    items = {item['node_id']: item for item in application['checklist']}
    if (application['root_id'] != path['root_id'] or set(items) != set(nodes)
            or len(items) != len(application['checklist']) or application['source_ids'] != rule['source_ids']):
        _reject('$.application.checklist', 'Saved checklist must reference the selected published graph.')
    evidence = _index(snapshot['evidence'], '$.snapshot.evidence')
    source_ids = {source['id'] for source in snapshot['sources']} | set(rule['source_ids'])
    for identifier, item in items.items():
        node = nodes[identifier]
        if (item['operator'] != node['operator'] or item['children'] != node['children']
                or item['requirement'] != node['requirement']
                or not set(item['source_ids']) <= source_ids
                or any(ref not in evidence or not node['requirement']
                       or evidence[ref]['requirement_key'] != node['requirement']['key'] for ref in item['evidence_ids'])):
            _reject('$.application.checklist', 'Saved requirement, evidence or source reference is invalid.')
    events = {entry['event_id']: entry for entry in application['history']}
    if len(events) != len(application['history']):
        _reject('$.application.history', 'History event identities must be unique.')
    report = application['stage_report']
    reports = [entry['stage_change'] for entry in application['history'] if entry['stage_change']]
    if report != (reports[-1] if reports else None):
        _reject('$.application.stage_report', 'Active report must match the latest stage history.')
    seen_reports = set()
    for entry in application['history']:
        if _instant(entry['observed_at']) > _instant(entry['received_at']):
            _reject('$.application.history', 'History observation time cannot follow receipt time.')
        change = entry['stage_change']
        if change:
            if (change['event_id'] != entry['event_id']
                    or change['observed_at'] != entry['observed_at'] or change['received_at'] != entry['received_at']
                    or change['corrects_event_id'] is not None and change['corrects_event_id'] not in seen_reports):
                _reject('$.application.history', 'Stage history needs valid event and correction references.')
            seen_reports.add(change['event_id'])
        if any(change['evidence_id'] not in evidence for change in entry['evidence_changes']):
            _reject('$.application.history', 'Historical evidence references must remain available.')
    _index(application['correspondence'], '$.application.correspondence')
    for record in application['correspondence']:
        if (record['event_id'] not in events or events[record['event_id']]['correspondence_id'] != record['id']
                or not set(record['evidence_ids']) <= set(evidence)):
            _reject('$.application.correspondence', 'Saved correspondence requires valid event and evidence references.')

def update_application(snapshot, arguments, rule_result, *, event_id, occurred_at, received_at, agency_receipts=()):
    """Propose application.update effects from explicit user intent, with no writes.

    Retry/version/access/audit enforcement remains CaseService's responsibility.
    No event IDs are generated, no identity contents or free-text notice bodies
    are accepted, and user reports never modify caller-verified agency receipts.
    """
    snapshot = _snapshot(snapshot)
    receipts = list(agency_receipts)
    validate('UpdateApplicationInput', {'snapshot': snapshot, 'arguments': arguments, 'rule_result': rule_result,
                                      'event_id': event_id, 'occurred_at': occurred_at, 'received_at': received_at,
                                      'agency_receipts': receipts})
    if _instant(occurred_at) > _instant(received_at):
        _reject('$.occurred_at', 'Reported time cannot follow server receipt time.')
    if not any(key in arguments for key in ('stage_change', 'correspondence')) and not arguments.get('evidence_changes'):
        _reject('$.arguments', 'Provide a stage report, correspondence record or evidence change.')
    applications = _index(snapshot['applications'], '$.snapshot.applications')
    prior = applications.get(arguments['application_id'])
    if prior is None:
        _reject('$.arguments.application_id', 'Application reference is not in the authorized case.')
    if any(entry['event_id'] == event_id for entry in prior['history']):
        _reject('$.event_id', 'Resolve accepted event replay in CaseService before calling this pure transition.')
    if len(prior['history']) >= 64:
        _reject('$.application.history', 'History capacity reached; no prior corrections may be dropped.')
    selection = {'application_id': prior['id'], 'action_id': prior['action_id'], 'program_id': prior['program_id'],
                 'rule_version': prior['rule_version'], 'path_id': prior['path_id']}
    rule, path = _selection(snapshot, selection, rule_result, received_at)
    if prior['rule_id'] != rule['id'] or prior['official_url'] != path['official_url']:
        _reject('$.application', 'Saved application must match its published reference.')
    _validate_saved(prior, snapshot, rule, path)
    if _instant(received_at) < _instant(prior['prepared_at']):
        _reject('$.received_at', 'Operation time cannot precede the saved preparation.')
    expected_checklist, expected_answers = _content(snapshot, path, received_at)
    # Persisted derived content is always regenerated, never accepted as truth.
    application = copy.deepcopy(prior)
    application.update(checklist=expected_checklist, draft_answers=expected_answers)
    evidence = copy.deepcopy(snapshot['evidence'])
    records = _index(evidence, '$.snapshot.evidence')
    valid_keys = {node['requirement']['key'] for node in path['nodes']
                  if node['requirement'] and node['requirement']['kind'] == 'evidence'}
    changes = arguments.get('evidence_changes', [])
    if len({change['evidence_id'] for change in changes}) != len(changes):
        _reject('$.arguments.evidence_changes', 'Each evidence identity may be changed once per event.')
    for change in changes:
        record = records.get(change['evidence_id'])
        if record is None or record['requirement_key'] not in valid_keys:
            _reject('$.arguments.evidence_changes', 'Evidence changes must reference this application path in the authorized case.')
        if record['observed_at'] and _instant(occurred_at) < _instant(record['observed_at']):
            _reject('$.arguments.evidence_changes', 'Older evidence reports require caller reconciliation before updating.')
        state = change['state']
        record.update(state=state, provenance=state if state in ('unknown', 'conflicting', 'stale') else 'user_reported',
                      observed_at=occurred_at, source_ids=[])
    next_snapshot = {**snapshot, 'evidence': evidence}
    application['checklist'], application['draft_answers'] = _content(next_snapshot, path, received_at)
    report = None
    if 'stage_change' in arguments:
        report = _transition(application, arguments['stage_change'], event_id, occurred_at, received_at)
        application['stage_report'] = report
    correspondence_id = None
    if 'correspondence' in arguments:
        correspondence = arguments['correspondence']
        if any(record['id'] == correspondence['id'] for record in application['correspondence']):
            _reject('$.arguments.correspondence.id', 'Correspondence identity is already recorded.')
        if len(application['correspondence']) >= 32:
            _reject('$.application.correspondence', 'Correspondence capacity reached; prior records may not be dropped.')
        if any(identifier not in records or records[identifier]['requirement_key'] not in valid_keys for identifier in correspondence['evidence_ids']):
            _reject('$.arguments.correspondence.evidence_ids', 'Correspondence must reference evidence for this application.')
        correspondence_id = correspondence['id']
        application['correspondence'].append({**copy.deepcopy(correspondence), 'event_id': event_id,
                                              'observed_at': occurred_at, 'received_at': received_at, 'provenance': 'user_reported'})
        application['correspondence'].sort(key=lambda record: (record['observed_at'], record['id']))
    outcome = _agency_outcome(snapshot, prior['id'], rule, receipts, received_at)
    if prior['agency_outcome'] is not None and not any(canonical_json(prior['agency_outcome']) == canonical_json(receipt) for receipt in receipts):
        _reject('$.agency_receipts', 'Caller must revalidate and retain the prior agency receipt; reports cannot erase it.')
    application['agency_outcome'] = outcome
    application['history'].append({'event_id': event_id, 'observed_at': occurred_at, 'received_at': received_at,
                                   'stage_change': report, 'correspondence_id': correspondence_id, 'evidence_changes': copy.deepcopy(changes)})
    application.update(input_case_version=snapshot['case_version'], prepared_at=received_at,
                       preparation_state='pending' if changes else 'provisional')
    application['next_step'] = _next_step(application)
    application['call_script'] = _script(application, rule, path)
    result = {'contract_version': VERSION, 'input_case_version': snapshot['case_version'], 'event_id': event_id,
              'application': application, 'evidence': evidence, 'changed_evidence_ids': [change['evidence_id'] for change in changes],
              'sources': copy.deepcopy(rule_result['sources']), 'requires_plan_reassessment': bool(changes),
              'household_eligibility': 'unknown', 'external_submission': False}
    validate('ApplicationUpdateResult', result)
    return result
