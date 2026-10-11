"""Credential-free synthetic checks of the bounded pure C08 forecast slice."""

import copy
import json
import random
import unittest

from backend.stillhere.finance import FinanceInputError, forecast_finances

START = "2026-10-10"
ZONE = "America/Chicago"
ANCHOR = "2026-10-10T05:00:00Z"


def source(identity="cash", amount=30000, restrictions=(), **changes):
    return {"id": identity, "type": "cash", "currency": "USD", "balance_cents": amount,
            "accessible": True, "as_of": ANCHOR,
            "restrictions": None if restrictions is None else list(restrictions),
            "reflected_event_ids": [], **changes}


def expense(identity="food", amount=2000, category="food", **changes):
    return {"id": identity, "category": category, "amount_cents": amount,
            "date": START, "essential": True, "priority": 10, **changes}


def coverage(identity="coverage", **changes):
    return {"id": identity, "state": "confirmed", "categories": ["food", "lodging"],
            "start_date": START, "end_date": "2026-10-16", "household_coverage": "full",
            "covers_full_cost": True, **changes}


def receipt(identity="award", amount=50000, when="2026-10-17", **changes):
    return {"id": identity, "state": "hypothetical", "amount_cents": amount, "date": when,
            "currency": "USD", "restrictions": [], **changes}


def ledger(money=None, costs=None, **changes):
    return {"money_sources": [source()] if money is None else money,
            "expense_commitments": [expense()] if costs is None else costs,
            "actual_events": [], "aid": [], "support": [], **changes}


def canonical():
    costs = []
    for identity, amount in (("food", 2000), ("lodging", 4000), ("transport", 500)):
        item = expense(identity, amount, identity)
        del item["date"]
        item.update(start_date=START, end_date="2026-10-23")
        costs.append(item)
    costs.append(expense("recovery", 3000, "recovery", action_id="replace_id"))
    return ledger(costs=costs)


def calculate(value, scenarios=None, **changes):
    return forecast_finances(value, start_date=START, time_zone=ZONE,
                             input_case_version=4, scenarios=scenarios, **changes)


class CanonicalFinanceTests(unittest.TestCase):
    def test_all_four_examples_in_one_baseline_plus_three_scenarios(self):
        scenarios = []
        for identity, when in (("coverage", None), ("day8", "2026-10-17"), ("day12", "2026-10-21")):
            scenarios.append({"id": identity, "label": identity,
                              "support": [coverage(state="hypothetical")],
                              "receipts": [] if when is None else [receipt(when=when)]})
        result = calculate(canonical(), scenarios)
        results = {item["scenario_id"]: item for item in [result["baseline"], *result["scenarios"]]}
        self.assertEqual(results["baseline"]["first_gap"]["amount_cents"], 5500)
        self.assertEqual(results["coverage"]["first_gap"]["amount_cents"], 2500)
        self.assertIsNone(results["day8"]["first_gap"])
        self.assertEqual(results["day8"]["ending_projected_position_cents"], 28000)
        self.assertEqual(results["day12"]["first_gap"]["amount_cents"], 2500)
        self.assertEqual(results["day12"]["ending_projected_position_cents"], 28000)

    def test_no_aid_baseline_day_five_55_dollars_and_minus_640(self):
        result = calculate(canonical())["baseline"]
        self.assertEqual(result["state"], "complete")
        self.assertEqual(result["opening_accessible_cents"], 30000)
        self.assertEqual(result["first_gap"]["day"], 5)
        self.assertEqual(result["first_gap"]["date"], "2026-10-14")
        self.assertEqual(result["first_gap"]["amount_cents"], 5500)
        self.assertEqual(result["ending_projected_position_cents"], -64000)
        self.assertEqual(len(result["daily_projections"]), 14)
        self.assertEqual(result["daily_projections"][0]["action_ids"], ["replace_id"])

    def test_confirmed_week_of_food_lodging_day_eleven_25_and_minus_220(self):
        value = canonical()
        value["support"] = [coverage()]
        result = calculate(value)["baseline"]
        self.assertEqual(result["first_gap"]["day"], 11)
        self.assertEqual(result["first_gap"]["amount_cents"], 2500)
        self.assertEqual(result["ending_projected_position_cents"], -22000)
        self.assertEqual(sum(day["support_coverage_cents"] for day in result["daily_projections"]), 42000)

    def test_hypothetical_day_eight_500_dollars_no_gap_ending_280(self):
        value = canonical()
        value["support"] = [coverage()]
        result = calculate(value, [{"id": "day8", "label": "Aid day 8",
                                    "receipts": [receipt()]}])
        comparison = result["scenarios"][0]
        self.assertIsNone(comparison["first_gap"])
        self.assertEqual(comparison["ending_projected_position_cents"], 28000)
        self.assertEqual(result["baseline"]["ending_projected_position_cents"], -22000)
        self.assertEqual(comparison["daily_projections"][7]["receipts_cents"], 50000)

    def test_delayed_day_twelve_preserves_day_eleven_gap_despite_280_ending(self):
        value = canonical()
        value["support"] = [coverage()]
        comparison = calculate(value, [{"id": "day12", "label": "Aid day 12",
                                        "receipts": [receipt(when="2026-10-21")]}])["scenarios"][0]
        self.assertEqual(comparison["first_gap"]["day"], 11)
        self.assertEqual(comparison["first_gap"]["amount_cents"], 2500)
        self.assertEqual(comparison["ending_projected_position_cents"], 28000)


