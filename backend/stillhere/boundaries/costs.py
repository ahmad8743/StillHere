"""Planner-to-finance reconciliation; all comparisons stay hypothetical."""

from copy import deepcopy
from zoneinfo import ZoneInfo

from ..finance import forecast_finances, validate_financial_scenario
from ..planner import export_action_costs
from ..planner.validation import actions
from .common import detached, fail, identity, ids, instant, version
from ..contracts import canonical_json


def reconcile_action_costs(plan, ledger, selected_action_ids, *, input_case_version,
                           as_of, time_zone, start_date):
    """Return reviewed alternatives or an all-or-nothing clarification proposal.

    Dated null amounts can be forecast as incomplete. Null dates are retained in
    the export and block comparison; no date or zero amount is invented. Only
    untouched same-rule/version planner-owned sibling costs can be removed.
    """
    plan, ledger = detached(plan), detached(ledger)
    version(input_case_version)
    selected = ids(selected_action_ids, limit=32)
    forecast_finances(ledger, start_date=start_date, time_zone=time_zone,
                      input_case_version=input_case_version)
    exported = export_action_costs(plan, input_case_version=input_case_version,
                                  as_of=as_of, time_zone=time_zone)
    mapping = actions(plan)
    paths = {path['action_id']: path for path in exported['paths']}
    if set(selected) - paths.keys():
        fail('$.selected_action_ids', 'Select owned actions from the authorized plan.')
    today = instant(as_of).astimezone(ZoneInfo(time_zone)).date().isoformat()
    existing = {item['id']: item for item in ledger['expense_commitments']}
    issues, alternatives = [], []
    removed = set()
    retained = set(existing)
    def issue(code, record_id):
        item = {'code': code, 'record_id': record_id}
        if item not in issues:
            issues.append(item)
    for identifier in selected:
        path = paths[identifier]
        if not path['selectable']:
            issue('action_not_selectable', identifier)
        # Exclusivity applies only to reciprocal same-rule/version alternatives.
        siblings = {other for other in path['alternative_ids'] if other in paths
                    and identifier in paths[other]['alternative_ids']
                    and (paths[other]['rule_id'], paths[other]['rule_version']) ==
                        (path['rule_id'], path['rule_version'])}
        if siblings & set(selected):
            issue('mutually_exclusive_alternatives', identifier)
        scope = siblings | {identifier}
        replacement = []
        for old_id, old in sorted(existing.items()):
            old_path = paths.get(old.get('action_id'))
            if old_path is None or old.get('action_id') not in scope:
                continue
            matching = next((cost for cost in old_path['commitments']
                             if cost['id'] == old_id and cost['planner_cost_id'] == old.get('planner_cost_id')), None)
            if old.get('origin') != 'recovery_planner':
                continue
            if matching is None and old_path['status'] in ('completed', 'skipped'):
                continue
            if matching is None:
                issue('planner_cost_binding_requires_review', old_id)
                continue
            protected = (old['essential'] or old_path['status'] in ('completed', 'skipped')
                         or (old.get('rule_id'), old.get('rule_version')) !=
                            (old_path['rule_id'], old_path['rule_version'])
                         or old.get('fulfilled_cents') != 0 or type(old.get('fulfilled_cents')) is not int
                         or old.get('fulfilled_cents_by_date')
                         or old.get('actual_event_ids') != []
                         or any(e.get('commitment_id') == old_id for e in ledger['actual_events'])
                         or any(old_id in s.get('commitment_ids', []) for s in ledger['support'])
                         or not old_path['is_current'] or old_path['input_freshness'] != 'current'
                         or old.get('date') is None or old['date'] < today
                         or old.get('due_at') is not None and instant(old['due_at']) < instant(as_of))
            if protected:
                # Protected spending stays; do not silently compare an exclusive
                # replacement that could obscure its remaining obligations.
                issue('protected_commitment_requires_reconciliation', old_id)
            elif old_id in removed:
                issue('overlapping_replacement', old_id)
            else:
                replacement.append(old_id)
                removed.add(old_id)
                retained.discard(old_id)
        costs = []
        for cost in path['commitments']:
            if cost['date'] is None:
                issue('cost_date_unknown', cost['id'])
            elif cost['date'] < max(today, start_date) or (cost['due_at'] is not None and instant(cost['due_at']) < instant(as_of)):
                issue('cost_timing_requires_reassessment', cost['id'])
            # Quote refresh of an untouched selected cost gets a distinct
            # hypothetical identity; finance forbids baseline ID collisions.
            if cost['id'] in existing:
                if cost['id'] not in replacement:
                    issue('selected_commitment_requires_reconciliation', cost['id'])
            item = deepcopy(cost)
            if item['due_at'] is None:
                item.pop('due_at')
            item.update(origin='recovery_planner', fulfilled_cents=0, actual_event_ids=[],
                        rule_id=path['rule_id'], rule_version=path['rule_version'])
            if cost['id'] in existing and cost['id'] in replacement:
                item['id'] = identity('scenario_cost', [input_case_version, plan['version'], item])
                item['planner_commitment_id'] = cost['id']
            costs.append(item)
        alternatives.append({'id': identifier, 'label': mapping[identifier]['title'],
                             'costs': costs, 'replaces_commitment_ids': sorted(replacement)})
    comparison = None
    scenario = {'id': 'boundary_comparison', 'label': 'Hypothetical action comparison', 'alternative_ids': selected}
    if not issues:
        comparison = validate_financial_scenario(ledger, scenario, start_date=start_date,
                           time_zone=time_zone, action_alternatives=alternatives)['comparison_ledger']
    return {'contract_version': '0.1', 'input_case_version': input_case_version,
            'plan_version': plan['version'], 'hypothetical': True,
            'state': 'needs_clarification' if issues else 'proposed',
            'cost_export': exported, 'selected_action_ids': selected,
            'retained_commitment_ids': sorted(existing if issues else retained),
            'remove_commitment_ids': [] if issues else sorted(removed),
            'action_alternatives': [] if issues else alternatives,
            'comparison_ledger': comparison,
            'issues': sorted(issues, key=lambda item: (item['code'], item['record_id']))}


