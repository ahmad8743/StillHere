"""Proposed C08 shape agreement; runtime still owns relational validation."""

import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator, FormatChecker

from backend.stillhere.finance import (compare_financial_scenarios, finance_reassessment,
    prepare_forecast_publication, set_financial_scenario)
from tests.test_finance import START, ZONE, canonical, coverage, expense, ledger, receipt, source
from tests.test_finance_updates import NOW, actual, apply, post
from tests.test_finance_scenarios import option, scenario, taxi_ledger

SCHEMA = json.loads((Path(__file__).resolve().parents[1] / 'contracts/parallel/finance.schema.json').read_text())


class FinanceSchemaTests(unittest.TestCase):
    def validate(self, definition, value):
        schema = {**SCHEMA, '$ref': '#/$defs/' + definition}
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)

    def test_schema_is_valid_draft_2020_12(self):
        Draft202012Validator.check_schema(SCHEMA)

    def test_update_request_and_applied_audit_result(self):
        value = ledger()
        payload = {'operation': 'record_expense', 'record': actual()}
        self.validate('FinanceUpdatePayload', payload)
        self.validate('FinanceUpdateRequest', {'ledger': value, 'update': payload, 'event_id': 'demo1',
            'effective_at': NOW, 'received_at': NOW, 'time_zone': ZONE})
        result = apply(value, payload)
        self.validate('FinanceUpdateResult', result)
        self.validate('FinanceLedger', result['next_ledger'])

    def test_clarification_and_rejection_shapes(self):
        self.validate('FinanceUpdateResult', post(record=actual(amount=None)))
        self.validate('FinanceUpdateResult', post(record=actual(amount=-1)))

    def test_transfer_and_receipt_audit_shapes(self):
        value = ledger(money=[source(), source('account', 0)])
        result = post(value, actual(kind='transfer', to_money_source_id='account'))
        self.validate('FinanceUpdateResult', result)
        result = post(record=actual(kind='receipt'))
        self.validate('FinanceUpdateResult', result)

    def test_pending_and_corrected_actual_shapes(self):
        pending = post(record=actual(state='proposed', amount=None))
        self.validate('FinanceUpdateResult', pending)
        value = post()['next_ledger']
        result = apply(value, {'operation': 'correct_actual', 'record_id': 'spent',
            'replacement': actual(amount=1000), 'reason': 'Synthetic corrected receipt'}, 'correct')
        self.validate('FinanceUpdateResult', result)

    def test_all_four_canonical_forecast_shapes(self):
        scenarios = [{'id': 'coverage', 'label': 'Week', 'support': [coverage(state='hypothetical')]},
            {'id': 'day8', 'label': 'Early', 'support': [coverage(state='hypothetical')], 'receipts': [receipt()]},
            {'id': 'day12', 'label': 'Late', 'support': [coverage(state='hypothetical')],
             'receipts': [receipt(when='2026-10-21')]}]
        result = compare_financial_scenarios(canonical(), start_date=START, time_zone=ZONE,
                                           input_case_version=4, scenarios=scenarios)
        self.validate('ForecastBundle', result)

    def test_unknown_projection_and_restricted_money_shapes(self):
        for value in (ledger(costs=[expense(amount=None)]), ledger(money=[source(restrictions=['food'])]),
                      ledger(money=[source(amount=None, restrictions=None)])):
            with self.subTest(value=value):
                self.validate('ForecastBundle', compare_financial_scenarios(value, start_date=START,
                    time_zone=ZONE, input_case_version=4))

    def test_scenario_set_saved_cost_snapshot_and_comparison_shapes(self):
        self.validate('ScenarioSetRequest', {'ledger': taxi_ledger(), 'scenario': scenario(),
            'event_id': 'scenario1', 'effective_at': NOW, 'received_at': NOW, 'time_zone': ZONE,
            'start_date': START, 'action_alternatives': [option()]})
        result = set_financial_scenario(taxi_ledger(), scenario(), event_id='scenario1',
            effective_at=NOW, received_at=NOW, time_zone=ZONE, start_date=START, action_alternatives=[option()])
        self.validate('FinanceUpdateResult', result)
        self.validate('ForecastBundle', compare_financial_scenarios(result['next_ledger'], start_date=START,
                    time_zone=ZONE, input_case_version=5))

    def test_publication_current_stale_and_reassessment_shapes(self):
        result = compare_financial_scenarios(ledger(), start_date=START, time_zone=ZONE, input_case_version=4)
        for version in (4, 5):
            self.validate('ForecastPublicationResult', prepare_forecast_publication(result,
                current_case_version=version, computed_at=NOW, publication_event_id='forecast4', prior_forecasts=result))
        self.validate('FinanceReassessment', finance_reassessment(None, result, changed_record_ids=[]))

    def test_schema_rejects_bad_money_and_unsupported_operation(self):
        for payload in ({'operation': 'invent_money'}, {'operation': 'record_expense', 'record': actual(amount=True)},
                        {'operation': 'record_expense', 'record': actual(amount=1.0)},
                        {'operation': 'record_expense', 'record': actual(), 'extra': 'unsupported'}):
            with self.subTest(payload=payload):
                schema = {**SCHEMA, '$ref': '#/$defs/FinanceUpdatePayload'}
                # JSON Schema treats 1.0 as an integer; runtime deliberately rejects all floats.
                if payload.get('record', {}).get('amount_cents') == 1.0 and type(payload['record']['amount_cents']) is float:
                    self.assertEqual(apply(ledger(), payload)['status'], 'rejected')
                else:
                    self.assertFalse(Draft202012Validator(schema).is_valid(payload))


if __name__ == '__main__':
    unittest.main()
