"""Synthetic remaining C05 slices, independent of finance, providers and persistence."""

import copy
import json
import unittest

from backend.stillhere.contracts import InvalidInput, empty_case
from backend.stillhere.knowledge.rules import ProgramRuleStore, build_query
from backend.stillhere.planner import (correct_completion, evaluate_options, export_action_costs,
    order_actions, propose_alternative_selection, resolve_dependencies, set_action_costs)
from backend.stillhere.planner.plans import revise_plan
from backend.stillhere.planner.validation import check

NOW = '2026-10-11T06:00:00Z'
LATER = '2026-10-11T07:00:00Z'
CASE = 'synthetic_case'


def node(identifier, kind='evidence', expected=True, source='synthetic_source'):
    return {'node_id': identifier, 'operator': 'requirement', 'children': [],
        'requirement': {'key': identifier, 'kind': kind, 'expected': expected,
            'label': 'Synthetic ' + identifier, 'timing': 'before_start', 'evidence_state': 'unknown'},
        'state': 'unknown', 'fact_state': 'missing', 'observed_at': None,
        'reason': 'fact_missing', 'source_ids': [source]}


def group(identifier, operator, children):
    return {'node_id': identifier, 'operator': operator, 'children': children, 'requirement': None,
        'state': 'unknown', 'fact_state': None, 'observed_at': None,
        'reason': 'and_or_evaluation', 'source_ids': ['synthetic_source']}