def validate_saved_action_scenarios(plan, ledger, *, input_case_version, as_of,
                                    time_zone, start_date):
    """Check saved quotes against current domain inputs without refreshing them.

    Unavailable/stale/moved/changed costs require explicit scenario.set. Keeping
    the old snapshot is auditable; treating an expired cost as a free new quote
    is not. This function never stores or silently substitutes new assumptions.
    """
    plan, ledger = detached(plan), detached(ledger)
    actions(plan)
    forecast_finances(ledger, start_date=start_date, time_zone=time_zone,
                      input_case_version=version(input_case_version))
    scenarios = ledger.get('scenarios', [])
    if not isinstance(scenarios, list) or len(scenarios) > 3:
        fail('$.scenarios', 'At most three saved scenarios are supported.')
    from .validation import validate_finance_value
    for scenario in scenarios:
        validate_finance_value('StoredScenario', scenario)
    ids([scenario['id'] for scenario in scenarios], limit=3)
    issues = []
    for scenario in scenarios:
        selected = ids(scenario.get('alternative_ids', []), limit=32)
        if not selected:
            continue
        proposed = reconcile_action_costs(plan, ledger, selected,
            input_case_version=input_case_version, as_of=as_of,
            time_zone=time_zone, start_date=start_date)
        saved = scenario.get('action_cost_snapshot')
        if (proposed['state'] != 'proposed' or not isinstance(saved, list)
                or canonical_json(sorted(saved, key=lambda item: item['id'])) != canonical_json(proposed['action_alternatives'])):
            issues.append({'code': 'saved_scenario_costs_require_reassessment', 'record_id': scenario['id']})
    return {'contract_version': '0.1', 'input_case_version': version(input_case_version),
            'plan_version': plan['version'],
            'state': 'needs_clarification' if issues else 'current', 'issues': issues}