class SupportAndRestrictionsTests(unittest.TestCase):
    def test_food_restrictions_cannot_pay_rent_despite_positive_total(self):
        value = ledger(money=[source(amount=0), source("food_aid", 10000, ["food"])],
                       costs=[expense("rent", 4000, "rent"), expense()])
        result = calculate(value)["baseline"]
        self.assertEqual(result["first_gap"]["amount_cents"], 4000)
        self.assertEqual(result["first_gap"]["expense_ids"], ["rent"])
        self.assertEqual(result["ending_projected_position_cents"], 4000)
        self.assertEqual(result["daily_projections"][0]["restricted_coverage_cents"], 2000)
        self.assertEqual(result["daily_projections"][0]["known_inputs_unrestricted_position_cents"], -4000)

    def test_confirmed_support_then_restricted_then_unrestricted(self):
        value = ledger(money=[source(amount=1000), source("voucher", 700, ["food"])],
                       support=[coverage(categories=["food"], covers_full_cost=False, daily_limit_cents=500)])
        row = calculate(value)["baseline"]["daily_projections"][0]
        self.assertEqual(row["support_coverage_cents"], 500)
        self.assertEqual(row["restricted_coverage_cents"], 700)
        self.assertEqual(row["uncovered_expense_cents"], 800)
        self.assertEqual(row["projected_position_cents"], 200)

    def test_overlapping_full_support_never_removes_expense_twice(self):
        result = calculate(ledger(support=[coverage("a"), coverage("b")]))["baseline"]
        self.assertEqual(result["ending_projected_position_cents"], 30000)
        self.assertEqual(result["daily_projections"][0]["support_coverage_cents"], 2000)
        self.assertEqual(result["daily_projections"][0]["expenses"][0]["support_ids"], ["a"])

    def test_support_limits_span_expenses_and_dates_after_actual_consumption(self):
        value = ledger(costs=[expense("a", 1000), expense("b", 1000),
                              expense("c", 1000, date="2026-10-11"),
                              expense("d", 1000, date="2026-10-12")],
                       support=[coverage(covers_full_cost=False, total_limit_cents=2700,
                                         consumed_cents=200, daily_limit_cents=1500)])
        result = calculate(value)["baseline"]
        self.assertEqual([row["support_coverage_cents"] for row in result["daily_projections"][:3]],
                         [1500, 1000, 0])
        self.assertEqual(result["ending_projected_position_cents"], 28500)

    def test_support_only_applies_to_matching_dates_and_expense_ids(self):
        value = ledger(costs=[expense("a"), expense("b"), expense("c", date="2026-10-11")],
                       support=[coverage(categories=["food"], commitment_ids=["a", "c"], end_date=START)])
        result = calculate(value)["baseline"]
        self.assertEqual(sum(row["support_coverage_cents"] for row in result["daily_projections"]), 2000)
        self.assertEqual(result["ending_projected_position_cents"], 26000)

    def test_hypothetical_ledger_support_never_enters_baseline(self):
        result = calculate(ledger(support=[coverage(state="hypothetical")]))["baseline"]
        self.assertEqual(result["ending_projected_position_cents"], 28000)

    def test_scenario_support_is_additive_and_never_changes_baseline(self):
        result = calculate(ledger(), [{"id": "meals", "label": "If meals confirmed",
                                     "support": [coverage(state="hypothetical")]}])
        self.assertEqual(result["baseline"]["ending_projected_position_cents"], 28000)
        self.assertEqual(result["scenarios"][0]["ending_projected_position_cents"], 30000)
        self.assertEqual(result["scenarios"][0]["scenario_assumptions"]["support"][0]["id"], "coverage")

    def test_narrower_funds_before_flexible_funds_preserves_rent_coverage(self):
        value = ledger(money=[source(amount=0), source("a_flexible", 2000, ["food", "rent"]),
                              source("z_food", 2000, ["food"])],
                       costs=[expense("food"), expense("rent", 2000, "rent")])
        result = calculate(value)["baseline"]
        self.assertIsNone(result["first_gap"])
        self.assertEqual(result["ending_projected_position_cents"], 0)
        self.assertEqual(result["daily_projections"][0]["expenses"][0]["restricted_source_ids"], ["z_food"])

    def test_essential_costs_before_discretionary_then_user_priority(self):
        value = ledger(money=[source(amount=1000)],
                       costs=[expense("a_optional", 1000, essential=False, priority=0),
                              expense("z_essential", 700, priority=2),
                              expense("b_essential", 700, priority=1)])
        row = calculate(value)["baseline"]["daily_projections"][0]
        self.assertEqual(row["expense_ids"], ["b_essential", "z_essential", "a_optional"])
        self.assertEqual([item["unmet_cents"] for item in row["expenses"]], [0, 400, 1000])

    def test_nonessential_gap_and_first_essential_gap_are_distinct(self):
        value = ledger(money=[source(amount=0)],
                       costs=[expense("optional", 100, essential=False),
                              expense("essential", 200, date="2026-10-11")])
        result = calculate(value)["baseline"]
        self.assertEqual(result["first_gap"]["day"], 1)
        self.assertEqual(result["first_essential_gap"]["day"], 2)


