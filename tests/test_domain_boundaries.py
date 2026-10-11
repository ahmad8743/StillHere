"""Synthetic cross-domain behavior, authority isolation and immutable inputs."""

import copy
import json
import unittest
from pathlib import Path

from backend.stillhere.boundaries import (TrustedRecordBoundary, assemble_dependencies,
    finance_planner_request, invalidate_applications, propose_completion_correction,
    reconcile_action_costs, report_application_only, update_application_boundary, validate)
from backend.stillhere.boundaries import validate_saved_action_scenarios
from backend.stillhere.contracts import InvalidInput, empty_case
from backend.stillhere.finance import compare_financial_scenarios, forecast_finances, FinanceInputError
from backend.stillhere.planner import evaluate_options, export_action_costs, set_action_costs
from backend.stillhere.planner.plans import revise_plan
from tests import test_applications as application_fixtures
from tests import test_finance as finance_fixtures
from tests import test_planner_bounded as planner_fixtures

NOW = '2026-10-11T06:00:00Z'
LATER = '2026-10-11T07:00:00Z'
ZONE = 'America/Chicago'
START = '2026-10-12'


class DomainBoundaryTests(unittest.TestCase):
    def setUp(self):
        # Reuse synthetic domain fixture builders without discovering their tests.
        self.p = planner_fixtures.BoundedPlannerTests()
        self.p.setUp()
        self.plan = self.p.cost_plan()
        self.ledger = finance_fixtures.ledger(costs=[finance_fixtures.expense(date=START)])
        self.a = application_fixtures.ApplicationDomainTests()
        self.a.setUp()
        self.a.save_draft()

    def reconcile(self, selected=None, plan=None, ledger=None):
        return reconcile_action_costs(plan or self.plan, ledger or self.ledger, ['a'] if selected is None else selected,
             input_case_version=1, as_of=NOW, time_zone=ZONE, start_date=START)

    def old_cost(self, **changes):
        value = self.p.commitment(self.p.export(self.plan)['paths'][1])
        value.pop('due_at')
        value.update(rule_id=self.plan['actions'][1]['rule_id'],rule_version=self.plan['actions'][1]['rule_version'])
        value.update(changes)
        return value

    def report(self, stage='approved', **kwargs):
        return report_application_only(self.a.snapshot, {'application_id':'app1',
            'stage_change': {'stage':stage, 'corrects_event_id':None}},
            event_id='report1', occurred_at=NOW, received_at=LATER, **kwargs)

    def request(self, ledger=None, previous=None, changed=None, plan=None, case_version=1):
        return finance_planner_request(plan or self.plan, ledger or self.ledger, previous,
            case_id='synthetic_case', input_case_version=case_version,
            changed_record_ids=['expense_commitments:food'] if changed is None else changed,
            start_date=START, time_zone=ZONE)

    def test_same_rule_alternative_replaces_only_untouched_cost(self):
        old = self.old_cost()
        self.ledger['expense_commitments'] += [old, finance_fixtures.expense('unrelated',500,'transport',date=START, essential=False,action_id='elsewhere')]
        before = copy.deepcopy(self.ledger)
        result = self.reconcile()
        self.assertEqual(result['state'],'proposed',result['issues'])
        self.assertEqual(result['remove_commitment_ids'],[old['id']])
        self.assertEqual(result['retained_commitment_ids'],['food','unrelated'])
        self.assertEqual(self.ledger,before)
        self.assertEqual(result['comparison_ledger']['money_sources'],before['money_sources'])
        validate('CostReconciliation',result)

    def test_unknown_amount_is_incomplete_not_zero(self):
        self.plan['actions'][0]['cost_items'][0]['amount_cents']=None
        result=self.reconcile()
        self.assertEqual(result['state'],'proposed')
        self.assertIsNone(result['action_alternatives'][0]['costs'][0]['amount_cents'])
        forecasts=compare_financial_scenarios(self.ledger,start_date=START,time_zone=ZONE,input_case_version=1,
            scenarios=[{'id':'unknown','label':'Unknown','alternative_ids':['a']}],action_alternatives=result['action_alternatives'])
        self.assertEqual(forecasts['scenarios'][0]['state'],'incomplete')
        validate('CostReconciliation',result)

    def test_unknown_date_suppresses_entire_patch_and_retains_unknown(self):
        self.plan['actions'][0]['cost_items'][0]['date']=None
        self.ledger['expense_commitments'].append(self.old_cost())
        result=self.reconcile()
        self.assertEqual(result['state'],'needs_clarification')
        self.assertEqual(result['remove_commitment_ids'],[])
        self.assertEqual(result['action_alternatives'],[])
        self.assertIsNone(result['comparison_ledger'])
        self.assertIsNone(result['cost_export']['paths'][0]['commitments'][0]['date'])
        validate('CostReconciliation',result)

    def test_known_zero_is_zero(self):
        self.plan['actions'][0]['cost_items'][0]['amount_cents']=0
        self.assertEqual(self.reconcile()['action_alternatives'][0]['costs'][0]['amount_cents'],0)

    def test_selected_existing_cost_refresh_uses_distinct_hypothetical_identity(self):
        old=self.p.commitment(self.p.export(self.plan)['paths'][0]);old.pop('due_at')
        old.update(rule_id=self.plan['actions'][0]['rule_id'],rule_version=self.plan['actions'][0]['rule_version'])
        self.ledger['expense_commitments'].append(old)
        result=self.reconcile()
        self.assertEqual(result['state'],'proposed',result['issues'])
        quoted=result['action_alternatives'][0]['costs'][0]
        self.assertNotEqual(quoted['id'],old['id'])
        self.assertEqual(quoted['planner_commitment_id'],old['id'])
        self.assertEqual(self.ledger['expense_commitments'][-1],old)
        validate('CostReconciliation',result)

    def test_legacy_or_wrong_rule_ownership_requires_reconciliation(self):
        for kind in ('missing','changed'):
            value=copy.deepcopy(self.ledger);old=self.old_cost()
            if kind=='missing':old.pop('rule_version')
            else:old['rule_version']='old_version'
            value['expense_commitments'].append(old)
            result=self.reconcile(ledger=value)
            self.assertEqual(result['state'],'needs_clarification')
            self.assertIn(old['id'],result['retained_commitment_ids'])

    def test_saved_scenario_quotes_are_checked_without_silent_repricing(self):
        from backend.stillhere.finance import set_financial_scenario
        quote=self.reconcile()
        result=set_financial_scenario(self.ledger,{'id':'saved','label':'Saved','alternative_ids':['a']},
            event_id='saved',effective_at=NOW,received_at=NOW,time_zone=ZONE,start_date=START,
            action_alternatives=quote['action_alternatives'])
        self.assertEqual(result['status'],'applied')
        saved=result['next_ledger'];before=copy.deepcopy(saved)
        def check(plan=self.plan, as_of=NOW, start_date=START):
            return validate_saved_action_scenarios(plan,saved,input_case_version=1,as_of=as_of,
                                                  time_zone=ZONE,start_date=start_date)
        self.assertEqual(check()['state'],'current')
        validate('SavedActionScenarioValidation',check())
        changed=copy.deepcopy(self.plan);changed['actions'][0]['cost_items'][0]['amount_cents']=5000
        self.assertEqual(check(changed)['state'],'needs_clarification')
        changed['actions'][0]['cost_items'][0]['date']=None
        self.assertEqual(check(changed)['state'],'needs_clarification')
        changed=copy.deepcopy(self.plan);changed['actions'][0]['input_freshness']='stale'
        self.assertEqual(check(changed)['state'],'needs_clarification')
        self.assertEqual(check(as_of='2026-10-13T06:00:00Z',start_date='2026-10-13')['state'],'needs_clarification')
        self.assertEqual(saved,before)

    def test_protected_essential_fulfilled_unknown_actual_support_spending(self):
        for changes in ({'essential':True},{'fulfilled_cents':100},{'fulfilled_cents':None}, {'actual_event_ids':['actual1']}):
            with self.subTest(changes=changes):
                value=copy.deepcopy(self.ledger)
                old=self.old_cost(**changes)
                value['expense_commitments'].append(old)
                result=self.reconcile(ledger=value)
                self.assertIn(old['id'],result['retained_commitment_ids'])
                self.assertEqual(result['state'],'needs_clarification')
                self.assertIsNone(result['comparison_ledger'])
                self.assertEqual(value['expense_commitments'][-1],old)

    def test_actual_match_is_protected_even_if_metadata_claims_empty(self):
        old=self.old_cost()
        self.ledger['expense_commitments'].append(old)
        self.ledger['actual_events']=[{'id':'actual1','kind':'expense','state':'proposed', 'amount_cents':500,
            'date':START,'effective_at':'2026-10-12T12:00:00Z','currency':'USD','source':'user_reported',
            'money_source_id':'cash','category':'documents','commitment_id':old['id']}]
        result=self.reconcile()
        self.assertIn(old['id'],result['retained_commitment_ids'])
        self.assertEqual(result['state'],'needs_clarification')

    def test_support_reference_is_preserved(self):
        old=self.old_cost()
        self.ledger['expense_commitments'].append(old)
        self.ledger['support']=[finance_fixtures.coverage(categories=['documents'],commitment_ids=[old['id']],end_date='2026-10-16')]
        result=self.reconcile()
        self.assertEqual(result['state'],'needs_clarification')
        self.assertEqual(self.ledger['support'][0]['commitment_ids'],[old['id']])

    def test_restrictions_remain_and_cannot_pay_other_category(self):
        self.ledger['money_sources']=[finance_fixtures.source(amount=0),finance_fixtures.source('voucher',10000,['food'])]
        result=self.reconcile()
        self.assertEqual(result['comparison_ledger']['money_sources'],self.ledger['money_sources'])
        forecast=forecast_finances(result['comparison_ledger'],start_date=START,time_zone=ZONE,input_case_version=1)
        self.assertEqual(forecast['baseline']['first_gap']['amount_cents'],3500)

    def test_other_rule_or_one_way_alternative_is_not_removed(self):
        for kind in ('version','one_way'):
            with self.subTest(kind=kind):
                plan=copy.deepcopy(self.plan)
                if kind=='version': plan['actions'][1]['rule_version']='different'
                else: plan['actions'][1]['alternative_ids']=[]
                ledger=copy.deepcopy(self.ledger)
                old=self.old_cost()
                ledger['expense_commitments'].append(old)
                result=self.reconcile(plan=plan,ledger=ledger)
                self.assertEqual(result['state'],'proposed')
                self.assertIn(old['id'],result['retained_commitment_ids'])

    def test_completed_cost_and_history_remain(self):
        old=self.old_cost()
        self.p.complete('b')
        self.plan['actions'][1]=copy.deepcopy(self.p.action('b'))
        self.ledger['expense_commitments'].append(old)
        before=copy.deepcopy(self.plan)
        result=self.reconcile()
        self.assertIn(old['id'],result['retained_commitment_ids'])
        self.assertEqual(self.plan,before)

    def test_exclusive_selection_is_all_or_nothing(self):
        result=self.reconcile(['a','b'])
        self.assertEqual(result['state'],'needs_clarification')
        self.assertEqual(result['action_alternatives'],[])

    def test_blocked_stale_future_version_and_past_costs(self):
        for change in ({'status':'blocked'},{'input_freshness':'stale'}):
            plan=copy.deepcopy(self.plan);plan['actions'][0].update(change)
            self.assertEqual(self.reconcile(plan=plan)['state'],'needs_clarification')
        self.plan['actions'][0]['cost_items'][0]['date']='2026-10-10'
        self.assertEqual(self.reconcile()['state'],'needs_clarification')
        self.plan['actions'][0]['input_case_version']=2
        with self.assertRaises(InvalidInput): self.reconcile()

    def test_authoritative_amount_validation_beyond_json_shape(self):
        for amount in (1.0,True,-1,'200'):
            self.plan['actions'][0]['cost_items'][0]['amount_cents']=amount
            with self.assertRaises(InvalidInput):self.reconcile()
        self.plan['actions'][0]['cost_items'][0]['amount_cents']=3500
        self.ledger['money_sources'][0]['balance_cents']=True
        with self.assertRaises(FinanceInputError):self.request()

    def test_canonical_finance_results_through_boundary_consumption(self):
        scenarios=[{'id':'coverage','label':'Week','support':[finance_fixtures.coverage(state='hypothetical')]},
          {'id':'day8','label':'Early','support':[finance_fixtures.coverage(state='hypothetical')],'receipts':[finance_fixtures.receipt()]},
          {'id':'day12','label':'Late','support':[finance_fixtures.coverage(state='hypothetical')],'receipts':[finance_fixtures.receipt(when='2026-10-21')]}]
        original=finance_fixtures.canonical()
        checked=reconcile_action_costs(self.plan,original,[],input_case_version=1,as_of=NOW,time_zone=ZONE,start_date='2026-10-10')
        result=compare_financial_scenarios(checked['comparison_ledger'],start_date='2026-10-10',time_zone=ZONE,input_case_version=1,scenarios=scenarios)
        self.assertEqual(result['baseline']['first_gap']['day'],5)
        self.assertEqual(result['baseline']['ending_projected_position_cents'],-64000)
        self.assertEqual([f['ending_projected_position_cents'] for f in result['scenarios']],[-22000,28000,28000])
        outcomes={f['scenario_id']:f for f in result['scenarios']}
        self.assertEqual(outcomes['coverage']['first_gap']['day'],11)
        self.assertIsNone(outcomes['day8']['first_gap'])
        self.assertEqual(outcomes['day12']['first_gap']['day'],11)

    def test_finance_request_deduplicates_and_names_versions_and_completed(self):
        self.p.complete('b');self.plan['actions'][1]=copy.deepcopy(self.p.action('b'))
        first=self.request(changed=['expense_commitments:food','money_sources:cash'])
        second=self.request(changed=['money_sources:cash','expense_commitments:food'])
        self.assertEqual(first,second)
        self.assertEqual(first['affected_action_ids'],['a'])
        self.assertEqual(first['preserved_action_ids'],['b'])
        self.assertEqual(first['input_case_version'],1)
        self.assertNotEqual(first['request_id'],self.request(case_version=2)['request_id'])
        validate('PlannerReassessmentRequest',first)

    def test_no_reassessment_effect_when_unchanged_complete(self):
        previous=forecast_finances(self.ledger,start_date=START,time_zone=ZONE,input_case_version=1)
        result=self.request(previous=previous,changed=[])
        self.assertFalse(result['required'])
        self.assertEqual(result['affected_action_ids'],[])

    def test_incomplete_and_gap_changes_request_clarification(self):
        previous=forecast_finances(self.ledger,start_date=START,time_zone=ZONE,input_case_version=1)
        value=copy.deepcopy(self.ledger);value['money_sources'][0]['balance_cents']=0
        result=self.request(ledger=value,previous=previous)
        self.assertIn('funding_gap_worsened',result['reasons'])
        value['expense_commitments'][0]['amount_cents']=None
        self.assertIn('finance_inputs_need_clarification',self.request(ledger=value)['reasons'])

    def test_reassessment_rejects_unknown_changed_refs_and_invalid_previous(self):
        with self.assertRaises(InvalidInput): self.request(changed=['money_sources:other_case'])
        with self.assertRaises(InvalidInput): self.request(previous={'input_case_version':1,'baseline':{}})

    def test_no_car_replanning_keeps_completed_work_and_online_alternative(self):
        from backend.stillhere.knowledge.rules import ProgramRuleStore, build_query
        snapshot=empty_case('case_no_car',ZONE,NOW)
        snapshot['facts']={'document_issuing_state':application_fixtures.fact('CO'),
            'has_car':application_fixtures.fact(True),'office_transport_available':application_fixtures.fact(True),
            'internet_access':application_fixtures.fact(True)}
        rules=ProgramRuleStore().lookup(build_query(snapshot,{'program_id':'co_state_id_replacement'},NOW))
        evaluated=evaluate_options(snapshot,rules)
        prior=revise_plan(snapshot['plan'],evaluated,NOW,'initial','a'*64)
        completed=next(a for a in prior['actions'] if a['execution_mode']=='online')
        completed.update(status='completed',history=[{'event_id':'reported_online','from_status':'waiting','status':'completed',
            'reason_code':None,'occurred_at':NOW,'received_at':NOW,'provenance':'user_reported'}])
        completed_history=copy.deepcopy(completed['history'])
        snapshot['plan']=prior;snapshot['case_version']=2
        snapshot['facts']['has_car']=application_fixtures.fact(False)
        snapshot['facts']['office_transport_available']=application_fixtures.fact(False)
        rules=ProgramRuleStore().lookup(build_query(snapshot,{'program_id':'co_state_id_replacement'},NOW))
        evaluated=evaluate_options(snapshot,rules)
        plan=revise_plan(snapshot['plan'],evaluated,NOW,'replan','b'*64)
        office=next(a for a in plan['actions'] if a['execution_mode']=='in_person')
        online=next(a for a in plan['actions'] if a['execution_mode']=='online')
        self.assertEqual(office['status'],'blocked')
        self.assertIn(online['id'],office['alternative_ids'])
        self.assertEqual(online['status'],'completed')
        self.assertEqual(online['history'],completed_history)
        before=copy.deepcopy(plan)
        result=finance_planner_request(plan,self.ledger,None,case_id=snapshot['case_id'],input_case_version=2,
          changed_record_ids=['expense_commitments:food'],start_date=START,time_zone=ZONE)
        self.assertIn(office['id'],result['affected_action_ids'])
        self.assertEqual(result['preserved_action_ids'],[online['id']])
        self.assertEqual(plan,before)

    def test_dependency_ordering_correction_preserves_audit_and_spending(self):
        self.p.action('a')['requirements']=[planner_fixtures.node('done','action')]
        link=self.p.link(kind='action',target='b',node_id='done')
        ordered=assemble_dependencies(self.p.plan,case_id='synthetic_case',input_case_version=1,
            links=[link],evidence=[],as_of=NOW)
        self.assertEqual([a['id'] for a in ordered['actions']],['b','a'])
        self.p.complete('b')
        resolved=assemble_dependencies(self.p.plan,case_id='synthetic_case',input_case_version=1,
            links=[link],evidence=[],as_of=NOW)
        original=copy.deepcopy(next(a for a in resolved['actions'] if a['id']=='b')['history'])
        corrected=propose_completion_correction(resolved,{'action_id':'b','completion_event_id':'completion','reason_code':'reported_in_error'},
            event_id='correction',occurred_at=LATER,received_at=LATER,input_case_version=1)
        task=next(a for a in corrected['plan']['actions'] if a['id']=='b')
        self.assertEqual(task['history'][:-1],original)
        self.assertEqual(task['history'][-1]['correction_of'],'completion')
        self.assertEqual(corrected['affected_action_ids'],['a','b'])
        self.assertFalse(corrected['financial_reversal'])
        validate('CompletionCorrectionProposal',corrected)

    def test_correction_replay_invalid_reference_and_input_immutability(self):
        self.p.complete('b');before=copy.deepcopy(self.p.plan)
        for event,ref in [('completion','completion'),('correction','missing')]:
            with self.assertRaises(InvalidInput):
                propose_completion_correction(self.p.plan,{'action_id':'b','completion_event_id':ref,'reason_code':'reported_in_error'},
                    event_id=event,occurred_at=LATER,received_at=LATER,input_case_version=1)
        self.assertEqual(self.p.plan,before)

    def test_household_record_labels_cannot_create_confirmation(self):
        self.p.action('a')['requirements']=[planner_fixtures.node('confirmed','authority_confirmation')]
        link=self.p.link(kind='confirmation',target='confirm',node_id='confirmed')
        for boundary in (None,{'records':[self.p.confirmation()]}):
            with self.assertRaises(InvalidInput):
                assemble_dependencies(self.p.plan,case_id='synthetic_case',input_case_version=1,links=[link],evidence=[],
                    confirmation_ids=['confirm'],trusted_boundary=boundary,as_of=NOW)
        result=assemble_dependencies(self.p.plan,case_id='synthetic_case',input_case_version=1,links=[link],evidence=[],as_of=NOW)
        self.assertEqual(next(a for a in result['actions'] if a['id']=='a')['requirements'][0]['state'],'unknown')

    def test_trusted_backend_selector_and_domain_scope_checks(self):
        self.p.action('a')['requirements']=[planner_fixtures.node('confirmed','authority_confirmation')]
        link=self.p.link(kind='confirmation',target='confirm',node_id='confirmed')
        record=self.p.confirmation()
        boundary=TrustedRecordBoundary(resolver=lambda case,kind,selected: {'records':[record],'sources':[]})
        result=assemble_dependencies(self.p.plan,case_id='synthetic_case',input_case_version=1,links=[link],evidence=[],
                    confirmation_ids=['confirm'],trusted_boundary=boundary,as_of=NOW)
        self.assertEqual(next(a for a in result['actions'] if a['id']=='a')['requirements'][0]['state'],'satisfied')
        record['case_id']='other_case'
        with self.assertRaises(InvalidInput):boundary.select('synthetic_case','planner_confirmation',['confirm'])

    def test_trusted_sources_do_not_bypass_expiry(self):
        self.p.action('a')['requirements']=[planner_fixtures.node('confirmed','authority_confirmation')]
        record=self.p.confirmation(expires_at=NOW)
        boundary=TrustedRecordBoundary(resolver=lambda *args:{'records':[record],'sources':[]})
        result=assemble_dependencies(self.p.plan,case_id='synthetic_case',input_case_version=1,
            links=[self.p.link(kind='confirmation',target='confirm',node_id='confirmed')],evidence=[],
            confirmation_ids=['confirm'],trusted_boundary=boundary,as_of=NOW)
        self.assertEqual(next(a for a in result['actions'] if a['id']=='a')['requirements'][0]['state'],'unknown')

    def test_application_approval_without_money_or_agency_verification(self):
        before=copy.deepcopy(self.a.snapshot)
        result=self.report()
        self.assertEqual(result['application']['stage_report']['stage'],'approved')
        self.assertIsNone(result['application']['agency_outcome'])
        self.assertEqual(result['application']['preparation_state'],'pending')
        self.assertEqual(result['application']['prepared_at'],NOW)
        self.assertEqual(result['application']['input_case_version'],1)
        self.assertEqual(self.a.snapshot,before)
        self.assertNotIn('finance',result)
        validate('ApplicationBoundaryResult',result)

    def test_unavailable_rules_report_only_and_current_rules_delegate(self):
        args={'application_id':'app1','stage_change':{'stage':'submitted','corrects_event_id':None}}
        result=update_application_boundary(self.a.snapshot,args,None,event_id='submitted',occurred_at=NOW,received_at=NOW)
        self.assertEqual(result['mode'],'report_only')
        self.assertFalse(result['preparation_refreshed'])
        result=update_application_boundary(self.a.snapshot,args,self.a.rules(),event_id='submitted',occurred_at=NOW,received_at=NOW)
        self.assertEqual(result['mode'],'current_rules')
        validate('ApplicationBoundaryResult',result)

    def test_trusted_application_approval_still_never_creates_received_money(self):
        receipt=self.a.agency()
        source=self.a.snapshot['sources'].pop()
        boundary=TrustedRecordBoundary(resolver=lambda *args:{'records':[receipt],'sources':[source]})
        result=update_application_boundary(self.a.snapshot,{'application_id':'app1','stage_change':{'stage':'approved','corrects_event_id':None}},
            self.a.rules(),event_id='approved',occurred_at=NOW,received_at=NOW,receipt_ids=['receipt1'],trusted_boundary=boundary)
        self.assertEqual(result['application']['agency_outcome']['stage'],'approved')
        self.assertEqual(result['application']['stage_report']['stage'],'approved')
        self.assertEqual(result['household_eligibility'],'unknown')
        self.assertNotIn('finance',result)
        self.assertEqual(self.a.snapshot['finance']['ledger']['money_sources'],[])
        validate('ApplicationBoundaryResult',result)

    def test_public_stale_or_expired_source_cannot_supply_agency_verification(self):
        for changes in ({'verification_state':'unverified'},{'freshness':'stale'},{'expires_at':NOW},
                        {'scope':{'case_id':'other_case','application_id':'app1','program_id':application_fixtures.PROGRAM}}):
            with self.subTest(changes=changes):
                receipt=self.a.agency();source=self.a.snapshot['sources'].pop();source.update(changes)
                boundary=TrustedRecordBoundary(resolver=lambda *args:{'records':[receipt],'sources':[source]})
                with self.assertRaises(InvalidInput):
                    update_application_boundary(self.a.snapshot,{'application_id':'app1','stage_change':{'stage':'approved','corrects_event_id':None}},
                        self.a.rules(),event_id='approved',occurred_at=NOW,received_at=NOW,receipt_ids=['receipt1'],trusted_boundary=boundary)

    def test_stale_rules_allow_report_but_not_preparation(self):
        rules=self.a.rules();rules['state']='unavailable';rules['rules']=[];rules['sources']=[]
        result=update_application_boundary(self.a.snapshot,{'application_id':'app1','stage_change':{'stage':'approved','corrects_event_id':None}},
             rules,event_id='approved',occurred_at=NOW,received_at=NOW)
        self.assertEqual(result['application']['preparation_state'],'pending')
        self.assertFalse(result['preparation_refreshed'])

    def test_actual_expired_published_rules_choose_report_only(self):
        now='2027-01-11T06:00:00Z'
        rules=self.a.rules(now=now)
        self.assertEqual(rules['state'],'stale')
        result=update_application_boundary(self.a.snapshot,{'application_id':'app1','stage_change':{'stage':'submitted','corrects_event_id':None}},
            rules,event_id='late_report',occurred_at=NOW,received_at=now)
        self.assertEqual(result['mode'],'report_only')
        self.assertEqual(result['application']['prepared_at'],NOW)
        self.assertFalse(result['preparation_refreshed'])

    def test_available_misscoped_rules_never_fall_back_to_report_only(self):
        rules=self.a.rules();rules['query']['input_case_version']=2
        with self.assertRaises(InvalidInput):update_application_boundary(self.a.snapshot,{'application_id':'app1','stage_change':{'stage':'submitted','corrects_event_id':None}},
             rules,event_id='submitted',occurred_at=NOW,received_at=NOW)

    def test_invalidation_preserves_stage_reports_and_evidence_availability(self):
        approved=self.a.stage('approved');self.a.accept(approved)
        self.a.snapshot['evidence'][0]=application_fixtures.evidence(state='available')
        before=copy.deepcopy(self.a.snapshot)
        for changes in ({'changed_fact_keys':['email_access']},{'changed_rule_ids':[self.a.snapshot['applications'][0]['rule_id']]},
                        {'changed_evidence_ids':['proof1']},{'changed_source_ids':[application_fixtures.SOURCE]}):
            result=invalidate_applications(self.a.snapshot,target_case_version=3,**changes)
            app=result['applications'][0]
            self.assertEqual(app['preparation_state'],'pending')
            self.assertEqual(app['stage_report'],before['applications'][0]['stage_report'])
            self.assertEqual(app['history'],before['applications'][0]['history'])
            self.assertEqual(result['evidence'],before['evidence'])
            self.assertEqual(result['affected_application_ids'],['app1'])
            validate('ApplicationInvalidationProposal',result)
        self.assertEqual(self.a.snapshot,before)

    def test_unrelated_application_invalidation_does_not_refresh_or_overwrite(self):
        prior=copy.deepcopy(self.a.snapshot['applications'])
        result=invalidate_applications(self.a.snapshot,target_case_version=2,changed_fact_keys=['has_car'])
        self.assertEqual(result['affected_application_ids'],[])
        self.assertEqual(result['applications'],prior)

    def test_report_corrections_keep_original_and_reject_replay(self):
        result=self.report();self.a.snapshot['applications']=[result['application']]
        args={'application_id':'app1','stage_change':{'stage':'submitted','corrects_event_id':'report1'}}
        corrected=report_application_only(self.a.snapshot,args,event_id='corrected',occurred_at=LATER,received_at=LATER)
        self.assertEqual(corrected['application']['history'][0],result['application']['history'][0])
        self.assertEqual(corrected['application']['stage_report']['corrects_event_id'],'report1')
        with self.assertRaises(InvalidInput):self.report()

    def test_report_only_rejects_authority_fields_evidence_edits_and_future_time(self):
        for extra in ({'agency_outcome':{'stage':'approved'}},{'agency_receipts':[]},{'evidence_changes':[{'evidence_id':'proof1','state':'available'}]}):
            with self.assertRaises(InvalidInput):report_application_only(self.a.snapshot,{'application_id':'app1',
                'stage_change':{'stage':'submitted','corrects_event_id':None},**extra},event_id='bad',occurred_at=NOW,received_at=NOW)
        with self.assertRaises(InvalidInput):report_application_only(self.a.snapshot,{'application_id':'app1','stage_change':{'stage':'submitted','corrects_event_id':None}},
                event_id='future',occurred_at=LATER,received_at=NOW)

    def test_report_only_capacity_does_not_drop_history(self):
        app=self.a.snapshot['applications'][0]
        app['history']=[{'event_id':'event'+str(i),'observed_at':NOW,'received_at':NOW,'stage_change':None,
                         'correspondence_id':None,'evidence_changes':[]} for i in range(64)]
        before=copy.deepcopy(self.a.snapshot)
        with self.assertRaises(InvalidInput):self.report()
        self.assertEqual(self.a.snapshot,before)

    def test_report_only_rejects_corrupted_audit_and_graph(self):
        for kind in ('cycle','duplicate','active_report'):
            snap=copy.deepcopy(self.a.snapshot)
            if kind=='cycle':snap['applications'][0]['checklist'][0]['children']=['root']
            elif kind=='duplicate':snap['applications'][0]['checklist'].append(copy.deepcopy(snap['applications'][0]['checklist'][0]))
            else:snap['applications'][0]['stage_report']={'stage':'approved','corrects_event_id':None,'event_id':'forged','observed_at':NOW,'received_at':NOW,'provenance':'user_reported'}
            with self.assertRaises(InvalidInput):report_application_only(snap,{'application_id':'app1','stage_change':{'stage':'submitted','corrects_event_id':None}},
                event_id='bad',occurred_at=NOW,received_at=NOW)

    def test_output_alias_isolation_and_determinism(self):
        before=copy.deepcopy((self.plan,self.ledger,self.a.snapshot))
        result=self.reconcile();self.assertEqual(result,self.reconcile())
        result['comparison_ledger']['money_sources'][0]['balance_cents']=123
        request=self.request();request['forecast']['baseline']['daily_projections'].clear()
        report=self.report();report['application']['history'].clear()
        self.assertEqual((self.plan,self.ledger,self.a.snapshot),before)

    def test_bounds_nonfinite_and_duplicate_inputs(self):
        with self.assertRaises(InvalidInput):self.reconcile(['a','a'])
        with self.assertRaises(InvalidInput):self.request(changed=['x']*257)
        bad=copy.deepcopy(self.ledger);bad['money_sources'][0]['balance_cents']=float('nan')
        with self.assertRaises(InvalidInput):self.reconcile(ledger=bad)

    def test_proposed_schema_is_draft_2020_12(self):
        import jsonschema
        from referencing import Registry, Resource
        root=Path(__file__).resolve().parents[1]/'contracts'
        schema=json.loads((root/'parallel/domain-boundaries.schema.json').read_text())
        jsonschema.Draft202012Validator.check_schema(schema)
        registry=Registry()
        files=['case-service.schema.json',*[f'parallel/{name}.schema.json' for name in
            ('planner','finance','applications','domain-boundaries')]]
        for filename in files:
            contents=json.loads((root/filename).read_text())
            registry=registry.with_resource('https://stillhere.test/contracts/'+filename,
                                           Resource.from_contents(contents))
            if contents.get('$id','').startswith(('urn:','https:')):
                registry=registry.with_resource(contents['$id'],Resource.from_contents(contents))
        for name,result in [('CostReconciliation',self.reconcile()),
                            ('PlannerReassessmentRequest',self.request()),
                            ('ApplicationBoundaryResult',self.report())]:
            shape={'$schema':schema['$schema'],
                '$ref':'https://stillhere.test/contracts/parallel/domain-boundaries.schema.json#/$defs/'+name}
            jsonschema.Draft202012Validator(shape,registry=registry).validate(result)


