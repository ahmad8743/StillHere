"""Versioned advisory effects and dependency/correction assembly."""

from ..finance import finance_reassessment, forecast_finances
from ..planner import correct_completion, order_actions, resolve_dependencies
from ..planner.validation import actions, check
from .common import detached, fail, identity, ids, version
from .trusted import select_trusted


def finance_planner_request(plan, ledger, previous_forecasts, *, case_id,
                            input_case_version, changed_record_ids, start_date, time_zone):
    """Calculate authoritative current finance before translating its advice.

    previous_forecasts is an accepted backend calculation, never model output.
    The effect ID hashes versions, exact current calculation and changed refs;
    input ordering does not produce duplicate work. No action is completed here.
    """
    plan, ledger, previous = detached(plan), detached(ledger), detached(previous_forecasts)
    check('Id', case_id)
    version(input_case_version)
    mapping = actions(plan)
    if any(a.get('origin') == 'recovery_planner' and a['input_case_version'] > input_case_version for a in mapping.values()):
        fail('$.plan', 'Plan inputs cannot come from a later case version.')
    changed = ids(changed_record_ids)
    collections = ('money_sources', 'actual_events', 'expense_commitments', 'aid', 'support', 'scenarios')
    known = {collection + ':' + item['id'] for collection in collections for item in ledger.get(collection, [])}
    if set(changed) - known:
        fail('$.changed_record_ids', 'Changed references must identify current finance records.')
    current = forecast_finances(ledger, start_date=start_date, time_zone=time_zone,
                               input_case_version=input_case_version)
    if previous is not None:
        from .validation import validate_finance_bundle
        validate_finance_bundle(previous)
        if previous['input_case_version'] > input_case_version:
            fail('$.previous_forecasts', 'Previous calculation cannot be from a later version.')
    decision = finance_reassessment(previous, current, changed_record_ids=changed)
    # Restriction/accessibility changes can leave totals unchanged. Explicit
    # accounting references still request route review, including a first run.
    if any(ref.startswith(('money_sources:', 'actual_events:')) for ref in changed):
        decision['required'] = True
        decision['reasons'].append('financial_records_changed')
    # Money/gap changes potentially affect every active route; conservative,
    # explicit scope is preferable to guessing which route a household chose.
    affected = sorted(a['id'] for a in mapping.values() if a.get('origin') == 'recovery_planner'
                      and a['status'] not in ('completed', 'skipped') and a['is_current']) if decision['required'] else []
    preserved = sorted(a['id'] for a in mapping.values() if a['status'] in ('completed', 'skipped'))
    request = {'contract_version': '0.1', 'case_id': case_id, 'input_case_version': input_case_version,
               'plan_version': plan['version'], 'required': decision['required'],
               'reasons': sorted(set(decision['reasons'])), 'changed_record_ids': changed,
               'affected_action_ids': affected, 'preserved_action_ids': preserved,
               'preserve_completed_actions': True, 'forecast': current}
    request['request_id'] = identity('planner_request', request)
    return request


def assemble_dependencies(plan, *, case_id, input_case_version, links, evidence,
                          as_of, confirmation_ids=None, trusted_boundary=None,
                          priorities=None, deadlines=None):
    """Typed graph validation and ordering; trust never comes from record labels."""
    selected = select_trusted(trusted_boundary, case_id, 'planner_confirmation', confirmation_ids or [])
    # Planner source support must already be in the backend-selected action's
    # reviewed source_records. An arbitrary returned source cannot widen it.
    resolved = resolve_dependencies(detached(plan), case_id=case_id, input_case_version=input_case_version,
                  links=detached(links), evidence=detached(evidence),
                  confirmations=selected['records'], as_of=as_of)
    return order_actions(resolved, priorities=detached(priorities), deadlines=detached(deadlines))


def propose_completion_correction(plan, payload, *, event_id, occurred_at,
                                   received_at, input_case_version):
    plan, payload = detached(plan), detached(payload)
    corrected = correct_completion(plan, payload, event_id=event_id, occurred_at=occurred_at,
                  received_at=received_at, input_case_version=input_case_version)
    affected = sorted(a['id'] for a in corrected['actions'] if a != next(
        old for old in plan['actions'] if old['id'] == a['id']))
    return {'contract_version': '0.1', 'event_id': event_id, 'input_case_version': input_case_version,
            'plan_version': plan['version'], 'target_case_version': input_case_version + 1,
            'plan': corrected, 'affected_action_ids': affected,
            'preserved_action_ids': sorted(a['id'] for a in plan['actions'] if a['status'] in ('completed', 'skipped')
                                          and a['id'] != payload['action_id']),
            'financial_reversal': False}