class TimingAndReconciledInputTests(unittest.TestCase):
    def test_approved_unreceived_aid_is_not_baseline_cash(self):
        value = ledger(aid=[{"id": "aid", "stage": "approved", "amount_cents": 50000}])
        value["money_sources"].append(source("pending", 50000, aid_id="aid", type="received_assistance"))
        result = calculate(value, [{"id": "award", "label": "If received",
                                   "receipts": [receipt(aid_id="aid", when=START)]}])
        self.assertEqual(result["baseline"]["opening_accessible_cents"], 30000)
        self.assertEqual(result["baseline"]["ending_projected_position_cents"], 28000)
        self.assertEqual(result["scenarios"][0]["ending_projected_position_cents"], 78000)

    def test_received_aid_and_reflected_receipt_are_counted_once(self):
        value = ledger(money=[source(amount=80000, aid_id="aid", reflected_event_ids=["deposit"])],
                       aid=[{"id": "aid", "stage": "received", "amount_cents": 50000,
                             "matching_receipt_id": "deposit"}],
                       actual_events=[{"id": "deposit", "kind": "receipt", "state": "actual", "amount_cents": 50000}])
        result = calculate(value)["baseline"]
        self.assertEqual(result["state"], "complete")
        self.assertEqual(result["ending_projected_position_cents"], 78000)
        self.assertEqual(sum(row["receipts_cents"] for row in result["daily_projections"]), 0)

    def test_reconciled_actual_expense_fulfills_commitment_without_second_outflow(self):
        value = ledger(money=[source(amount=28200, reflected_event_ids=["spent"])],
                       costs=[expense(amount=2000, fulfilled_cents=1800)],
                       actual_events=[{"id": "spent", "kind": "expense", "state": "actual", "amount_cents": 1800}])
        result = calculate(value)["baseline"]
        self.assertEqual(result["ending_projected_position_cents"], 28000)
        self.assertEqual(result["daily_projections"][0]["expenses_due_cents"], 200)

    def test_daily_fulfillment_is_per_occurrence(self):
        item = expense()
        del item["date"]
        item.update(start_date=START, end_date="2026-10-11", fulfilled_cents_by_date={START: 2000})
        result = calculate(ledger(costs=[item]))["baseline"]
        self.assertEqual([row["expenses_due_cents"] for row in result["daily_projections"][:2]], [0, 2000])

    def test_reflected_internal_transfer_is_not_new_household_income(self):
        value = ledger(money=[source(amount=10000, reflected_event_ids=["transfer"]),
                              source("bank", 20000, reflected_event_ids=["transfer"])],
                       actual_events=[{"id": "transfer", "kind": "transfer", "amount_cents": 10000}])
        self.assertEqual(calculate(value)["baseline"]["ending_projected_position_cents"], 28000)

    def test_date_only_same_day_receipt_before_expenses(self):
        result = calculate(ledger(money=[source(amount=0)]),
                           [{"id": "same", "label": "Same day", "receipts": [receipt(amount=2000, when=START)]}])
        self.assertIsNone(result["scenarios"][0]["first_gap"])
        self.assertIsNotNone(result["baseline"]["first_gap"])

    def test_known_late_receipt_cannot_fund_earlier_timed_expense(self):
        value = ledger(money=[source(amount=0)], costs=[expense(due_at="2026-10-10T13:00:00Z")])
        comparison = calculate(value, [{"id": "late", "label": "Late receipt",
                                        "receipts": [receipt(amount=2000, when=START,
                                                             available_at="2026-10-10T22:00:00Z")]}])["scenarios"][0]
        self.assertEqual(comparison["first_gap"]["amount_cents"], 2000)
        self.assertEqual(comparison["ending_projected_position_cents"], 0)

    def test_known_early_receipt_and_equal_timestamp_cover_expense(self):
        for when in ("2026-10-10T12:00:00Z", "2026-10-10T13:00:00Z"):
            with self.subTest(when=when):
                value = ledger(money=[source(amount=0)], costs=[expense(due_at="2026-10-10T13:00:00Z")])
                comparison = calculate(value, [{"id": "early", "label": "Early receipt",
                                                "receipts": [receipt(amount=2000, when=START, available_at=when)]}])["scenarios"][0]
                self.assertIsNone(comparison["first_gap"])

    def test_local_day_used_for_utc_receipt_across_date_boundary(self):
        comparison = calculate(ledger(money=[source(amount=0)]),
                               [{"id": "local", "label": "Local date",
                                 "receipts": [receipt(amount=2000, when=START,
                                                      available_at="2026-10-11T03:00:00Z")]}])["scenarios"][0]
        self.assertEqual(comparison["daily_projections"][0]["receipts_cents"], 2000)

    def test_dst_forecast_has_fourteen_consecutive_calendar_dates(self):
        result = forecast_finances(ledger(money=[source(as_of="2026-10-31T05:00:00Z")], costs=[]),
                                   start_date="2026-10-31", time_zone=ZONE, input_case_version=9)["baseline"]
        self.assertEqual(result["end_date"], "2026-11-13")
        self.assertEqual(result["daily_projections"][2]["date"], "2026-11-02")
        self.assertEqual(len(result["daily_projections"]), 14)

    def test_restricted_scenario_receipt_is_only_used_on_compatible_costs(self):
        comparison = calculate(ledger(money=[source(amount=0)], costs=[expense("rent", 2000, "rent")]),
                               [{"id": "restricted", "label": "Food aid",
                                 "receipts": [receipt(amount=5000, when=START, restrictions=["food"])]}])["scenarios"][0]
        self.assertEqual(comparison["first_gap"]["amount_cents"], 2000)
        self.assertEqual(comparison["ending_projected_position_cents"], 3000)

    def test_outside_horizon_receipt_does_not_change_forecast(self):
        comparison = calculate(ledger(), [{"id": "later", "label": "After horizon",
                                           "receipts": [receipt(when="2026-10-24")]}])["scenarios"][0]
        self.assertEqual(comparison["ending_projected_position_cents"], 28000)
        self.assertIn("receipt_outside_horizon", {item["code"] for item in comparison["warnings"]})
        self.assertEqual(comparison["scenario_assumptions"]["receipts"][0]["date"], "2026-10-24")


