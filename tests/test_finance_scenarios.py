"""Synthetic planner-independent scenarios and derived-output lifecycle evidence."""

import copy
import json
import unittest

from backend.stillhere.finance import (FinanceInputError, compare_financial_scenarios,
    finance_reassessment, invalidate_financial_outputs, prepare_forecast_publication,
    set_financial_scenario, validate_financial_scenario)
from tests.test_finance import START, ZONE, canonical, coverage, expense, ledger, receipt


def option(identity="bus", amount=500, **changes):
    return {"id": identity, "label": "Synthetic " + identity,
            "costs": [expense(identity + "-cost", amount, "transport", essential=False,
                              action_id=identity)], "replaces_commitment_ids": ["taxi"], **changes}


def taxi_ledger():
    return ledger(costs=[expense(), expense("taxi", 3000, "transport", essential=False, action_id="taxi-action")])


def scenario(identity="bus-path", **changes):
    return {"id": identity, "label": "Synthetic bus path", "alternative_ids": ["bus"], **changes}


def compare(value=None, scenarios=None, alternatives=None, **changes):
    return compare_financial_scenarios(taxi_ledger() if value is None else value,
        start_date=START, time_zone=ZONE, input_case_version=4,
        scenarios=[scenario()] if scenarios is None else scenarios,
        action_alternatives=[option()] if alternatives is None else alternatives, **changes)