class BoundedPlannerTests(unittest.TestCase):
    def setUp(self):
        snapshot = empty_case(CASE, 'America/Chicago', NOW)
        snapshot['facts']['document_issuing_state'] = {'value': 'CO', 'state': 'user_reported',
            'observed_at': NOW, 'source_ids': []}
        rules = ProgramRuleStore().lookup(build_query(snapshot, {'program_id': 'co_state_id_replacement'}, NOW))
        evaluated = evaluate_options(snapshot, rules)
        self.plan = revise_plan(snapshot['plan'], evaluated, NOW, 'revision', 'a' * 64)
        for identifier, action in zip(('a', 'b'), self.plan['actions']):
            action.update(id=identifier, constraints=[], requirements=[node('proof')], blockers=[],
                questions=[{'node_id': None, 'fact_key': None, 'code': 'policy_coverage_partial',
                    'message': 'Partial synthetic policy.', 'source_ids': ['synthetic_source']}],
                source_ids=['synthetic_source'], alternative_ids=['b' if identifier == 'a' else 'a'])
            source = copy.deepcopy(action['source_records'][0])
            source.update(id='synthetic_source', retrieved_at='2026-10-10T00:00:00Z',
                reviewed_at='2026-10-10T00:00:00Z', expires_at='2026-11-01T00:00:00Z', freshness='current')
            action['source_records'] = [source]
        self.plan['blockers'] = []
        self.plan['questions'] = []

    def action(self, identifier='a', plan=None):
        return next(a for a in (plan or self.plan)['actions'] if a['id'] == identifier)

    def link(self, identifier='a', kind='evidence', target='proof_record', node_id='proof', link_id=None):
        action = self.action(identifier)
        target_action = self.action(target) if kind == 'action' and target in ('a', 'b') else None
        return {'id': link_id or 'link_' + identifier + '_' + node_id, 'action_id': identifier,
            'rule_id': action['rule_id'], 'rule_version': action['rule_version'], 'node_id': node_id,
            'kind': kind, 'target_id': target,
            'target_rule_id': target_action['rule_id'] if target_action else None,
            'target_rule_version': target_action['rule_version'] if target_action else None}

    def evidence(self, **overrides):
        return {'id': 'proof_record', 'case_id': CASE, 'key': 'proof', 'available': True,
            'state': 'user_reported', 'observed_at': NOW, 'expires_at': None, 'source_ids': [], **overrides}

    def confirmation(self, **overrides):
        action = self.action()
        return {'id': 'confirm', 'case_id': CASE, 'action_id': 'a', 'rule_id': action['rule_id'],
            'rule_version': action['rule_version'], 'node_id': 'confirmed', 'value': True,
            'state': 'source_supported', 'observed_at': NOW, 'expires_at': None,
            'source_ids': ['synthetic_source'], **overrides}

    def resolve(self, links=None, evidence=None, confirmations=None, plan=None, **kw):
        return resolve_dependencies(plan or self.plan, case_id=CASE, input_case_version=1,
            links=links or [], evidence=evidence or [], confirmations=confirmations or [], as_of=NOW, **kw)

    def complete(self, identifier='b', event='completion'):
        action = self.action(identifier)
        action['status'] = 'completed'
        action['history'] = [{'event_id': event, 'from_status': 'waiting', 'status': 'completed',
            'reason_code': None, 'occurred_at': NOW, 'received_at': NOW, 'provenance': 'user_reported'}]

    def cost(self, **kw):
        return {'id': 'fee', 'category': 'documents', 'amount_cents': 3500, 'date': '2026-10-12',
            'due_at': None, 'state': 'user_reported', 'observed_at': NOW, 'source_ids': [], 'essential': False, **kw}

    def cost_plan(self, amount=3500):
        updates = [{'action_id': a['id'], 'rule_id': a['rule_id'], 'rule_version': a['rule_version'],
            'items': [self.cost(amount_cents=amount)]} for a in self.plan['actions']]
        return set_action_costs(self.plan, updates, as_of=NOW)

    def export(self, plan=None):
        return export_action_costs(plan or self.plan, input_case_version=1, as_of=NOW, time_zone='America/Chicago')

    def commitment(self, path):
        return {**path['commitments'][0], 'origin': 'recovery_planner', 'fulfilled_cents': 0,
            'actual_event_ids': []}

    def correct(self, plan=None, **kw):
        return correct_completion(plan or self.plan, {'action_id': 'b', 'completion_event_id': 'completion',
            'reason_code': 'reported_in_error'}, occurred_at=LATER, received_at=LATER,
            event_id='correction', input_case_version=1, **kw)

    def test_evidence_available_and_missing_exact_predicate_preserve_unknown_eligibility(self):
        for available, expected in ((True, 'satisfied'), (False, 'unmet'), (None, 'unknown')):
            with self.subTest(available=available):
                result = self.resolve([self.link()], [self.evidence(available=available)])
                self.assertEqual(self.action(plan=result)['requirements'][0]['state'], expected)
                self.assertEqual(result['household_eligibility'], 'unknown')
                self.assertEqual(result['state'], 'provisional')
                self.assertNotEqual(self.action(plan=result)['status'], 'ready')

    def test_evidence_unknown_stale_conflicting_expired_and_future_do_not_satisfy(self):
        for updates in ({'state': 'unknown'}, {'state': 'conflicting'}, {'state': 'stale'},
                        {'observed_at': None}, {'observed_at': LATER}, {'expires_at': NOW},
                        {'key': 'another_proof'}, {'state': 'source_supported', 'source_ids': ['wrong']}):
            with self.subTest(updates=updates):
                result = self.resolve([self.link()], [self.evidence(**updates)])
                self.assertEqual(self.action(plan=result)['requirements'][0]['state'], 'unknown')

    def test_explicit_negative_predicate_can_be_satisfied_by_missing_evidence(self):
        self.action()['requirements'][0]['requirement']['expected'] = False
        result = self.resolve([self.link()], [self.evidence(available=False)])
        self.assertEqual(self.action(plan=result)['requirements'][0]['state'], 'satisfied')

    def test_typed_evidence_never_infers_from_title_or_unlinked_records(self):
        result = self.resolve(evidence=[self.evidence()])
        self.assertEqual(self.action(plan=result)['requirements'][0]['state'], 'unknown')

    def test_cross_household_records_rejected_without_mutation(self):
        before = copy.deepcopy(self.plan)
        with self.assertRaises(InvalidInput):
            self.resolve([self.link()], [self.evidence(case_id='other_case')])
        self.assertEqual(self.plan, before)

    def test_link_consumer_scope_kind_and_duplicate_leaf_are_validated(self):
        for updates in ({'rule_version': 'other'}, {'node_id': 'missing'}, {'kind': 'confirmation'},
                        {'target_rule_id': 'wrong'}):
            with self.subTest(updates=updates), self.assertRaises(InvalidInput):
                self.resolve([{**self.link(), **updates}])
        with self.assertRaises(InvalidInput):
            self.resolve([self.link(), self.link(link_id='second')])

    def test_source_supported_confirmation_matches_and_false_blocks_only_modeled_gate(self):
        self.action()['requirements'] = [node('confirmed', 'authority_confirmation')]
        for value, state in ((True, 'satisfied'), (False, 'unmet'), (None, 'unknown')):
            result = self.resolve([self.link(kind='confirmation', target='confirm', node_id='confirmed')],
                confirmations=[self.confirmation(value=value)])
            self.assertEqual(self.action(plan=result)['requirements'][0]['state'], state)
            self.assertEqual(result['household_eligibility'], 'unknown')

    def test_confirmation_household_claim_wrong_scope_sources_or_expiry_remain_unknown(self):
        self.action()['requirements'] = [node('confirmed', 'authority_confirmation')]
        link = self.link(kind='confirmation', target='confirm', node_id='confirmed')
        for updates in ({'state': 'user_reported'}, {'source_ids': []}, {'source_ids': ['wrong']},
                        {'rule_version': 'other'}, {'action_id': 'b'}, {'node_id': 'other'},
                        {'observed_at': LATER}, {'expires_at': NOW}, {'state': 'conflicting'}):
            with self.subTest(updates=updates):
                result = self.resolve([link], confirmations=[self.confirmation(**updates)])
                self.assertEqual(self.action(plan=result)['requirements'][0]['state'], 'unknown')

    def test_expired_future_or_stale_reviewed_source_cannot_verify_confirmation(self):
        self.action()['requirements'] = [node('confirmed', 'authority_confirmation')]
        source = self.action()['source_records'][0]
        for updates in ({'freshness': 'stale'}, {'freshness': 'unknown'}, {'expires_at': NOW},
                        {'reviewed_at': LATER}, {'retrieved_at': LATER}, {'updated_at': LATER}):
            original = copy.deepcopy(source)
            source.update(updates)
            result = self.resolve([self.link(kind='confirmation', target='confirm', node_id='confirmed')],
                confirmations=[self.confirmation()])
            self.assertEqual(self.action(plan=result)['requirements'][0]['state'], 'unknown')
            source.clear(); source.update(original)

    def test_nested_and_or_keep_only_required_blockers_and_partial_policy_questions(self):
        self.action()['requirements'] = [group('root', 'all_of', ['choice', 'confirmed']),
            group('choice', 'any_of', ['proof', 'fallback']), node('proof'), node('fallback'),
            node('confirmed', 'authority_confirmation')]
        links = [self.link(), self.link(node_id='fallback', target='fallback_record'),
            self.link(kind='confirmation', target='confirm', node_id='confirmed')]
        result = self.resolve(links, [self.evidence(), self.evidence(id='fallback_record', key='fallback', available=False)],
            [self.confirmation()])
        action = self.action(plan=result)
        self.assertEqual(action['requirements'][0]['state'], 'satisfied')
        self.assertEqual(action['blockers'], [])
        self.assertEqual([q['code'] for q in action['questions']], ['policy_coverage_partial'])
        self.assertEqual(action['requirements'][3]['state'], 'unmet')

    def test_action_link_requires_exact_completed_task_not_ready_or_skipped(self):
        self.action()['requirements'] = [node('finished', 'action')]
        link = self.link(kind='action', target='b', node_id='finished')
        for status, expected in (('ready', 'unmet'), ('waiting', 'unmet'), ('skipped', 'unmet'), ('completed', 'satisfied')):
            self.action('b')['status'] = status
            if status == 'completed':
                self.complete()
            result = self.resolve([link])
            self.assertEqual(self.action(plan=result)['requirements'][0]['state'], expected)

    def test_completed_historical_action_matches_pinned_old_version_and_is_preserved(self):
        self.complete()
        self.action('b').update(is_current=False, input_freshness='stale')
        self.action()['requirements'] = [node('finished', 'action')]
        before = copy.deepcopy(self.action('b'))
        result = self.resolve([self.link(kind='action', target='b', node_id='finished')])
        self.assertEqual(self.action(plan=result)['requirements'][0]['state'], 'satisfied')
        self.assertEqual(self.action('b', result), before)

    def test_missing_mismatched_and_stale_action_dependencies_remain_explicit(self):
        self.action()['requirements'] = [node('finished', 'action')]
        link = self.link(kind='action', target='b', node_id='finished')
        for updates in ({'target_id': 'absent'}, {'target_rule_version': 'other'}):
            result = self.resolve([{**link, **updates}])
            self.assertEqual(self.action(plan=result)['requirements'][0]['reason'], 'dependency_scope_unresolved')
            self.assertTrue(self.action(plan=result)['questions'])
        self.action('b')['input_freshness'] = 'stale'
        result = self.resolve([link])
        self.assertEqual(self.action(plan=result)['requirements'][0]['reason'], 'dependency_stale')

    def test_two_action_cycle_and_self_cycle_produce_blockers_not_recursion(self):
        for action in self.plan['actions']:
            action['requirements'] = [node('finished', 'action')]
        links = [self.link(kind='action', target='b', node_id='finished'),
                 self.link('b', kind='action', target='a', node_id='finished')]
        result = self.resolve(links)
        self.assertEqual(result['dependency_cycles'][0]['action_ids'], ['a', 'b'])
        self.assertTrue(all(a['status'] == 'blocked' for a in result['actions']))
        self.assertTrue(any(b['code'] == 'dependency_cycle' for b in result['blockers']))
        result = self.resolve([self.link(kind='action', target='a', node_id='finished')])
        self.assertEqual(result['dependency_cycles'][0]['action_ids'], ['a'])

    def test_completion_without_report_or_future_report_does_not_satisfy_dependency(self):
        self.action()['requirements'] = [node('finished', 'action')]
        self.action('b')['status'] = 'completed'
        link = self.link(kind='action', target='b', node_id='finished')
        result = self.resolve([link])
        self.assertEqual(self.action(plan=result)['requirements'][0]['reason'], 'dependency_completion_unverified')
        self.complete()
        self.action('b')['history'][-1]['received_at'] = LATER
        result = self.resolve([link])
        self.assertEqual(self.action(plan=result)['requirements'][0]['state'], 'unknown')

    def test_cycle_branch_is_retained_without_blocking_satisfied_or_branch(self):
        self.action()['requirements'] = [group('root', 'any_of', ['proof', 'finished']),
            node('proof'), node('finished', 'action')]
        result = self.resolve([self.link(), self.link(kind='action', target='a', node_id='finished')], [self.evidence()])
        self.assertEqual(self.action(plan=result)['status'], 'waiting')
        self.assertEqual(self.action(plan=result)['blockers'], [])
        self.assertTrue(result['dependency_cycles'])

    def test_stale_consumer_does_not_get_refreshed_by_unrelated_evidence(self):
        self.action()['input_freshness'] = 'stale'
        result = self.resolve([self.link()], [self.evidence()])
        self.assertEqual(self.action(plan=result)['requirements'][0]['state'], 'unknown')
        self.assertEqual(result['state'], 'pending')

    def test_invalid_graphs_and_bounds_fail_without_partial_output(self):
        for nodes in ([group('root', 'all_of', ['absent'])], [node('x'), node('y')],
                      [group('root', 'all_of', ['loop']), group('loop', 'all_of', ['loop'])]):
            self.action()['requirements'] = nodes
            with self.assertRaises(InvalidInput):
                self.resolve()
        self.action()['requirements'] = [node('proof')]
        with self.assertRaises(InvalidInput):
            self.resolve(evidence=[self.evidence(id='e' + str(i)) for i in range(129)])

    def test_priority_deadline_stable_ties_and_prerequisites_order(self):
        ordered = order_actions(self.plan, priorities=[{'action_id': 'a', 'priority': 1}, {'action_id': 'b', 'priority': 0}])
        self.assertEqual([a['id'] for a in ordered['actions']], ['b', 'a'])
        ordered = order_actions(self.plan, deadlines=[{'action_id': 'b', 'deadline': '2026-10-12'}])
        self.assertEqual([a['id'] for a in ordered['actions']], ['b', 'a'])
        self.action()['requirements'] = [node('finished', 'action')]
        resolved = self.resolve([self.link(kind='action', target='b', node_id='finished')])
        ordered = order_actions(resolved, priorities=[{'action_id': 'a', 'priority': 0}, {'action_id': 'b', 'priority': 1000}])
        self.assertEqual([a['id'] for a in ordered['actions']], ['b', 'a'])

    def test_order_preserves_terminal_work_and_rejects_invalid_priority_or_date(self):
        self.complete('a')
        before = copy.deepcopy(self.action())
        ordered = order_actions(self.plan)
        self.assertEqual(ordered['actions'][-1], before)
        with self.assertRaises(InvalidInput):
            order_actions(self.plan, priorities=[{'action_id': 'a', 'priority': 1}])
        for invalid in (True, 1.0, -1, 1001):
            with self.assertRaises(InvalidInput):
                order_actions(self.plan, priorities=[{'action_id': 'b', 'priority': invalid}])
        with self.assertRaises(InvalidInput):
            order_actions(self.plan, deadlines=[{'action_id': 'b', 'deadline': '2026-02-30'}])

    def test_completion_correction_retains_original_and_stales_dependents_without_money_or_fact_changes(self):
        self.complete()
        self.action()['requirements'] = [node('finished', 'action')]
        resolved = self.resolve([self.link(kind='action', target='b', node_id='finished')])
        original = copy.deepcopy(self.action('b', resolved))
        result = self.correct(resolved)
        corrected = self.action('b', result)
        self.assertEqual(corrected['history'][0], original['history'][0])
        self.assertEqual(corrected['history'][-1]['correction_of'], 'completion')
        self.assertEqual(corrected['status'], 'waiting')
        self.assertEqual(self.action(plan=result)['input_freshness'], 'stale')
        self.assertEqual(result['state'], 'pending')
        self.assertEqual(result['version'], resolved['version'] + 1)
        for field in ('requirements', 'costs', 'source_records'):
            self.assertEqual(corrected[field], original[field])

    def test_correction_wrong_completion_event_and_noncompleted_work_rejected(self):
        with self.assertRaises(InvalidInput):
            self.correct()
        self.complete(event='different')
        with self.assertRaises(InvalidInput):
            self.correct()

    def test_correction_future_out_of_order_and_duplicate_event_rejected(self):
        self.complete()
        for occurred, received in ((LATER, NOW), ('2026-10-10T06:00:00Z', NOW)):
            with self.assertRaises(InvalidInput):
                correct_completion(self.plan, {'action_id': 'b', 'completion_event_id': 'completion',
                    'reason_code': 'wrong_action'}, occurred_at=occurred, received_at=received,
                    event_id='correction', input_case_version=1)
        result = self.correct()
        with self.assertRaises(InvalidInput):
            self.correct(result)

    def test_correction_capacity_fails_without_discarding_completion_history(self):
        self.complete()
        action = self.action('b')
        action['history'] = [{**action['history'][0], 'event_id': str(i)} for i in range(63)] + action['history']
        before = copy.deepcopy(self.plan)
        with self.assertRaises(InvalidInput):
            self.correct()
        self.assertEqual(self.plan, before)

    def test_cost_export_dated_nullable_cents_and_explicit_zero_are_distinct(self):
        for amount, expected in ((3500, 'known'), (0, 'known'), (None, 'incomplete')):
            export = self.export(self.cost_plan(amount))
            path = export['paths'][0]
            self.assertEqual(path['cost_state'], expected)
            self.assertEqual(path['commitments'][0]['amount_cents'], amount)
            self.assertEqual(path['commitments'][0]['date'], '2026-10-12')
        unknown = self.export()['paths'][0]
        self.assertIsNone(unknown['commitments'][0]['amount_cents'])
        self.assertIsNone(unknown['commitments'][0]['date'])

    def test_cost_date_unknown_is_not_dropped_or_assigned_deadline(self):
        plan = self.cost_plan()
        self.action(plan=plan)['cost_items'][0]['date'] = None
        self.action(plan=plan)['deadline'] = '2026-10-12'
        export = self.export(plan)
        self.assertIsNone(export['paths'][0]['commitments'][0]['date'])
        self.assertIn('cost_date_unknown', export['paths'][0]['warnings'])

    def test_cost_invalid_cents_nonfinite_and_duplicate_ids_rejected(self):
        for value in (True, 1.0, -1, '3500', float('nan')):
            with self.subTest(value=value), self.assertRaises(InvalidInput):
                self.cost_plan(value)
        plan = self.cost_plan()
        self.action(plan=plan)['cost_items'] *= 2
        with self.assertRaises(InvalidInput):
            self.export(plan)

    def test_cost_stale_or_wrong_source_retains_reported_value_but_exports_null(self):
        for updates in ({'state': 'stale'}, {'state': 'unknown'}, {'state': 'conflicting'},
                        {'state': 'source_supported', 'source_ids': ['wrong']}):
            plan = self.cost_plan()
            self.action(plan=plan)['cost_items'][0].update(updates)
            path = self.export(plan)['paths'][0]
            self.assertEqual(path['cost_items'][0]['amount_cents'], 3500)
            self.assertIsNone(path['commitments'][0]['amount_cents'])

    def test_cost_confirmed_source_support_and_local_date_time_boundary(self):
        plan = self.cost_plan()
        item = self.action(plan=plan)['cost_items'][0]
        item.update(state='source_supported', source_ids=['synthetic_source'], due_at='2026-10-13T03:00:00Z')
        path = self.export(plan)['paths'][0]
        self.assertEqual(path['commitments'][0]['amount_cents'], 3500)
        item['due_at'] = '2026-10-13T06:00:00Z'
        with self.assertRaises(InvalidInput):
            self.export(plan)

    def test_cost_updates_reject_wrong_version_future_observations_and_terminal_overwrite(self):
        update = {'action_id': 'a', 'rule_id': self.action()['rule_id'], 'rule_version': 'wrong', 'items': [self.cost()]}
        with self.assertRaises(InvalidInput):
            set_action_costs(self.plan, [update], as_of=NOW)
        update['rule_version'] = self.action()['rule_version']
        update['items'][0]['observed_at'] = LATER
        with self.assertRaises(InvalidInput):
            set_action_costs(self.plan, [update], as_of=NOW)
        update['items'][0]['observed_at'] = NOW
        self.complete('a')
        with self.assertRaises(InvalidInput):
            set_action_costs(self.plan, [update], as_of=NOW)
        self.assertEqual(self.export()['paths'][0]['commitments'], [])

    def test_selection_replaces_only_untouched_planner_alternative_costs_and_retains_essentials(self):
        export = self.export(self.cost_plan())
        existing = [self.commitment(export['paths'][1]), {'id': 'food', 'category': 'food',
            'essential': True, 'amount_cents': 6500, 'date': '2026-10-12'}]
        before = copy.deepcopy(existing)
        proposal = propose_alternative_selection(export, ['a'], existing_commitments=existing)
        self.assertEqual(proposal['state'], 'proposed')
        self.assertEqual(proposal['retained_commitment_ids'], ['food'])
        self.assertEqual(proposal['remove_commitment_ids'], [existing[0]['id']])
        self.assertEqual(proposal['add_commitments'][0]['action_id'], 'a')
        self.assertTrue(proposal['hypothetical'])
        self.assertEqual(existing, before)

    def test_selection_unknown_cost_date_and_unselectable_path_block_patch(self):
        for plan in (self.plan, self.cost_plan(None)):
            proposal = propose_alternative_selection(self.export(plan), ['a'], existing_commitments=[])
            self.assertEqual(proposal['state'], 'needs_clarification')
            self.assertEqual(proposal['add_commitments'], [])
        plan = self.cost_plan(); self.action(plan=plan)['status'] = 'blocked'
        proposal = propose_alternative_selection(self.export(plan), ['a'], existing_commitments=[])
        self.assertIn('action_not_selectable', proposal['issues'])
        plan = self.cost_plan()
        self.action(plan=plan)['cost_items'][0]['date'] = '2026-10-10'
        proposal = propose_alternative_selection(self.export(plan), ['a'], existing_commitments=[])
        self.assertIn('cost_timing_requires_reassessment', proposal['issues'])
        self.assertEqual(proposal['add_commitments'], [])

    def test_selection_mutually_exclusive_alternatives_and_duplicate_ids_rejected(self):
        export = self.export(self.cost_plan())
        proposal = propose_alternative_selection(export, ['a', 'b'], existing_commitments=[])
        self.assertIn('mutually_exclusive_alternatives', proposal['issues'])
        with self.assertRaises(InvalidInput):
            propose_alternative_selection(export, ['a', 'a'], existing_commitments=[])

    def test_selection_preserves_partial_actual_and_unknown_fulfillment_and_requires_reconciliation(self):
        export = self.export(self.cost_plan())
        for updates in ({'fulfilled_cents': 1200}, {'fulfilled_cents': None}, {'actual_event_ids': ['expense']},
                        {'fulfilled_cents': 0.0}, {'fulfilled_cents': False}):
            record = {**self.commitment(export['paths'][1]), **updates}
            proposal = propose_alternative_selection(export, ['a'], existing_commitments=[record])
            self.assertEqual(proposal['retained_commitment_ids'], [record['id']])
            self.assertEqual(proposal['remove_commitment_ids'], [])
            self.assertEqual(proposal['add_commitments'], [])
            self.assertIn('commitment_reconciliation_required', proposal['issues'])

    def test_selection_preserves_unrelated_planner_records_and_terminal_work(self):
        export = self.export(self.cost_plan())
        independent = copy.deepcopy(export['paths'][1]); independent.update(action_id='independent', alternative_ids=[])
        export['paths'].append(independent)
        unrelated = {'id': 'other', 'action_id': 'independent', 'origin': 'recovery_planner',
            'planner_cost_id': 'other', 'essential': False, 'fulfilled_cents': 0, 'actual_event_ids': []}
        self.complete('b')
        terminal_export = self.export(self.plan)
        record = self.commitment(export['paths'][1])
        proposal = propose_alternative_selection(terminal_export, [], existing_commitments=[record, unrelated])
        self.assertEqual(set(proposal['retained_commitment_ids']), {record['id'], 'other'})
        self.assertEqual(proposal['remove_commitment_ids'], [])

    def test_selection_preserves_past_undated_and_essential_action_costs(self):
        export = self.export(self.cost_plan())
        for updates in ({'date': '2026-10-10'}, {'date': None}, {'essential': True}):
            record = {**self.commitment(export['paths'][1]), **updates}
            proposal = propose_alternative_selection(export, ['a'], existing_commitments=[record])
            self.assertEqual(proposal['retained_commitment_ids'], [record['id']])
            self.assertEqual(proposal['state'], 'needs_clarification')
            self.assertEqual(proposal['add_commitments'], [])

    def test_cost_essential_flag_is_explicit_and_retained_in_export(self):
        plan = self.cost_plan()
        self.action(plan=plan)['cost_items'][0]['essential'] = True
        self.assertTrue(self.export(plan)['paths'][0]['commitments'][0]['essential'])

    def test_selection_preserves_other_programs_and_nonplanner_action_linked_expenses(self):
        export = self.export(self.cost_plan())
        unrelated_plan = self.cost_plan()
        independent = copy.deepcopy(self.action('b', unrelated_plan))
        independent.update(id='independent', program_id='other_program', rule_id='other_rule', alternative_ids=[])
        unrelated_plan['actions'].append(independent)
        export = self.export(unrelated_plan)
        independent_cost = self.commitment(export['paths'][2])
        nonplanner = {**self.commitment(export['paths'][1]), 'id': 'ordinary', 'origin': 'user'}
        proposal = propose_alternative_selection(export, ['a'], existing_commitments=[independent_cost, nonplanner])
        self.assertEqual(set(proposal['retained_commitment_ids']), {independent_cost['id'], 'ordinary'})
        self.assertEqual(proposal['remove_commitment_ids'], [])

    def test_malformed_timestamps_dates_versions_and_input_bounds_are_rejected(self):
        for observed in ('2026-02-30T00:00:00Z', '2026-10-11', '2026-10-11T06:00:00-05:00'):
            with self.assertRaises(InvalidInput):
                self.resolve([self.link()], [self.evidence(observed_at=observed)])
        with self.assertRaises(InvalidInput):
            export_action_costs(self.plan, input_case_version=True, as_of=NOW, time_zone='America/Chicago')
        self.action()['input_case_version'] = 2
        with self.assertRaises(InvalidInput):
            self.resolve()
        with self.assertRaises(InvalidInput):
            self.export()
        self.action()['input_case_version'] = 1
        with self.assertRaises(InvalidInput):
            propose_alternative_selection(self.export(self.cost_plan()), ['a'],
                existing_commitments=[{'id': 'expense', 'amount_cents': float('inf')}])

    def test_repeat_permutation_json_and_alias_isolation_across_pipeline(self):
        links = [self.link('b'), self.link()]
        evidence = [self.evidence()]
        before = copy.deepcopy((self.plan, links, evidence))
        first = self.resolve(links, evidence)
        second = self.resolve(list(reversed(links)), evidence)
        self.assertEqual(first, second)
        exported = self.export(self.cost_plan())
        proposal = propose_alternative_selection(exported, ['a'], existing_commitments=[])
        check('PlannerSelectionProposal', json.loads(json.dumps(proposal)))
        first['actions'][0]['requirements'][0]['state'] = 'unmet'
        exported['paths'][0]['cost_items'][0]['source_ids'].append('mutated')
        proposal['add_commitments'][0]['source_ids'].append('changed')
        self.assertEqual((self.plan, links, evidence), before)


if __name__ == '__main__':
    unittest.main()