class UnknownFinanceTests(unittest.TestCase):
    def assert_incomplete(self, result, code):
        self.assertEqual(result["state"], "incomplete")
        self.assertIsNone(result["ending_projected_position_cents"])
        self.assertIsNone(result["first_gap"])
        self.assertTrue(all(row["projected_position_cents"] is None for row in result["daily_projections"]))
        self.assertIn(code, {item["code"] for item in result["warnings"]})
        self.assertIn("incomplete_forecast", {item["code"] for item in result["warnings"]})
        self.assertTrue(all(expense["unmet_cents"] is None
                            for row in result["daily_projections"] for expense in row["expenses"]))

    def test_unknown_balance_is_null_and_known_money_is_only_subtotal(self):
        result = calculate(ledger(money=[source(amount=None), source("known", 100)]))["baseline"]
        self.assert_incomplete(result, "unknown_balance")
        self.assertIsNone(result["opening_accessible_cents"])
        self.assertEqual(result["opening_known_accessible_cents"], 100)
        self.assertEqual(result["known_inputs_first_gap"]["amount_cents"], 1900)

    def test_unknown_action_cost_is_preserved_with_no_complete_coverage_claim(self):
        result = calculate(ledger(costs=[expense("fee", None, "recovery", action_id="replace_id"),
                                         expense()]))["baseline"]
        self.assert_incomplete(result, "unknown_expense_amount")
        row = result["daily_projections"][0]
        self.assertIsNone(row["expenses_due_cents"])
        self.assertEqual(row["known_expenses_due_cents"], 2000)
        self.assertIsNone(row["expenses"][0]["amount_cents"])
        self.assertIn("replace_id", row["action_ids"])

    def test_unknown_fulfillment_is_preserved(self):
        result = calculate(ledger(costs=[expense(fulfilled_cents=None)]))["baseline"]
        self.assert_incomplete(result, "unknown_expense_amount")
        self.assertIsNone(result["daily_projections"][0]["expenses"][0]["fulfilled_cents"])

    def test_unknown_restrictions_keep_funds_separate(self):
        result = calculate(ledger(money=[source(amount=5000, **{"restrictions": None})]))["baseline"]
        self.assert_incomplete(result, "unknown_restrictions")
        self.assertEqual(result["opening_known_accessible_cents"], 0)
        self.assertEqual(result["daily_projections"][0]["restricted_coverage_cents"], 0)

    def test_unknown_or_partial_household_coverage_cannot_erase_full_cost(self):
        for changes in ({"household_coverage": "unknown"}, {"household_coverage": "partial"},
                        {"daily_limit_cents": None}, {"quantity_limit": 3}):
            with self.subTest(changes=changes):
                result = calculate(ledger(support=[coverage(**changes)]))["baseline"]
                self.assert_incomplete(result, "unknown_support_coverage")
                self.assertEqual(result["daily_projections"][0]["support_coverage_cents"], 0)

    def test_partial_support_with_known_value_limit_is_bounded(self):
        result = calculate(ledger(support=[coverage(household_coverage="partial", daily_limit_cents=500)]))["baseline"]
        self.assertEqual(result["state"], "complete")
        self.assertEqual(result["daily_projections"][0]["support_coverage_cents"], 500)

    def test_unknown_scenario_receipt_amount_only_invalidates_scenario(self):
        result = calculate(ledger(), [{"id": "unknown", "label": "Unknown award",
                                     "receipts": [receipt(amount=None, when=START)]}])
        self.assertEqual(result["baseline"]["state"], "complete")
        self.assert_incomplete(result["scenarios"][0], "unknown_receipt_amount")
        self.assertIsNone(result["scenarios"][0]["daily_projections"][0]["receipts_cents"])

    def test_unknown_receipt_restrictions_do_not_fund_expenses(self):
        comparison = calculate(ledger(money=[source(amount=0)]),
                               [{"id": "unknown", "label": "Unknown terms",
                                 "receipts": [receipt(when=START, restrictions=None)]}])["scenarios"][0]
        self.assert_incomplete(comparison, "unknown_restrictions")
        self.assertEqual(comparison["ending_known_inputs_position_cents"], -2000)

    def test_unknown_accessibility_or_as_of_is_incomplete(self):
        for changes in ({"accessible": None}, {"as_of": None}):
            with self.subTest(changes=changes):
                self.assert_incomplete(calculate(ledger(money=[source(**changes)]))["baseline"], "unknown_balance")

    def test_inaccessible_unknown_money_does_not_poison_known_accessible_forecast(self):
        result = calculate(ledger(money=[source(), source("locked", None, accessible=False)]))["baseline"]
        self.assertEqual(result["state"], "complete")
        self.assertEqual(result["opening_accessible_cents"], 30000)
        self.assertIn("inaccessible_funds", {item["code"] for item in result["warnings"]})

    def test_stale_conflicting_balances_are_incomplete(self):
        for freshness in ("stale", "conflicting", "unknown", None):
            with self.subTest(freshness=freshness):
                self.assert_incomplete(calculate(ledger(money=[source(freshness=freshness)]))["baseline"], "uncertain_balance")

    def test_future_or_intraday_balance_cannot_fund_earlier_expenses(self):
        for when in ("2026-10-11T05:00:00Z", "2026-10-10T22:00:00Z"):
            with self.subTest(when=when):
                result = calculate(ledger(money=[source(as_of=when)]))["baseline"]
                self.assert_incomplete(result, "future_balance")
                self.assertEqual(result["opening_known_accessible_cents"], 0)

    def test_unreconciled_actual_event_cannot_produce_authoritative_forecast(self):
        for kind in ("receipt", "expense", "transfer", "correction"):
            with self.subTest(kind=kind):
                result = calculate(ledger(actual_events=[{"id": "event", "kind": kind, "amount_cents": 5000}]))["baseline"]
                self.assert_incomplete(result, "unreconciled_actual_event")

    def test_received_aid_without_reconciled_balance_is_incomplete_not_new_cash(self):
        result = calculate(ledger(aid=[{"id": "aid", "stage": "received", "amount_cents": 50000}]))["baseline"]
        self.assert_incomplete(result, "unrepresented_received_aid")
        self.assertEqual(result["opening_known_accessible_cents"], 30000)

    def test_availability_and_expiry_constraints_require_normalization(self):
        for changes in ({"available_at": "2026-10-11T05:00:00Z"}, {"expires_at": "2026-10-11T05:00:00Z"}):
            with self.subTest(changes=changes):
                result = calculate(ledger(money=[source(**changes)]))["baseline"]
                self.assert_incomplete(result, "unsupported_fund_timing")
                self.assertEqual(result["opening_known_accessible_cents"], 0)