class ScenarioTests(unittest.TestCase):
    def test_explicit_replacement_only_changes_hypothetical_action_cost(self):
        value = taxi_ledger()
        before = copy.deepcopy(value)
        result = compare(value)
        self.assertEqual(value, before)
        self.assertEqual(result["baseline"]["ending_projected_position_cents"], 25000)
        self.assertEqual(result["scenarios"][0]["ending_projected_position_cents"], 27500)
        assumptions = result["scenarios"][0]["scenario_assumptions"]
        self.assertEqual(assumptions["replaced_commitment_ids"], ["taxi"])
        self.assertEqual(assumptions["action_costs"][0]["action_id"], "bus")
        self.assertIn("food", result["scenarios"][0]["daily_projections"][0]["expense_ids"])
        json.dumps(result, allow_nan=False)

    def test_essential_expenses_cannot_be_replaced_even_if_action_linked(self):
        value = taxi_ledger()
        value["expense_commitments"][1]["essential"] = True
        with self.assertRaises(FinanceInputError):
            compare(value)

    def test_nonaction_expenses_cannot_be_replaced(self):
        value = taxi_ledger()
        del value["expense_commitments"][1]["action_id"]
        with self.assertRaises(FinanceInputError):
            compare(value)

    def test_unknown_action_cost_produces_incomplete_scenario_only(self):
        result = compare(alternatives=[option(amount=None)])
        self.assertEqual(result["baseline"]["state"], "complete")
        self.assertEqual(result["scenarios"][0]["state"], "incomplete")
        self.assertIsNone(result["scenarios"][0]["ending_projected_position_cents"])
        self.assertIsNone(result["scenarios"][0]["scenario_assumptions"]["action_costs"][0]["amount_cents"])

    def test_dated_action_cost_not_brought_forward(self):
        alternative = option()
        alternative["costs"][0]["date"] = "2026-10-17"
        result = compare(alternatives=[alternative])["scenarios"][0]
        self.assertNotIn("bus", result["daily_projections"][0]["action_ids"])
        self.assertIn("bus", result["daily_projections"][7]["action_ids"])

    def test_alternative_addition_does_not_infer_replacement(self):
        result = compare(alternatives=[option(replaces_commitment_ids=[])])["scenarios"][0]
        self.assertEqual(result["ending_projected_position_cents"], 24500)
        self.assertIn("taxi", result["daily_projections"][0]["expense_ids"])

    def test_selected_alternative_must_exist(self):
        with self.assertRaises(FinanceInputError):
            compare(scenarios=[scenario(alternative_ids=["missing"])])

    def test_overlapping_paths_cannot_replace_same_action_twice(self):
        with self.assertRaises(FinanceInputError):
            compare(scenarios=[scenario(alternative_ids=["bus", "walk"])], alternatives=[option(), option("walk")])

    def test_distinct_scenarios_are_independent_and_sorted(self):
        result = compare(scenarios=[scenario("walk", alternative_ids=["walk"]), scenario()],
                         alternatives=[option(), option("walk", 0)])
        self.assertEqual([item["scenario_id"] for item in result["scenarios"]], ["bus-path", "walk"])
        self.assertEqual([item["ending_projected_position_cents"] for item in result["scenarios"]], [27500, 28000])

    def test_fourth_scenario_rejected(self):
        with self.assertRaises(FinanceInputError):
            compare(scenarios=[scenario(str(index)) for index in range(4)])

    def test_baseline_reserved_and_duplicate_scenario_id_rejected(self):
        for scenarios in ([scenario("baseline")], [scenario(), scenario()]):
            with self.subTest(scenarios=scenarios), self.assertRaises(FinanceInputError):
                compare(scenarios=scenarios)

    def test_actual_or_unknown_fulfillment_cannot_be_replaced(self):
        for fulfilled in (100, None):
            value = taxi_ledger()
            value["expense_commitments"][1]["fulfilled_cents"] = fulfilled
            with self.subTest(fulfilled=fulfilled), self.assertRaises(FinanceInputError):
                compare(value)

    def test_pending_actual_match_prevents_replacement(self):
        value = taxi_ledger()
        value["actual_events"] = [{"id": "pending", "state": "proposed", "commitment_id": "taxi"}]
        with self.assertRaises(FinanceInputError):
            compare(value)

    def test_support_linked_to_replaced_commitment_requires_explicit_remapping(self):
        value = taxi_ledger()
        value["support"] = [coverage(categories=["transport"], commitment_ids=["taxi"])]
        with self.assertRaises(FinanceInputError):
            compare(value)

    def test_action_cost_ids_cannot_collide_with_baseline(self):
        alternative = option()
        alternative["costs"][0]["id"] = "food"
        with self.assertRaises(FinanceInputError):
            compare(alternatives=[alternative])

    def test_action_cost_requires_id_and_cannot_claim_fulfillment(self):
        for field, value in (("action_id", None), ("fulfilled_cents", 10)):
            alternative = option()
            alternative["costs"][0][field] = value
            with self.subTest(field=field), self.assertRaises(FinanceInputError):
                compare(alternatives=[alternative])

    def test_empty_cost_list_cannot_turn_missing_cost_into_free_replacement(self):
        with self.assertRaises(FinanceInputError):
            compare(alternatives=[option(costs=[])])

    def test_action_cost_unknowns_and_invalid_values_validate_even_unselected(self):
        with self.assertRaises(FinanceInputError):
            validate_financial_scenario(
                taxi_ledger(), scenario(alternative_ids=[]), start_date=START, time_zone=ZONE,
                action_alternatives=[option(amount=True)])

    def test_existing_additive_canonical_results_are_preserved(self):
        scenarios = [{"id": "coverage", "label": "Week", "support": [coverage(state="hypothetical")]},
                     {"id": "day8", "label": "Early", "support": [coverage(state="hypothetical")], "receipts": [receipt()]},
                     {"id": "day12", "label": "Late", "support": [coverage(state="hypothetical")], "receipts": [receipt(when="2026-10-21")]}]
        result = compare(canonical(), scenarios=scenarios, alternatives=[])
        self.assertEqual(result["baseline"]["first_gap"]["day"], 5)
        self.assertEqual(result["baseline"]["ending_projected_position_cents"], -64000)
        outcomes = {item["scenario_id"]: item for item in result["scenarios"]}
        self.assertEqual(outcomes["coverage"]["ending_projected_position_cents"], -22000)
        self.assertEqual(outcomes["day12"]["ending_projected_position_cents"], 28000)
        self.assertEqual(outcomes["day12"]["first_gap"]["day"], 11)
        self.assertIsNone(outcomes["day8"]["first_gap"])

    def test_scenario_set_stores_cost_snapshot_without_actual_money_changes(self):
        value = taxi_ledger()
        result = set_financial_scenario(value, scenario(), event_id="set1", effective_at="2026-10-10T12:00:00Z",
             received_at="2026-10-10T12:01:00Z", time_zone=ZONE, start_date=START, action_alternatives=[option()])
        self.assertEqual(result["status"], "applied", result["issues"])
        next_value = result["next_ledger"]
        for key in ("money_sources", "actual_events", "expense_commitments", "aid", "support"):
            self.assertEqual(next_value[key], value[key])
        result = compare_financial_scenarios(next_value, start_date=START, time_zone=ZONE, input_case_version=5)
        self.assertEqual(result["scenarios"][0]["ending_projected_position_cents"], 27500)

    def test_scenario_set_replays_and_edit_replaces_same_id(self):
        kwargs = dict(effective_at="2026-10-10T12:00:00Z", received_at="2026-10-10T12:01:00Z",
                      time_zone=ZONE, start_date=START, action_alternatives=[option()])
        result = set_financial_scenario(taxi_ledger(), scenario(), event_id="set1", **kwargs)
        value = result["next_ledger"]
        replay = set_financial_scenario(value, scenario(), event_id="set1", **kwargs)
        self.assertTrue(replay["replayed"])
        result = set_financial_scenario(value, scenario(label="Edited label"), event_id="set2", **kwargs)
        self.assertEqual(len(result["next_ledger"]["scenarios"]), 1)
        self.assertEqual(result["next_ledger"]["scenarios"][0]["label"], "Edited label")

    def test_stored_quote_cannot_silently_change(self):
        value = set_financial_scenario(taxi_ledger(), scenario(), event_id="set1", effective_at="2026-10-10T12:00:00Z",
             received_at="2026-10-10T12:01:00Z", time_zone=ZONE, start_date=START, action_alternatives=[option()])["next_ledger"]
        with self.assertRaises(FinanceInputError):
            compare_financial_scenarios(value, start_date=START, time_zone=ZONE, input_case_version=5,
                                         action_alternatives=[option(amount=900)])

    def test_invalid_scenario_set_returns_unapplied_proposal(self):
        value = taxi_ledger()
        before = copy.deepcopy(value)
        result = set_financial_scenario(value, scenario("baseline"), event_id="set1", effective_at="2026-10-10T12:00:00Z",
             received_at="2026-10-10T12:01:00Z", time_zone=ZONE, start_date=START, action_alternatives=[option()])
        self.assertEqual(result["status"], "rejected")
        self.assertIsNone(result["next_ledger"])
        self.assertEqual(value, before)

    def test_validation_output_is_detached_and_deterministic(self):
        value, choice, alternative = taxi_ledger(), scenario(), option()
        before = copy.deepcopy((value, choice, alternative))
        first = validate_financial_scenario(value, choice, start_date=START, time_zone=ZONE, action_alternatives=[alternative])
        second = validate_financial_scenario(value, choice, start_date=START, time_zone=ZONE, action_alternatives=[alternative])
        self.assertEqual(first, second)
        first["comparison_ledger"]["money_sources"][0]["balance_cents"] = 0
        self.assertEqual((value, choice, alternative), before)


