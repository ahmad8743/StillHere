"""Credential-free bounded C06 contracts, provenance and pure transitions."""

import copy
import json
import unittest
from pathlib import Path

from backend.stillhere.applications import prepare_application, update_application, validate
from backend.stillhere.contracts import InvalidInput, empty_case
from backend.stillhere.knowledge.rules import ProgramRuleStore, build_query

NOW = '2026-10-11T06:00:00Z'
OLDER = '2026-10-11T05:00:00Z'
FUTURE = '2026-10-12T06:00:00Z'
PROGRAM = 'co_state_id_replacement'
SOURCE = 'source_rule_co_replacement'


def fact(value, state='user_reported', observed=NOW, sources=()):
    return {'value': value, 'state': state, 'observed_at': observed, 'source_ids': list(sources)}


def evidence(identifier='proof1', key='proof_available', state='unknown', provenance=None, observed=NOW, sources=()):
    return {'id': identifier, 'requirement_key': key, 'state': state,
            'provenance': provenance or (state if state in ('unknown', 'conflicting', 'stale') else 'user_reported'),
            'observed_at': observed, 'source_ids': list(sources)}


def leaf(key, kind='fact', timing='before_start', expected=True):
    return {'id': key, 'operator': 'requirement', 'children': [], 'source_ids': [SOURCE],
            'requirement': {'key': key, 'kind': kind, 'label': 'Synthetic requirement ' + key,
                            'expected': expected, 'timing': timing, 'evidence_state': 'unknown'}}


def group(identifier, operator, children):
    return {'id': identifier, 'operator': operator, 'children': children, 'requirement': None, 'source_ids': [SOURCE]}


class ApplicationDomainTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = empty_case('case_synthetic', 'America/Chicago', NOW)
        self.snapshot['facts'] = {'document_issuing_state': fact('CO'), 'email_access': fact(True)}
        self.catalog = ProgramRuleStore._load()
        self.path = self.catalog['rules'][0]['paths'][0]
        self.path.update(root_id='root', nodes=[group('root', 'all_of', ['email_access', 'proof_available', 'later_proof']),
                        leaf('email_access'), leaf('proof_available', 'evidence'),
                        leaf('later_proof', 'evidence', 'during_application')])
        self.snapshot['evidence'] = [evidence(), evidence('later1', 'later_proof')]
        self.arguments = {'application_id': 'app1', 'action_id': 'action1', 'program_id': PROGRAM,
                          'rule_version': self.catalog['rules'][0]['version'], 'path_id': self.path['id']}
        self.snapshot['plan']['actions'] = [{'id': 'action1', 'program_id': PROGRAM, 'rule_id': self.catalog['rules'][0]['id'],
            'rule_version': self.arguments['rule_version'], 'path_id': self.path['id'], 'status': 'waiting',
            'is_current': True, 'input_freshness': 'current', 'unrelated_planner_field': 'ignored'}]
        self.snapshot['sources'] = copy.deepcopy(self.catalog['sources'])

    def rules(self, now=NOW):
        store = ProgramRuleStore(lambda: copy.deepcopy(self.catalog))
        return store.lookup(build_query(self.snapshot, {'program_id': PROGRAM, 'version': self.arguments['rule_version']}, now))

    def prepare(self, receipts=()):
        return prepare_application(self.snapshot, self.arguments, self.rules(), prepared_at=NOW, agency_receipts=receipts)

    def save_draft(self, receipts=()):
        result = self.prepare(receipts)
        self.snapshot['applications'] = [copy.deepcopy(result['application'])]
        return result['application']

    def update(self, changes, event='event1', occurred=NOW, receipts=()):
        return update_application(self.snapshot, {'application_id': 'app1', **changes}, self.rules(),
                                  event_id=event, occurred_at=occurred, received_at=NOW, agency_receipts=receipts)

    def accept(self, result):
        self.snapshot['applications'] = [copy.deepcopy(result['application'])]
        self.snapshot['evidence'] = copy.deepcopy(result['evidence'])
        self.snapshot['case_version'] += 1

    def stage(self, stage, correction=None, event='event1', receipts=()):
        return self.update({'stage_change': {'stage': stage, 'corrects_event_id': correction}}, event=event, receipts=receipts)

    def answer(self, application, key):
        return next(answer for answer in application['draft_answers'] if answer['fact_key'] == key)

    def agency(self, stage='approved', source='agency1', receipt='receipt1'):
        self.snapshot['sources'].append({'id': source, 'url': 'https://dmv.colorado.gov/',
            'issuer': self.catalog['rules'][0]['issuer'], 'scope': {'case_id': self.snapshot['case_id'], 'application_id': 'app1', 'program_id': PROGRAM},
            'retrieved_at': NOW, 'updated_at': None, 'expires_at': None, 'verification_state': 'agency_record_verified',
            'freshness': 'current', 'data_mode': 'cached'})
        return {'id': receipt, 'case_id': self.snapshot['case_id'], 'application_id': 'app1', 'program_id': PROGRAM,
                'stage': stage, 'observed_at': NOW, 'verified_at': NOW, 'source_ids': [source]}

    def test_preparation_uses_exact_sources_and_blank_unknowns(self):
        result = self.prepare()
        application = result['application']
        self.assertEqual(self.answer(application, 'email_access')['answer'], 'Yes')
        self.assertEqual(self.answer(application, 'proof_available')['answer'], '')
        self.assertEqual(application['source_ids'], self.catalog['rules'][0]['source_ids'])
        self.assertEqual({s['id'] for s in result['sources']}, set(application['source_ids']))
        self.assertEqual(application['stage_report'], None)
        self.assertEqual(application['agency_outcome'], None)
        self.assertEqual(application['preparation_state'], 'provisional')
        self.assertEqual(result['household_eligibility'], 'unknown')
        self.assertFalse(result['external_submission'])
        self.assertEqual(application['official_url'], self.path['official_url'])
        for line in application['call_script']:
            self.assertTrue(line['source_ids'])

    def test_missing_evidence_and_no_coercion(self):
        self.snapshot['evidence'][0] = evidence(state='missing')
        application = self.prepare()['application']
        self.assertEqual(application['next_step']['kind'], 'gather_evidence')
        self.assertEqual(self.answer(application, 'proof_available')['answer'], 'No')
        for value in ('true', 1, {'document_number': 'synthetic'}, None):
            self.snapshot['facts']['email_access'] = fact(value)
            self.assertEqual(self.answer(self.prepare()['application'], 'email_access')['answer'], '')

    def test_conflicting_evidence_records_do_not_silently_choose_latest(self):
        self.snapshot['evidence'] += [evidence('proof2', state='missing')]
        self.snapshot['evidence'][0] = evidence(state='available')
        application = self.prepare()['application']
        answer = self.answer(application, 'proof_available')
        self.assertEqual(answer['answer'], '')
        self.assertEqual(answer['state'], 'conflicting')
        self.assertEqual(set(answer['evidence_ids']), {'proof1', 'proof2'})
        self.assertEqual(application['next_step']['kind'], 'clarify_evidence')

    def test_unknown_stale_conflicting_and_future_evidence_stay_blank(self):
        for state in ('unknown', 'stale', 'conflicting'):
            self.snapshot['evidence'][0] = evidence(state=state)
            self.assertEqual(self.answer(self.prepare()['application'], 'proof_available')['answer'], '')
        for observed in (None, FUTURE):
            self.snapshot['evidence'][0] = evidence(state='available', observed=observed)
            self.assertEqual(self.answer(self.prepare()['application'], 'proof_available')['answer'], '')

    def test_unknown_stale_conflicting_and_future_facts_stay_blank(self):
        for state in ('unknown', 'stale', 'conflicting'):
            self.snapshot['facts']['email_access'] = fact(True, state)
            self.assertEqual(self.answer(self.prepare()['application'], 'email_access')['answer'], '')
        for observed in (None, FUTURE):
            self.snapshot['facts']['email_access'] = fact(True, observed=observed)
            self.assertEqual(self.answer(self.prepare()['application'], 'email_access')['answer'], '')

    def test_untyped_evidence_fact_is_not_an_evidence_record(self):
        self.snapshot['facts']['proof_available'] = fact(True)
        self.snapshot['evidence'] = []
        self.assertEqual(self.answer(self.prepare()['application'], 'proof_available')['answer'], '')

    def test_fact_and_evidence_provenance_keeps_source_and_observation(self):
        self.snapshot['facts']['email_access'] = fact(False, 'source_supported', sources=[SOURCE])
        self.snapshot['evidence'][0] = evidence(state='available', provenance='source_supported', sources=[SOURCE])
        application = self.prepare()['application']
        for key in ('email_access', 'proof_available'):
            answer = self.answer(application, key)
            self.assertEqual(answer['state'], 'source_supported')
            self.assertEqual(answer['observed_at'], NOW)
            self.assertIn(SOURCE, answer['source_ids'])

    def test_no_household_authority_confirmation_or_task_outcome_inference(self):
        self.path.update(root_id='confirm', nodes=[leaf('confirm', 'authority_confirmation')])
        self.snapshot['facts']['confirm'] = fact(True, 'source_supported', sources=[SOURCE])
        self.snapshot['plan']['actions'][0]['status'] = 'completed'
        application = self.prepare()['application']
        self.assertEqual(self.answer(application, 'confirm')['answer'], '')
        self.assertIsNone(application['agency_outcome'])
        self.assertIsNone(application['stage_report'])
        self.path.update(root_id='task', nodes=[leaf('task', 'action')])
        self.snapshot['facts']['task'] = fact(True)
        self.assertEqual(self.answer(self.prepare()['application'], 'task')['answer'], '')

    def test_evidence_timing_retained_and_later_evidence_does_not_block_start(self):
        self.snapshot['evidence'][0] = evidence(state='available')
        application = self.prepare()['application']
        self.assertEqual(application['next_step']['kind'], 'review_draft')
        later = next(node for node in application['checklist'] if node['node_id'] == 'later_proof')
        self.assertEqual(later['requirement']['timing'], 'during_application')
        self.assertTrue(any('during the application' in line['text'] for line in application['call_script']))
        self.path['nodes'][-1]['requirement']['timing'] = 'before_receipt'
        self.assertTrue(any('before receiving assistance' in line['text'] for line in self.prepare()['application']['call_script']))

    def test_or_branches_retained_without_blocking_satisfied_alternative(self):
        self.path.update(root_id='choice', nodes=[group('choice', 'any_of', ['proof_available', 'email_access']),
                                                leaf('proof_available', 'evidence'), leaf('email_access')])
        self.snapshot['evidence'][0] = evidence(state='missing')
        application = self.prepare()['application']
        self.assertEqual(application['checklist'][0]['state'], 'satisfied')
        self.assertEqual(application['checklist'][0]['children'], ['proof_available', 'email_access'])
        self.assertEqual(application['next_step']['kind'], 'review_draft')
        self.assertEqual(len(application['draft_answers']), 2)

    def test_shared_dag_leaf_is_prepared_once(self):
        self.path.update(root_id='root', nodes=[group('root', 'all_of', ['a', 'b']),
                        group('a', 'all_of', ['email_access']), group('b', 'any_of', ['email_access']), leaf('email_access')])
        self.assertEqual(len(self.prepare()['application']['draft_answers']), 1)
        self.snapshot['facts']['email_access'] = fact(None, 'unknown')
        application = self.prepare()['application']
        self.assertEqual(application['next_step']['node_ids'], ['email_access'])
        self.assertEqual(len([line for line in application['call_script'] if line['kind'] == 'question']), 1)

    def test_false_expected_predicate_retains_actual_answer(self):
        self.path.update(root_id='email_access', nodes=[leaf('email_access', expected=False)])
        application = self.prepare()['application']
        self.assertEqual(application['checklist'][0]['state'], 'missing')
        self.assertEqual(application['draft_answers'][0]['answer'], 'Yes')

    def test_prepare_and_update_are_deterministic_and_do_not_mutate_inputs(self):
        before = copy.deepcopy((self.snapshot, self.arguments, self.catalog))
        rules = self.rules()
        saved_rules = copy.deepcopy(rules)
        result = prepare_application(self.snapshot, self.arguments, rules, prepared_at=NOW)
        self.assertEqual(result, self.prepare())
        self.assertEqual(before, (self.snapshot, self.arguments, self.catalog))
        self.assertEqual(rules, saved_rules)
        result['application']['draft_answers'][0]['answer'] = 'changed'
        self.save_draft()
        args = {'application_id': 'app1', 'evidence_changes': [{'evidence_id': 'proof1', 'state': 'available'}]}
        before = copy.deepcopy((self.snapshot, args, rules))
        result = update_application(self.snapshot, args, rules, event_id='event1', occurred_at=NOW, received_at=NOW)
        self.assertEqual(before, (self.snapshot, args, rules))
        result['evidence'][0]['state'] = 'missing'
        self.assertEqual(self.snapshot['evidence'][0]['state'], 'unknown')

    def test_invalid_argument_references(self):
        for field, value in [('action_id', 'absent'), ('path_id', 'absent'), ('program_id', 'other'), ('rule_version', 'other')]:
            with self.subTest(field=field), self.assertRaises(InvalidInput):
                prepare_application(self.snapshot, {**self.arguments, field: value}, self.rules(), prepared_at=NOW)
        self.snapshot['plan']['actions'][0]['program_id'] = 'other'
        with self.assertRaises(InvalidInput): self.prepare()

    def test_duplicate_ids_and_missing_source_references(self):
        for collection in ('evidence', 'sources'):
            with self.subTest(collection=collection):
                original = copy.deepcopy(self.snapshot[collection])
                self.snapshot[collection].append(copy.deepcopy(original[0]))
                with self.assertRaises(InvalidInput): self.prepare()
                self.snapshot[collection] = original
        self.snapshot['evidence'][0]['source_ids'] = ['absent']
        with self.assertRaises(InvalidInput): self.prepare()
        self.snapshot['evidence'][0]['source_ids'] = []
        self.snapshot['facts']['email_access']['source_ids'] = ['absent']
        with self.assertRaises(InvalidInput): self.prepare()

    def test_invalid_evidence_provenance_and_sensitive_payload_rejected(self):
        self.snapshot['evidence'][0]['provenance'] = 'source_supported'
        with self.assertRaises(InvalidInput): self.prepare()
        self.snapshot['evidence'][0] = evidence(state='available', provenance='unknown')
        with self.assertRaises(InvalidInput): self.prepare()
        self.snapshot['evidence'][0] = evidence()
        self.snapshot['evidence'][0]['raw_document'] = 'synthetic raw content'
        with self.assertRaises(InvalidInput): self.prepare()
        self.save_draft_after_reset()
        with self.assertRaises(InvalidInput):
            self.update({'correspondence': {'id': 'letter', 'kind': 'other', 'evidence_ids': [], 'body': 'synthetic identity contents'}})

    def save_draft_after_reset(self):
        self.snapshot['evidence'][0] = evidence()
        self.save_draft()

    def test_stale_missing_conflicting_and_failed_rules_preserve_inputs(self):
        for state in ('stale', 'conflicting', 'unknown', 'unavailable', 'no_match'):
            rules = self.rules()
            rules['state'] = state
            if state in ('unknown', 'unavailable', 'no_match'):
                rules.update(rules=[], sources=[])
            if state == 'conflicting':
                other = copy.deepcopy(rules['rules'][0]); other['version'] = 'other'
                rules['rules'].append(other)
            before = copy.deepcopy(self.snapshot)
            with self.assertRaises(InvalidInput):
                prepare_application(self.snapshot, self.arguments, rules, prepared_at=NOW)
            self.assertEqual(before, self.snapshot)

    def test_current_label_cannot_hide_expired_or_future_rules(self):
        rules = self.rules(); rules['rules'][0]['review_expires_at'] = '2026-10-11T05:00:00Z'
        with self.assertRaises(InvalidInput): prepare_application(self.snapshot, self.arguments, rules, prepared_at=NOW)
        rules = self.rules(); rules['sources'][0]['freshness'] = 'stale'
        with self.assertRaises(InvalidInput): prepare_application(self.snapshot, self.arguments, rules, prepared_at=NOW)

    def test_invalid_graph_references_and_cycles(self):
        self.path['nodes'][0]['children'].append('absent')
        with self.assertRaises(InvalidInput): self.prepare()
        self.path['nodes'][0]['children'] = ['root']
        with self.assertRaises(InvalidInput): self.prepare()

    def test_scope_case_version_time_and_selected_action_freshness(self):
        rules = self.rules(); rules['query']['input_case_version'] += 1
        with self.assertRaises(InvalidInput): prepare_application(self.snapshot, self.arguments, rules, prepared_at=NOW)
        with self.assertRaises(InvalidInput): prepare_application(self.snapshot, self.arguments, self.rules(), prepared_at=FUTURE)
        self.snapshot['facts']['document_issuing_state'] = fact('CO', 'stale')
        with self.assertRaises(InvalidInput): self.prepare()
        self.snapshot['facts']['document_issuing_state'] = fact('CO')
        for field, value in [('is_current', False), ('input_freshness', 'stale'), ('status', 'skipped')]:
            old = self.snapshot['plan']['actions'][0][field]
            self.snapshot['plan']['actions'][0][field] = value
            with self.assertRaises(InvalidInput): self.prepare()
            self.snapshot['plan']['actions'][0][field] = old

    def test_existing_application_must_use_update(self):
        self.save_draft()
        with self.assertRaises(InvalidInput): self.prepare()

    def test_user_approval_is_only_a_report_and_cannot_create_money_or_outcome(self):
        self.save_draft()
        before = copy.deepcopy(self.snapshot)
        result = self.stage('approved')
        application = result['application']
        self.assertEqual(application['stage_report']['provenance'], 'user_reported')
        self.assertIsNone(application['agency_outcome'])
        self.assertEqual(application['next_step']['kind'], 'check_reported_status')
        self.assertEqual(result['household_eligibility'], 'unknown')
        self.assertFalse(result['external_submission'])
        self.assertNotIn('finance', result)
        self.assertEqual(self.snapshot, before)

    def test_corrections_can_reverse_stage_and_preserve_previous_reports(self):
        self.save_draft(); self.accept(self.stage('approved'))
        with self.assertRaises(InvalidInput): self.stage('draft', event='event2')
        result = self.stage('draft', correction='event1', event='event2')
        self.assertEqual(result['application']['stage_report']['stage'], 'draft')
        self.assertEqual(result['application']['history'][0]['stage_change']['stage'], 'approved')
        self.assertEqual(result['application']['history'][1]['stage_change']['corrects_event_id'], 'event1')
        self.assertEqual(len(result['application']['history']), 2)

    def test_correction_must_target_active_report(self):
        self.save_draft()
        with self.assertRaises(InvalidInput): self.stage('draft', correction='absent')
        self.accept(self.stage('submitted'))
        with self.assertRaises(InvalidInput): self.stage('draft', correction='absent', event='event2')
        self.accept(self.stage('under_review', event='event2'))
        with self.assertRaises(InvalidInput): self.stage('draft', correction='event1', event='event3')

    def test_normal_transition_allows_evidence_request_and_resubmission(self):
        self.save_draft()
        for stage, event in [('submitted', 'e1'), ('under_review', 'e2'), ('needs_evidence', 'e3'), ('submitted', 'e4'), ('denied', 'e5')]:
            result = self.stage(stage, event=event)
            self.accept(result)
        self.assertEqual(len(self.snapshot['applications'][0]['history']), 5)
        with self.assertRaises(InvalidInput): self.stage('approved', event='e6')

    def test_older_stage_requires_correction_and_future_reports_are_invalid(self):
        self.save_draft(); self.accept(self.stage('submitted'))
        with self.assertRaises(InvalidInput): self.update({'stage_change': {'stage': 'under_review', 'corrects_event_id': None}}, event='e2', occurred=OLDER)
        result = self.update({'stage_change': {'stage': 'draft', 'corrects_event_id': 'event1'}}, event='e2', occurred=OLDER)
        self.assertEqual(result['application']['stage_report']['observed_at'], OLDER)
        with self.assertRaises(InvalidInput): self.update({'stage_change': {'stage': 'draft', 'corrects_event_id': 'event1'}}, event='e2', occurred=FUTURE)

    def test_reported_correspondence_does_not_verify_receipt_or_decision(self):
        self.save_draft()
        for kind in ('receipt_notice', 'evidence_request', 'decision_notice'):
            result = self.update({'correspondence': {'id': 'letter_' + kind, 'kind': kind, 'evidence_ids': ['proof1']}})
            self.assertIsNone(result['application']['agency_outcome'])
            self.assertIsNone(result['application']['stage_report'])
            self.assertEqual(result['application']['correspondence'][0]['provenance'], 'user_reported')
            if kind != 'receipt_notice': self.assertEqual(result['application']['next_step']['kind'], 'review_correspondence')

    def test_update_evidence_revises_draft_and_requests_plan_reassessment(self):
        self.save_draft()
        result = self.update({'evidence_changes': [{'evidence_id': 'proof1', 'state': 'available'}]})
        self.assertEqual(self.answer(result['application'], 'proof_available')['answer'], 'Yes')
        self.assertTrue(result['requires_plan_reassessment'])
        self.assertEqual(result['application']['preparation_state'], 'pending')
        self.assertEqual(result['changed_evidence_ids'], ['proof1'])
        self.assertEqual(result['application']['next_step']['kind'], 'review_draft')
        self.assertEqual(result['evidence'][0]['provenance'], 'user_reported')
        self.assertEqual(result['application']['history'][0]['evidence_changes'][0]['state'], 'available')
        self.accept(result)
        result = self.update({'evidence_changes': [{'evidence_id': 'proof1', 'state': 'missing'}]}, event='event2')
        self.assertEqual(result['application']['next_step']['kind'], 'gather_evidence')

    def test_combined_update_is_atomic_and_keeps_correspondence_time(self):
        self.save_draft()
        args = {'stage_change': {'stage': 'needs_evidence', 'corrects_event_id': None},
                'correspondence': {'id': 'letter1', 'kind': 'evidence_request', 'evidence_ids': ['proof1']},
                'evidence_changes': [{'evidence_id': 'proof1', 'state': 'missing'}]}
        result = self.update(args)
        self.assertEqual(len(result['application']['history']), 1)
        self.assertEqual(result['application']['correspondence'][0]['received_at'], NOW)
        before = copy.deepcopy(self.snapshot)
        args['evidence_changes'].append({'evidence_id': 'absent', 'state': 'available'})
        with self.assertRaises(InvalidInput): self.update(args)
        self.assertEqual(before, self.snapshot)

    def test_update_unknown_application_evidence_and_correspondence_refs(self):
        self.save_draft()
        with self.assertRaises(InvalidInput):
            update_application(self.snapshot, {'application_id': 'absent', 'stage_change': {'stage': 'draft', 'corrects_event_id': None}}, self.rules(), event_id='e', occurred_at=NOW, received_at=NOW)
        for change in ({'evidence_changes': [{'evidence_id': 'absent', 'state': 'available'}]},
                       {'correspondence': {'id': 'letter', 'kind': 'evidence_request', 'evidence_ids': ['absent']}}):
            with self.assertRaises(InvalidInput): self.update(change)
        self.snapshot['evidence'].append(evidence('unrelated', 'other_program'))
        with self.assertRaises(InvalidInput): self.update({'evidence_changes': [{'evidence_id': 'unrelated', 'state': 'available'}]})

    def test_empty_duplicate_and_sensitive_updates_rejected(self):
        self.save_draft()
        for change in ({}, {'evidence_changes': []}, {'agency_outcome': {'stage': 'approved'}},
                       {'identity_number': 'synthetic'}, {'stage_change': {'stage': 'invalid', 'corrects_event_id': None}},
                       {'evidence_changes': [{'evidence_id': 'proof1', 'state': 'available'}, {'evidence_id': 'proof1', 'state': 'missing'}]}):
            with self.assertRaises(InvalidInput): self.update(change)

    def test_replay_and_correspondence_duplicates_defer_to_case_service(self):
        self.save_draft()
        self.accept(self.stage('submitted'))
        with self.assertRaises(InvalidInput): self.stage('submitted')
        result = self.update({'correspondence': {'id': 'letter', 'kind': 'other', 'evidence_ids': []}}, event='e2')
        self.accept(result)
        with self.assertRaises(InvalidInput): self.update({'correspondence': {'id': 'letter', 'kind': 'other', 'evidence_ids': []}}, event='e3')

    def test_verified_agency_outcome_is_separate_from_report_and_survives_correction(self):
        receipt = self.agency()
        self.save_draft([receipt])
        result = self.stage('approved', receipts=[receipt])
        self.assertEqual(result['application']['agency_outcome'], receipt)
        self.assertEqual(result['application']['next_step']['kind'], 'review_agency_decision')
        self.accept(result)
        result = self.stage('submitted', correction='event1', event='event2', receipts=[receipt])
        self.assertEqual(result['application']['stage_report']['stage'], 'submitted')
        self.assertEqual(result['application']['agency_outcome']['stage'], 'approved')
        self.assertEqual(result['application']['next_step']['kind'], 'clarify_stage')
        self.assertEqual(result['household_eligibility'], 'unknown')
        with self.assertRaises(InvalidInput): self.stage('approved', correction='event1', event='event2')

    def test_public_rule_source_cannot_establish_official_outcome(self):
        receipt = self.agency()
        receipt['source_ids'] = [SOURCE]
        with self.assertRaises(InvalidInput): self.prepare([receipt])

    def test_agency_receipt_scope_times_issuer_and_mode_are_checked(self):
        receipt = self.agency()
        for field, value in [('case_id', 'other'), ('application_id', 'other'), ('program_id', 'other'),
                             ('source_ids', ['absent']), ('verified_at', OLDER), ('observed_at', FUTURE)]:
            with self.subTest(field=field), self.assertRaises(InvalidInput): self.prepare([{**receipt, field: value}])
        source = self.snapshot['sources'][-1]
        for field, value in [('issuer', 'other'), ('data_mode', 'seeded'), ('scope', {}), ('verification_state', 'official_page_reviewed')]:
            old = source[field]; source[field] = value
            with self.subTest(field=field), self.assertRaises(InvalidInput): self.prepare([receipt])
            source[field] = old

    def test_conflicting_verified_outcomes_are_not_silently_selected(self):
        first = self.agency('approved')
        second = self.agency('denied', 'agency2', 'receipt2')
        with self.assertRaises(InvalidInput): self.prepare([first, second])
        second['observed_at'] = OLDER
        self.assertEqual(self.prepare([first, second])['application']['agency_outcome']['stage'], 'approved')

    def test_bad_saved_references_are_rejected_and_derived_answers_regenerated(self):
        self.save_draft()
        application = self.snapshot['applications'][0]
        application['draft_answers'][0]['answer'] = 'No'
        result = self.stage('draft')
        self.assertEqual(self.answer(result['application'], 'email_access')['answer'], 'Yes')
        application['checklist'][0]['children'] = ['absent']
        with self.assertRaises(InvalidInput): self.stage('draft')

    def test_history_report_cannot_be_forged_or_lost(self):
        self.save_draft(); self.accept(self.stage('submitted'))
        self.snapshot['applications'][0]['stage_report']['event_id'] = 'absent'
        with self.assertRaises(InvalidInput): self.stage('under_review', event='event2')

    def test_evidence_change_after_submission_changes_next_step(self):
        self.save_draft(); self.accept(self.stage('submitted'))
        result = self.update({'evidence_changes': [{'evidence_id': 'proof1', 'state': 'missing'}]}, event='e2')
        self.assertEqual(result['application']['next_step']['kind'], 'gather_evidence')
        self.assertEqual(result['application']['stage_report']['stage'], 'submitted')

    def test_verified_receipt_and_evidence_request_keep_agency_basis_and_source(self):
        receipt = self.agency('received')
        self.snapshot['evidence'][0] = evidence(state='available')
        application = self.prepare([receipt])['application']
        self.assertEqual(application['next_step']['kind'], 'check_agency_status')
        self.assertEqual(application['next_step']['basis'], 'agency_supported')
        self.assertIn('agency1', application['next_step']['source_ids'])
        receipt['stage'] = 'needs_evidence'
        application = self.prepare([receipt])['application']
        self.assertEqual(application['next_step']['kind'], 'gather_evidence')
        self.assertEqual(application['next_step']['basis'], 'agency_supported')

    def test_history_capacity_never_truncates_corrections(self):
        self.save_draft()
        for index in range(64):
            self.accept(self.stage('draft', event='stage_' + str(index)))
        before = copy.deepcopy(self.snapshot)
        with self.assertRaises(InvalidInput): self.stage('submitted', event='stage_overflow')
        self.assertEqual(self.snapshot, before)

    def test_source_id_and_schema_empty_or_nonfinite_inputs_rejected(self):
        self.snapshot['sources'].append({})
        with self.assertRaises(InvalidInput): self.prepare()
        self.snapshot['sources'].pop()
        self.snapshot['facts']['email_access']['value'] = float('nan')
        with self.assertRaises(InvalidInput): self.prepare()
        with self.assertRaises(InvalidInput): validate('AgencyReceipt', {'id': 'receipt'})
        receipt = self.agency()
        receipt['source_ids'] = []
        with self.assertRaises(InvalidInput): self.prepare([receipt])

    def test_evidence_older_report_is_rejected_without_mutation(self):
        self.save_draft()
        before = copy.deepcopy(self.snapshot)
        with self.assertRaises(InvalidInput):
            self.update({'evidence_changes': [{'evidence_id': 'proof1', 'state': 'missing'}]}, occurred=OLDER)
        self.assertEqual(self.snapshot, before)

    def test_schema_is_draft_2020_and_shared_references_exist(self):
        schema = json.loads(Path('contracts/parallel/applications.schema.json').read_text())
        shared = json.loads(Path('contracts/case-service.schema.json').read_text())
        def walk(value):
            if isinstance(value, dict):
                if '$ref' in value:
                    reference = value['$ref']
                    definitions = shared['$defs'] if reference.startswith('../') else schema['$defs']
                    self.assertIn(reference.split('/')[-1], definitions)
                for child in value.values(): walk(child)
            elif isinstance(value, list):
                for child in value: walk(child)
        walk(schema)
        validate('ApplicationPreparationResult', self.prepare())
        self.save_draft()
        validate('ApplicationUpdateResult', self.stage('submitted'))
        self.assertEqual(schema['$defs']['PrepareApplicationArguments']['type'], 'object')
        self.assertEqual(schema['$defs']['UpdateApplicationArguments']['type'], 'object')


if __name__ == '__main__':
    unittest.main()