class DeterminismAndValidationTests(unittest.TestCase):
    def test_input_ledger_and_scenarios_immutable_and_output_has_no_alias_to_them(self):
        value = canonical()
        value["support"] = [coverage()]
        scenarios = [{"id": "aid", "label": "If aid arrives", "receipts": [receipt()]}]
        previous = copy.deepcopy((value, scenarios))
        result = calculate(value, scenarios)
        self.assertEqual((value, scenarios), previous)
        result["scenarios"][0]["scenario_assumptions"]["receipts"][0]["restrictions"].append("rent")
        result["baseline"]["daily_projections"][0]["expenses"][0]["support_ids"].clear()
        self.assertEqual((value, scenarios), previous)

    def test_repeated_calls_and_permuted_records_have_identical_json(self):
        value = canonical()
        value["money_sources"] += [source("bank", 500, ["food", "transport"]), source("voucher", 300, ["food"])]
        value["support"] = [coverage("a", daily_limit_cents=500), coverage("b", daily_limit_cents=800)]
        scenarios = [{"id": "z", "label": "Later", "receipts": [receipt("b"), receipt("a", amount=1000)]},
                     {"id": "a", "label": "Earlier", "receipts": [receipt(when=START)]}]
        expected = json.dumps(calculate(value, scenarios), sort_keys=True)
        rng = random.Random(8)
        for _ in range(12):
            for key in ("money_sources", "expense_commitments", "support"):
                rng.shuffle(value[key])
            rng.shuffle(scenarios)
            for scenario in scenarios:
                rng.shuffle(scenario["receipts"])
            self.assertEqual(json.dumps(calculate(value, scenarios), sort_keys=True), expected)

    def test_entire_output_is_json_serializable_and_carries_version(self):
        result = calculate(canonical(), [{"id": "x", "label": "If support",
                                          "support": [coverage(state="hypothetical")]}])
        self.assertEqual(json.loads(json.dumps(result)), result)
        self.assertEqual(result["contract_version"], "0.1")
        self.assertEqual(result["input_case_version"], 4)
        self.assertTrue(all(item["input_case_version"] == 4 for item in [result["baseline"], *result["scenarios"]]))

    def test_max_three_scenarios_and_unique_nonbaseline_ids(self):
        scenarios = [{"id": str(i), "label": "Scenario"} for i in range(3)]
        self.assertEqual(len(calculate(ledger(), scenarios)["scenarios"]), 3)
        for invalid in (scenarios + [{"id": "four", "label": "Fourth"}],
                        [{"id": "baseline", "label": "Reserved"}], [scenarios[0], scenarios[0]]):
            with self.subTest(invalid=invalid), self.assertRaises(FinanceInputError):
                calculate(ledger(), invalid)

    def test_money_requires_integer_cents_not_float_bool_string_or_negative(self):
        for amount in (2.0, True, "200", -1):
            for field in ("balance", "expense", "receipt"):
                with self.subTest(amount=amount, field=field), self.assertRaises(FinanceInputError):
                    if field == "balance":
                        calculate(ledger(money=[source(amount=amount)]))
                    elif field == "expense":
                        calculate(ledger(costs=[expense(amount=amount)]))
                    else:
                        calculate(ledger(), [{"id": "x", "label": "Receipt", "receipts": [receipt(amount=amount)]}])

    def test_dates_instants_and_zones_require_explicit_valid_formats(self):
        for field, value in (("start_date", "2026-02-30"), ("start_date", "2026-1-01"),
                             ("start_date", "9999-12-31"), ("time_zone", "Not/AZone"),
                             ("input_case_version", True), ("input_case_version", 0)):
            arguments = {"start_date": START, "time_zone": ZONE, "input_case_version": 4, field: value}
            with self.subTest(field=field), self.assertRaises(FinanceInputError):
                forecast_finances(ledger(), **arguments)
        for when in ("2026-10-10", "2026-10-10T05:00:00", "2026-10-10T00:00:00-05:00"):
            with self.subTest(when=when), self.assertRaises(FinanceInputError):
                calculate(ledger(money=[source(as_of=when)]))

    def test_currency_and_credit_sources_rejected(self):
        for changes in ({"currency": "EUR"}, {"type": "credit"}, {"type": "asset"}):
            with self.subTest(changes=changes), self.assertRaises(FinanceInputError):
                calculate(ledger(money=[source(**changes)]))

    def test_required_unknown_fields_must_be_present_as_null(self):
        for collection, key in (("money_sources", "balance_cents"), ("money_sources", "restrictions"),
                                ("expense_commitments", "amount_cents")):
            value = ledger()
            del value[collection][0][key]
            with self.subTest(key=key), self.assertRaises(FinanceInputError) as caught:
                calculate(value)
            self.assertIn(key, caught.exception.field)

    def test_duplicate_ids_are_rejected_instead_of_double_counted(self):
        for key, records in (("money_sources", [source(), source()]),
                             ("expense_commitments", [expense(), expense()]),
                             ("support", [coverage(), coverage()]),
                             ("actual_events", [{"id": "same"}, {"id": "same"}])):
            value = ledger(**{key: records}) if key not in {"money_sources", "expense_commitments"} else ledger()
            value[key] = records
            with self.subTest(key=key), self.assertRaises(FinanceInputError):
                calculate(value)

    def test_aid_references_prevent_repeat_receipts_or_already_received_hypotheses(self):
        for stage in ("approved", "received"):
            value = ledger(aid=[{"id": "aid", "stage": stage}])
            receipts = [receipt("one", aid_id="aid"), receipt("two", aid_id="aid")] if stage == "approved" else [receipt(aid_id="aid")]
            with self.subTest(stage=stage), self.assertRaises(FinanceInputError):
                calculate(value, [{"id": "x", "label": "Duplicate", "receipts": receipts}])

    def test_scenario_cannot_replace_support_or_drop_essential_costs(self):
        for scenario in ({"id": "x", "label": "Replace", "support": [coverage(state="hypothetical")]},
                         {"id": "x", "label": "Drop costs", "expense_commitments": []},
                         {"id": "x", "label": "Path", "alternative_action_ids": ["remote"]}):
            with self.subTest(scenario=scenario), self.assertRaises(FinanceInputError):
                calculate(ledger(support=[coverage()]), [scenario])

    def test_receipt_and_expense_instant_must_match_their_local_date(self):
        with self.assertRaises(FinanceInputError):
            calculate(ledger(costs=[expense(due_at="2026-10-11T13:00:00Z")]))
        with self.assertRaises(FinanceInputError):
            calculate(ledger(), [{"id": "x", "label": "Wrong date", "receipts": [receipt(when=START, available_at="2026-10-10T03:00:00Z")]}])

    def test_oversized_input_is_rejected(self):
        with self.assertRaises(FinanceInputError):
            calculate(ledger(costs=[expense(str(i)) for i in range(257)]))

    def test_malformed_record_states_produce_field_errors(self):
        for value in (ledger(money=[source(type=[])]),
                      ledger(money=[source(freshness=[])]),
                      ledger(support=[coverage(state=[])]),
                      ledger(support=[coverage(household_coverage=[])]),
                      ledger(aid=[{"id": "aid", "stage": []}])):
            with self.subTest(value=value), self.assertRaises(FinanceInputError):
                calculate(value)

    def test_dangling_support_reference_is_rejected(self):
        with self.assertRaises(FinanceInputError):
            calculate(ledger(support=[coverage(commitment_ids=["missing"])]))
        with self.assertRaises(FinanceInputError):
            calculate(ledger(), [{"id": "x", "label": "Missing target",
                                  "support": [coverage(state="hypothetical", commitment_ids=["missing"])]}])

    def test_rejected_input_is_also_immutable(self):
        value = ledger(money=[source(amount=3.5)])
        before = copy.deepcopy(value)
        with self.assertRaises(FinanceInputError):
            calculate(value)
        self.assertEqual(value, before)

    def test_invalid_ranges_and_ambiguous_daily_fulfillment_are_rejected(self):
        for changes in ({"start_date": "2026-10-11", "end_date": START},
                        {"start_date": START, "end_date": START, "fulfilled_cents": 100},
                        {"start_date": START, "end_date": START, "fulfilled_cents_by_date": {"2026-10-11": 100}}):
            item = expense()
            del item["date"]
            item.update(changes)
            with self.subTest(changes=changes), self.assertRaises(FinanceInputError):
                calculate(ledger(costs=[item]))


if __name__ == "__main__":
    unittest.main()