class LifecycleTests(unittest.TestCase):
    def test_current_publication_uses_explicit_receipt_time_and_preserves_version(self):
        forecasts = compare()
        before = copy.deepcopy(forecasts)
        result = prepare_forecast_publication(forecasts, current_case_version=4,
                   computed_at="2026-10-10T12:00:00Z", publication_event_id="forecast:4")
        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["proposed_finance"]["state"], "current")
        self.assertEqual(result["proposed_finance"]["input_case_version"], 4)
        self.assertEqual(forecasts, before)

    def test_stale_calculation_retains_prior_result_as_pending(self):
        prior = compare()
        result = prepare_forecast_publication(compare(), current_case_version=5,
                   computed_at="2026-10-10T12:00:00Z", publication_event_id="forecast:4", prior_forecasts=prior)
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(result["proposed_finance"]["state"], "pending")
        self.assertEqual(result["proposed_finance"]["input_case_version"], 4)
        self.assertEqual(result["proposed_finance"]["pending_input_case_version"], 5)
        self.assertEqual(result["proposed_finance"]["baseline"], prior["baseline"])

    def test_incomplete_results_are_published_as_incomplete(self):
        forecasts = compare(alternatives=[option(amount=None)])
        result = prepare_forecast_publication(forecasts, current_case_version=4,
                   computed_at="2026-10-10T12:00:00Z", publication_event_id="forecast:4")
        self.assertEqual(result["proposed_finance"]["state"], "incomplete")

    def test_invalid_publication_versions_rejected(self):
        for version in (0, True, None):
            with self.subTest(version=version), self.assertRaises(FinanceInputError):
                prepare_forecast_publication(compare(), current_case_version=version,
                   computed_at="2026-10-10T12:00:00Z", publication_event_id="forecast:4")

    def test_projection_version_mismatch_rejected(self):
        forecasts = compare()
        forecasts["baseline"]["input_case_version"] = 3
        with self.assertRaises(FinanceInputError):
            prepare_forecast_publication(forecasts, current_case_version=4,
                   computed_at="2026-10-10T12:00:00Z", publication_event_id="forecast:4")

    def test_invalidation_is_detached_and_retains_old_version(self):
        prior = compare()
        result = invalidate_financial_outputs(prior, target_case_version=5)
        self.assertEqual(result["state"], "pending")
        self.assertEqual(result["input_case_version"], 4)
        self.assertNotIn("state", prior)

    def test_new_and_worsened_gaps_trigger_reassessment_preserving_completed_actions(self):
        before = compare()
        after = compare(ledger(money=[], costs=[expense(amount=50000)]), scenarios=[], alternatives=[])
        request = finance_reassessment(before, after, changed_record_ids=["money_sources:cash"])
        self.assertTrue(request["required"])
        self.assertIn("essential_gap_worsened", request["reasons"])
        self.assertTrue(request["preserve_completed_actions"])
        self.assertEqual(request["input_case_version"], 4)

    def test_resolved_gap_triggers_reassessment(self):
        before = compare(ledger(money=[], costs=[expense(amount=50000)]), scenarios=[], alternatives=[])
        request = finance_reassessment(before, compare(), changed_record_ids=[])
        self.assertIn("essential_gap_resolved", request["reasons"])

    def test_incomplete_next_inputs_trigger_clarification_not_gap_resolution(self):
        before = compare(ledger(money=[], costs=[expense(amount=50000)]), scenarios=[], alternatives=[])
        after = compare(ledger(costs=[expense(amount=None)]), scenarios=[], alternatives=[])
        request = finance_reassessment(before, after, changed_record_ids=[])
        self.assertIn("finance_inputs_need_clarification", request["reasons"])
        self.assertNotIn("funding_gap_resolved", request["reasons"])
        self.assertNotIn("essential_gap_resolved", request["reasons"])

    def test_identical_forecasts_do_not_trigger_reassessment(self):
        forecasts = compare()
        request = finance_reassessment(forecasts, forecasts, changed_record_ids=[])
        self.assertFalse(request["required"])

    def test_changed_available_money_triggers_reassessment_without_a_gap(self):
        from tests.test_finance import source
        before = compare(ledger(costs=[]), scenarios=[], alternatives=[])
        after = compare(ledger(money=[source(amount=25000)], costs=[]), scenarios=[], alternatives=[])
        request = finance_reassessment(before, after, changed_record_ids=["money_sources:cash"])
        self.assertEqual(request["reasons"], ["available_money_changed"])

    def test_malformed_publication_scenario_collection_rejected(self):
        forecasts = compare()
        forecasts["scenarios"] = None
        with self.assertRaises(FinanceInputError):
            prepare_forecast_publication(forecasts, current_case_version=4,
                   computed_at="2026-10-10T12:00:00Z", publication_event_id="forecast:4")


if __name__ == "__main__":
    unittest.main()