class SharedProposalReviewTests(unittest.TestCase):
    def test_delivered_shared_patches_with_disposable_cases_in_isolated_process(self):
        # Applies only the delivered review text inside a fresh process. No
        # shared source/schema is edited, and no installed integration claim
        # follows from this simulation. This catches real transaction, replay,
        # effect identity, authority and report-only assembly errors.
        import os
        import subprocess
        import sys
        root = Path(__file__).resolve().parents[1]
        script = r'''
"""Isolated-process synthetic checks of review diffs; no shared-file edits."""
import copy
import runpy
import tempfile
from pathlib import Path
from unittest.mock import patch

from backend.stillhere import contracts, commands, integration, service
from tests.test_domain_boundaries import DomainBoundaryTests, NOW, LATER, START

root=Path.cwd()
handoff=(root/'docs/parallel/domain-boundaries-handoff.md').read_text()
schema_code=handoff.split('## Exact shared schema proposal')[1].split('```python\n')[1].split('\n```')[0]
namespace={}
exec(compile(schema_code,'reviewed_schema_proposal','exec'),namespace)
schema_builder=namespace['proposed_shared_schema']
contracts.SCHEMA=schema_builder(contracts.SCHEMA, root/'contracts')
# Parse only the exact code hunks in the delivered handoff, reconstruct in memory.
import difflib
document=(root/'docs/parallel/domain-boundaries-handoff.md').read_text()
for name,module in [('commands',commands),('integration',integration),('service',service)]:
    filename='backend/stillhere/'+name+'.py'
    body=document.split('### '+filename+'\n\n```diff\n')[1].split('\n```')[0]
    original=(root/filename).read_text().splitlines(True)
    result=[];cursor=0
    import re
    lines=body.splitlines(True)
    for line in lines:
        if line.startswith(('---','+++')):continue
        if line.startswith('@@'):
            match=re.match(r'@@ -(\d+)',line)
            start=int(match[1])-1
            result.extend(original[cursor:start]);cursor=start
        elif line.startswith(' '):
            assert original[cursor].rstrip('\n')==line[1:].rstrip('\n')
            result.append(original[cursor]);cursor+=1
        elif line.startswith('-'):
            assert original[cursor].rstrip('\n')==line[1:].rstrip('\n');cursor+=1
        elif line.startswith('+'):result.append(line[1:])
    result.extend(original[cursor:])
    exec(compile(''.join(result),filename,'exec'),module.__dict__)

fixture=DomainBoundaryTests();fixture.setUp()
with tempfile.TemporaryDirectory() as directory:
    app=service.CaseService(str(Path(directory)/'synthetic.sqlite3'),clock=lambda:LATER)
    token=app.create_session()['session_token']
    def case(identity):
        result=app.create_case(token,{'contract_version':'0.1','event_id':identity,'time_zone':'America/Chicago'})
        assert result['status']=='applied',result['issues']
        return result['case_snapshot']
    def seed(snapshot, case_id):
        snapshot=copy.deepcopy(snapshot);snapshot['case_id']=case_id
        contracts.validate('CaseSnapshot',snapshot)
        with app._transaction() as connection:
            connection.execute('UPDATE cases SET snapshot_json=? WHERE case_id=?',(contracts.canonical_json(snapshot),case_id))
    def command(case_id,event,kind,payload,version=1):
        return {'contract_version':'0.1','case_id':case_id,'event_id':event,'expected_case_version':version,
                'occurred_at':LATER,'channel':'dashboard','type':kind,'payload':payload}
    first=case('case_finance');first['plan']=copy.deepcopy(fixture.plan)
    first['plan']['actions'][0]['cost_items'][0]['amount_cents']=None
    first['finance']['ledger']=copy.deepcopy(fixture.ledger)
    seed(first,first['case_id'])
    cmd=command(first['case_id'],'scenario','scenario.set',{'scenario':{'id':'unknown','label':'Unknown','alternative_ids':['a']},'start_date':START})
    result=app.execute(token,cmd)
    assert result['status']=='applied',result['issues']
    saved=result['case_snapshot']
    assert saved['finance']['scenarios'][0]['state']=='incomplete'
    assert saved['finance']['ledger']['money_sources']==fixture.ledger['money_sources']
    assert saved['finance']['ledger']['actual_events']==[]
    assert app.execute(token,cmd)['status']=='already_applied'
    updated=copy.deepcopy(fixture.ledger['expense_commitments'][0]);updated['amount_cents']=None
    finance_command=command(first['case_id'],'finance','finance.update',{'operation':'set_commitment','record':updated},2)
    financial=app.execute(token,finance_command)
    assert financial['status']=='applied',financial['issues']
    assert financial['case_snapshot']['finance']['baseline']['state']=='incomplete'
    assert app.execute(token,finance_command)['status']=='already_applied'
    with app._connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM planner_effects').fetchone()[0]==1
    forged=command(first['case_id'],'forged','finance.update',{'operation':'set_commitment','record':{
        'id':'forged','category':'documents','amount_cents':0,'date':START,'essential':False,'origin':'recovery_planner'}},3)
    assert app.execute(token,forged)['status']=='rejected'

    second=case('case_application');seed(fixture.a.snapshot,second['case_id'])
    cmd=command(second['case_id'],'approved','application.update',{'application_id':'app1','stage_change':{'stage':'approved','corrects_event_id':None}})
    with patch.object(app,'_application_rules',side_effect=service.ServiceError(503,'application_rules_unavailable','Current rules unavailable.',True)):
        result=app.execute(token,cmd)
        assert result['status']=='applied',result['issues']
        assert result['case_snapshot']['applications'][0]['preparation_state']=='pending'
        assert result['case_snapshot']['applications'][0]['agency_outcome'] is None
        assert result['case_snapshot']['finance']['ledger']['money_sources']==[]
        assert app.execute(token,cmd)['status']=='already_applied'
    changed=command(second['case_id'],'fact','fact.correct',{'fact_key':'email_access','value':False,'observed_at':LATER},2)
    assert app.execute(token,changed)['status']=='applied'

    third=case('case_correction');fixture.p.complete('b');third['plan']=copy.deepcopy(fixture.p.plan)
    seed(third,third['case_id'])
    cmd=command(third['case_id'],'corrected','task.update',{'action_id':'b','completion_event_id':'completion','reason_code':'reported_in_error'})
    result=app.execute(token,cmd)
    assert result['status']=='applied',result['issues']
    action=next(a for a in result['case_snapshot']['plan']['actions'] if a['id']=='b')
    assert [h['event_id'] for h in action['history']]==['completion','corrected']
    assert result['case_snapshot']['plan']['version']==third['plan']['version']+1
    assert app.execute(token,cmd)['status']=='already_applied'
print('Review proposals: synthetic scenario/replay/effect dedup, forged ownership rejection, report-only approval/fact invalidation, completion correction/replay pass. Shared files untouched.')
'''
        result = subprocess.run(
            [sys.executable, '-W', 'error::ResourceWarning', '-c', script],
            cwd=root, env={'PATH': os.defpath, 'PYTHONDONTWRITEBYTECODE': '1'},
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
