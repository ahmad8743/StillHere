"""Deterministic synthetic finance update, reconciliation and replay contracts."""

import copy
import json
import unittest

from backend.stillhere.finance import apply_financial_update
from tests.test_finance import ANCHOR, START, ZONE, calculate, expense, ledger, source

NOW = "2026-10-10T12:00:00Z"


def actual(identity="spent", kind="expense", amount=1200, **changes):
    record = {"id": identity, "kind": kind, "amount_cents": amount,
              "currency": "USD", "source": "user_reported", "money_source_id": "cash"}
    if kind == "expense":
        record.update(category="food", commitment_id="food")
    if kind == "receipt":
        record["restrictions"] = []
    return {**record, **changes}


def apply(value, payload, event_id="command1", **changes):
    return apply_financial_update(value, payload, event_id=event_id, effective_at=NOW,
                                  received_at="2026-10-10T12:01:00Z", time_zone=ZONE, **changes)


def post(value=None, record=None, event_id="command1", **fields):
    record = actual() if record is None else record
    return apply(ledger() if value is None else value,
                 {"operation": "record_" + record["kind"], "record": record, **fields}, event_id)


class UpdateTests(unittest.TestCase):
    def accepted(self, result):
        self.assertEqual(result["status"], "applied", result["issues"])
        json.dumps(result, allow_nan=False)
        return result["next_ledger"]

    def unchanged(self, value, payload, status="needs_clarification"):
        before = copy.deepcopy(value)
        result = apply(value, payload)
        self.assertEqual(result["status"], status, result)
        self.assertEqual(value, before)
        self.assertIsNone(result["next_ledger"])
        self.assertEqual(result["changed_record_ids"], [])
        self.assertTrue(result["issues"])
        return result

    def test_spending_reduces_balance_and_only_matched_remaining_cost(self):
        value = ledger()
        before = copy.deepcopy(value)
        result = post(value)
        next_value = self.accepted(result)
        self.assertEqual(value, before)
        self.assertEqual(next_value["money_sources"][0]["balance_cents"], 28800)
        self.assertEqual(next_value["expense_commitments"][0]["fulfilled_cents"], 1200)
        self.assertEqual(next_value["money_sources"][0]["reflected_event_ids"], ["spent"])
        # A later start excludes the spent occurrence. The forecast never replays actuals.
        from backend.stillhere.finance import forecast_finances
        result = forecast_finances(next_value, start_date="2026-10-11", time_zone=ZONE, input_case_version=5)
        self.assertEqual(result["baseline"]["opening_known_accessible_cents"], 28800)
        self.assertEqual(result["baseline"]["ending_projected_position_cents"], 28800)

    def test_audit_preserves_before_after_and_matching_references(self):
        result = post(record=actual(matching_refs=["bank:synthetic-1"]))
        next_value = self.accepted(result)
        audit = next_value["finance_updates"][0]
        self.assertEqual(audit["id"], "command1")
        self.assertEqual(audit["payload"]["record"]["matching_refs"], ["bank:synthetic-1"])
        balance_change = next(item for item in audit["changes"] if item["collection"] == "money_sources")
        self.assertEqual(balance_change["before"]["balance_cents"], 30000)
        self.assertEqual(balance_change["after"]["balance_cents"], 28800)
        self.assertEqual(audit["received_at"], "2026-10-10T12:01:00Z")

    def test_replay_ignores_receipt_time_and_preserves_latest_ledger(self):
        payload = {"operation": "record_expense", "record": actual()}
        next_value = self.accepted(apply(ledger(), payload))
        latest = self.accepted(post(next_value, actual("later", amount=300), "command2"))
        replay = apply_financial_update(latest, payload, event_id="command1", effective_at=NOW,
                                         received_at="2026-10-12T12:00:00Z", time_zone=ZONE)
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["next_ledger"], latest)
        self.assertEqual(replay["changed_record_ids"], [])
        self.assertEqual(len(latest["finance_updates"]), 2)

    def test_replay_with_equivalent_utc_suffix_and_object_key_order(self):
        payload = {"operation": "record_expense", "record": actual()}
        next_value = self.accepted(apply(ledger(), payload))
        result = apply_financial_update(next_value, dict(reversed(list(payload.items()))),
                    event_id="command1", effective_at=NOW.replace("Z", "+00:00"),
                    received_at=NOW, time_zone=ZONE)
        self.assertTrue(result["replayed"])

    def test_changed_logical_payload_reusing_command_identity_rejected(self):
        next_value = self.accepted(post())
        self.unchanged(next_value, {"operation": "record_expense", "record": actual(amount=999)}, "rejected")

    def test_distinct_command_same_actual_identity_clarifies(self):
        next_value = self.accepted(post())
        result = post(next_value, actual(), "different-command")
        self.assertEqual(result["status"], "needs_clarification")

    def test_duplicate_provider_reference_clarifies_without_second_effect(self):
        next_value = self.accepted(post(record=actual(matching_refs=["import:1"])))
        result = post(next_value, actual("new-identity", matching_refs=["import:1"]), "command2")
        self.assertEqual(result["status"], "needs_clarification")
        self.assertEqual(next_value["money_sources"][0]["balance_cents"], 28800)

    def test_ambiguous_commitment_clarifies(self):
        record = actual()
        del record["commitment_id"]
        self.unchanged(ledger(), {"operation": "record_expense", "record": record})

    def test_explicit_additional_expense_does_not_fulfill_planned_food(self):
        value = self.accepted(post(record=actual(commitment_id="additional")))
        self.assertNotIn("fulfilled_cents", value["expense_commitments"][0])
        self.assertEqual(value["money_sources"][0]["balance_cents"], 28800)

    def test_no_candidate_unmatched_expense_is_additional(self):
        record = actual(category="medical")
        del record["commitment_id"]
        self.accepted(post(record=record))

    def test_match_category_and_occurrence_validated(self):
        self.unchanged(ledger(), {"operation": "record_expense", "record": actual(category="rent")}, "rejected")
        self.unchanged(ledger(), {"operation": "record_expense", "record": actual(commitment_date="2026-10-09")}, "rejected")

    def test_daily_occurrence_is_fulfilled_once(self):
        cost = expense()
        del cost["date"]
        cost.update(start_date=START, end_date="2026-10-23")
        result = post(ledger(costs=[cost]))
        value = self.accepted(result)
        self.assertEqual(value["expense_commitments"][0]["fulfilled_cents_by_date"], {START: 1200})
        replay = post(value)
        self.assertEqual(replay["next_ledger"], value)

    def test_late_settlement_matches_explicit_prior_occurrence(self):
        record = actual(effective_at="2026-10-11T12:00:00Z", commitment_date=START)
        value = self.accepted(post(record=record))
        self.assertEqual(value["expense_commitments"][0]["fulfilled_cents"], 1200)
        self.assertEqual(value["actual_events"][0]["date"], "2026-10-11")

    def test_unknown_actual_amount_is_clarification_not_zero(self):
        self.unchanged(ledger(), {"operation": "record_expense", "record": actual(amount=None)})

    def test_zero_actual_amount_is_known_zero(self):
        value = self.accepted(post(record=actual(amount=0)))
        self.assertEqual(value["money_sources"][0]["balance_cents"], 30000)
        self.assertEqual(value["expense_commitments"][0]["fulfilled_cents"], 0)

    def test_invalid_cents_rejected(self):
        for amount in (True, 1.0, "1", -1):
            with self.subTest(amount=amount):
                self.unchanged(ledger(), {"operation": "record_expense", "record": actual(amount=amount)}, "rejected")

    def test_unknown_balance_and_fulfillment_cannot_be_inferred(self):
        self.unchanged(ledger(money=[source(amount=None)]), {"operation": "record_expense", "record": actual()})
        self.unchanged(ledger(costs=[expense(fulfilled_cents=None)]), {"operation": "record_expense", "record": actual()})

    def test_overspending_requires_reconciliation_and_never_negative_actual_money(self):
        self.unchanged(ledger(money=[source(amount=100)]), {"operation": "record_expense", "record": actual()})

    def test_restricted_source_cannot_fund_wrong_category(self):
        self.unchanged(ledger(money=[source(restrictions=["rent"])]), {"operation": "record_expense", "record": actual()}, "rejected")

    def test_unknown_restrictions_clarify(self):
        self.unchanged(ledger(money=[source(restrictions=None)]), {"operation": "record_expense", "record": actual()})

    def test_restricted_source_can_pay_matching_category(self):
        self.accepted(post(ledger(money=[source(restrictions=["food"])])))

    def test_receipt_adds_once_and_has_no_expense_fulfillment(self):
        value = self.accepted(post(record=actual(kind="receipt", amount=5000)))
        self.assertEqual(value["money_sources"][0]["balance_cents"], 35000)
        self.assertNotIn("fulfilled_cents", value["expense_commitments"][0])

    def test_receipt_requires_explicit_restrictions(self):
        record = actual(kind="receipt")
        del record["restrictions"]
        self.unchanged(ledger(), {"operation": "record_receipt", "record": record}, "rejected")

    def test_restricted_receipt_cannot_merge_into_unrestricted_cash(self):
        self.unchanged(ledger(), {"operation": "record_receipt", "record": actual(kind="receipt", restrictions=["food"])}, "rejected")

    def test_transfer_updates_both_sources_once_and_conserves_money(self):
        value = ledger(money=[source(), source("account", 1000)])
        record = actual(kind="transfer", amount=4000, to_money_source_id="account")
        result = post(value, record)
        next_value = self.accepted(result)
        self.assertEqual({item["id"]: item["balance_cents"] for item in next_value["money_sources"]}, {"account": 5000, "cash": 26000})
        self.assertEqual(sum(item["balance_cents"] for item in next_value["money_sources"]), 31000)
        self.assertTrue(all("spent" in item["reflected_event_ids"] for item in next_value["money_sources"]))
        self.assertEqual(post(next_value, record)["next_ledger"], next_value)

    def test_transfer_must_preserve_restrictions(self):
        value = ledger(money=[source(restrictions=["food"]), source("account", 0)])
        self.unchanged(value, {"operation": "record_transfer", "record": actual(kind="transfer", to_money_source_id="account")}, "rejected")

    def test_transfer_failure_is_atomic_for_both_sides(self):
        value = ledger(money=[source(), source("account", None)])
        self.unchanged(value, {"operation": "record_transfer", "record": actual(kind="transfer", to_money_source_id="account")})

    def test_pending_import_is_not_actual_money_then_explicit_posting_matches_it(self):
        record = actual(state="proposed", matching_refs=["bank:pending"])
        value = self.accepted(post(record=record))
        self.assertEqual(value["money_sources"][0]["balance_cents"], 30000)
        self.assertEqual(calculate(value)["baseline"]["state"], "complete")
        replacement = actual(matching_refs=["bank:pending", "bank:posted"])
        next_value = self.accepted(apply(value, {"operation": "reconcile_event", "record_id": "spent",
                     "replacement": replacement, "reason": "Import posted"}, "command2"))
        self.assertEqual(len(next_value["actual_events"]), 1)
        self.assertEqual(next_value["money_sources"][0]["balance_cents"], 28800)
        self.assertEqual(next_value["actual_events"][0]["matching_refs"], ["bank:pending", "bank:posted"])

    def test_unknown_pending_amount_stays_proposed(self):
        value = self.accepted(post(record=actual(amount=None, state="proposed")))
        self.assertIsNone(value["actual_events"][0]["amount_cents"])
        self.assertEqual(value["money_sources"][0]["balance_cents"], 30000)

    def test_newer_snapshot_requires_explicit_reflection_acknowledgment(self):
        value = ledger(money=[source(amount=28800, as_of="2026-10-10T14:00:00Z")])
        self.unchanged(value, {"operation": "record_expense", "record": actual()})
        next_value = self.accepted(post(value, balance_reflected_source_ids=["cash"]))
        self.assertEqual(next_value["money_sources"][0]["balance_cents"], 28800)
        self.assertEqual(next_value["expense_commitments"][0]["fulfilled_cents"], 1200)

    def test_reflected_transfer_can_acknowledge_one_snapshot_and_apply_other_side(self):
        value = ledger(money=[source(amount=26000, as_of="2026-10-10T14:00:00Z"), source("account", 1000)])
        record = actual(kind="transfer", amount=4000, to_money_source_id="account")
        next_value = self.accepted(post(value, record, balance_reflected_source_ids=["cash"]))
        self.assertEqual(sum(item["balance_cents"] for item in next_value["money_sources"]), 31000)

    def test_reflected_fulfillment_is_linked_without_double_counting(self):
        value = ledger(money=[source(amount=28800, as_of="2026-10-10T14:00:00Z")],
                       costs=[expense(fulfilled_cents=1200)])
        next_value = self.accepted(post(value, balance_reflected_source_ids=["cash"], commitment_fulfillment_reflected=True))
        self.assertEqual(next_value["expense_commitments"][0]["fulfilled_cents"], 1200)

    def test_reflected_claim_after_snapshot_is_not_accepted(self):
        self.unchanged(ledger(), {"operation": "record_expense", "record": actual(), "balance_reflected_source_ids": ["cash"]})

    def test_balance_refresh_preserves_acknowledged_references_and_does_not_replay(self):
        value = self.accepted(post())
        next_value = self.accepted(apply(value, {"operation": "set_balance", "money_source_id": "cash",
             "balance_cents": 28000, "as_of": "2026-10-10T15:00:00Z", "reflected_event_ids": ["spent"]}, "refresh"))
        self.assertEqual(next_value["money_sources"][0]["balance_cents"], 28000)
        self.assertEqual(post(next_value)["next_ledger"], next_value)

    def test_balance_refresh_omitting_matched_events_clarifies(self):
        value = self.accepted(post())
        payload = {"operation": "set_balance", "money_source_id": "cash", "balance_cents": 30000,
                   "as_of": "2026-10-10T15:00:00Z", "reflected_event_ids": []}
        result = apply(value, payload, "refresh")
        self.assertEqual(result["status"], "needs_clarification")

    def test_unknown_balance_refresh_remains_unknown(self):
        value = self.accepted(apply(ledger(), {"operation": "set_balance", "money_source_id": "cash",
                   "balance_cents": None, "as_of": None, "reflected_event_ids": []}))
        self.assertIsNone(value["money_sources"][0]["balance_cents"])
        self.assertEqual(calculate(value)["baseline"]["state"], "incomplete")

    def test_stale_balance_requires_reconciliation(self):
        self.unchanged(ledger(money=[source(freshness="stale")]), {"operation": "record_expense", "record": actual()})

    def test_commitment_correction_has_reason_and_keeps_history(self):
        result = apply(ledger(), {"operation": "correct_record", "collection": "expense_commitments",
                     "record": expense(amount=None), "reason": "Amount is not confirmed"})
        value = self.accepted(result)
        self.assertIsNone(value["expense_commitments"][0]["amount_cents"])
        self.assertEqual(value["finance_updates"][0]["changes"][0]["before"]["amount_cents"], 2000)

    def test_posted_actual_amount_correction_reverses_old_effect_and_match(self):
        value = self.accepted(post())
        next_value = self.accepted(apply(value, {"operation": "correct_actual", "record_id": "spent",
                "replacement": actual(amount=1000), "reason": "Receipt total corrected"}, "correct1"))
        self.assertEqual(next_value["money_sources"][0]["balance_cents"], 29000)
        self.assertEqual(next_value["expense_commitments"][0]["fulfilled_cents"], 1000)
        self.assertEqual(len(next_value["actual_events"]), 1)
        revision = next(item for item in next_value["finance_updates"][1]["changes"] if item["collection"] == "actual_events")
        self.assertEqual(revision["before"]["amount_cents"], 1200)

    def test_correction_after_later_arithmetic_keeps_newest_anchor_and_other_spending(self):
        value = self.accepted(post())
        value = self.accepted(post(value, actual("later", amount=500, effective_at="2026-10-10T14:00:00Z"), "later"))
        value = self.accepted(apply(value, {"operation": "correct_actual", "record_id": "spent",
                "replacement": actual(amount=1000), "reason": "Corrected total"}, "correct"))
        self.assertEqual(value["money_sources"][0]["balance_cents"], 28500)
        self.assertEqual(value["money_sources"][0]["as_of"], "2026-10-10T14:00:00Z")
        self.assertEqual(value["expense_commitments"][0]["fulfilled_cents"], 1500)

    def test_correction_after_snapshot_requires_explicit_reconciled_values(self):
        value = self.accepted(post())
        value = self.accepted(apply(value, {"operation": "set_balance", "money_source_id": "cash",
                "balance_cents": 28000, "as_of": "2026-10-10T15:00:00Z", "reflected_event_ids": ["spent"]}, "refresh"))
        result = apply(value, {"operation": "correct_actual", "record_id": "spent",
                "replacement": actual(amount=1000), "reason": "Corrected total"}, "correct")
        self.assertEqual(result["status"], "needs_clarification")
        result = apply(value, {"operation": "reconcile_correction", "record_id": "spent",
                "replacement": actual(amount=1000), "reason": "Reconciled balance and receipt",
                "source_snapshots": [{"money_source_id": "cash", "balance_cents": 28200,
                    "as_of": "2026-10-10T16:00:00Z", "reflected_event_ids": ["spent"]}],
                "commitment_fulfillment": [{"commitment_id": "food", "date": START, "fulfilled_cents": 1000}]}, "reconcile")
        value = self.accepted(result)
        self.assertEqual(value["money_sources"][0]["balance_cents"], 28200)
        self.assertEqual(value["expense_commitments"][0]["fulfilled_cents"], 1000)

    def test_direct_commitment_edit_cannot_erase_matched_fulfillment(self):
        value = self.accepted(post())
        result = apply(value, {"operation": "set_commitment", "record": expense()}, "erase")
        self.assertEqual(result["status"], "needs_clarification")

    def test_aid_stays_outside_money_until_explicit_receipt(self):
        value = self.accepted(apply(ledger(), {"operation": "set_aid", "record": {"id": "grant", "stage": "approved",
                   "amount_cents": 50000, "expected_date": "2026-10-17", "restrictions": ["food"]}}))
        self.assertEqual(calculate(value)["baseline"]["opening_accessible_cents"], 30000)
        dedicated = source("grant-money", 0, ["food"], type="received_assistance", aid_id="grant")
        value = self.accepted(apply(value, {"operation": "set_money_source", "record": dedicated}, "source"))
        record = actual(kind="receipt", amount=50000, money_source_id="grant-money", aid_id="grant", restrictions=["food"])
        value = self.accepted(post(value, record, "received"))
        self.assertEqual(value["aid"][0]["stage"], "received")
        self.assertEqual(value["aid"][0]["actual_receipt_id"], "spent")
        self.assertEqual(next(item for item in value["money_sources"] if item["id"] == "grant-money")["balance_cents"], 50000)

    def test_receipt_cannot_duplicate_aid_under_new_actual_id(self):
        value = ledger(money=[source("cash", 0, type="received_assistance", aid_id="grant")],
                       aid=[{"id": "grant", "stage": "approved", "restrictions": []}])
        value = self.accepted(post(value, actual(kind="receipt", aid_id="grant")))
        result = post(value, actual("duplicate", kind="receipt", aid_id="grant"), "command2")
        self.assertEqual(result["status"], "needs_clarification")

    def test_aid_received_stage_requires_actual_receipt(self):
        self.unchanged(ledger(), {"operation": "set_aid", "record": {"id": "grant", "stage": "received"}}, "rejected")

    def test_support_update_unknown_limit_preserved(self):
        from tests.test_finance import coverage
        value = self.accepted(apply(ledger(), {"operation": "set_support", "record": coverage(daily_limit_cents=None)}))
        self.assertIsNone(value["support"][0]["daily_limit_cents"])
        self.assertEqual(calculate(value)["baseline"]["state"], "incomplete")

    def test_legacy_actual_reconciles_explicit_balance_and_fulfillment(self):
        record = actual(effective_at=NOW, date=START, state="posted")
        value = ledger(money=[source(amount=28800, as_of="2026-10-10T14:00:00Z")],
                       costs=[expense(fulfilled_cents=1200)], actual_events=[record])
        result = apply(value, {"operation": "reconcile_event", "record_id": "spent",
                 "replacement": record, "reason": "Confirm imported snapshot",
                 "balance_reflected_source_ids": ["cash"], "commitment_fulfillment_reflected": True})
        value = self.accepted(result)
        self.assertEqual(value["money_sources"][0]["balance_cents"], 28800)
        self.assertEqual(value["expense_commitments"][0]["fulfilled_cents"], 1200)

    def test_unsupported_or_malformed_operation_rejected_without_mutation(self):
        for payload in ({}, {"operation": "guess_balance"}, {"operation": "set_money_source", "record": {}},
                        {"operation": "record_expense", "record": actual(), "extra": 1}):
            with self.subTest(payload=payload):
                self.unchanged(ledger(), payload, "rejected")

    def test_output_aliases_cannot_change_input_or_other_audit_records(self):
        value = ledger()
        next_value = self.accepted(post(value))
        next_value["money_sources"][0]["balance_cents"] = 99
        next_value["finance_updates"][0]["changes"][0]["after"]["amount_cents"] = 99
        self.assertEqual(value["money_sources"][0]["balance_cents"], 30000)
        self.assertEqual(next_value["actual_events"][0]["amount_cents"], 1200)

    def test_record_capacity_does_not_drop_history(self):
        value = ledger(aid=[{"id": "aid" + str(index), "stage": "unknown"} for index in range(256)])
        self.unchanged(value, {"operation": "set_aid", "record": {"id": "overflow", "stage": "unknown"}}, "rejected")

    def test_new_proposal_does_not_alias_previous_audit_history(self):
        value = self.accepted(post())
        before = copy.deepcopy(value)
        next_value = self.accepted(post(value, actual("second", amount=100), "second"))
        next_value["finance_updates"][0]["payload"]["record"]["amount_cents"] = 99
        self.assertEqual(value, before)

    def test_actual_correction_preserves_import_identity(self):
        value = self.accepted(post(record=actual(matching_refs=["bank:posted"])))
        result = apply(value, {"operation": "correct_actual", "record_id": "spent",
                "replacement": actual(amount=1000), "reason": "Corrected total"}, "correct")
        self.assertEqual(result["status"], "rejected")

    def test_reconcile_correction_transfer_requires_two_snapshots(self):
        value = self.accepted(post(ledger(money=[source(), source("account", 0)]),
                actual(kind="transfer", to_money_source_id="account")))
        result = apply(value, {"operation": "reconcile_correction", "record_id": "spent",
            "replacement": actual(kind="transfer", amount=1000, to_money_source_id="account"),
            "reason": "Corrected transfer", "source_snapshots": [
                {"money_source_id": "cash", "balance_cents": 29000, "as_of": "2026-10-10T14:00:00Z", "reflected_event_ids": ["spent"]},
                {"money_source_id": "account", "balance_cents": 1000, "as_of": "2026-10-10T14:00:00Z", "reflected_event_ids": ["spent"]}]}, "correct")
        value = self.accepted(result)
        self.assertEqual(sum(item["balance_cents"] for item in value["money_sources"]), 30000)

    def test_reconcile_correction_cannot_erase_other_actual_fulfillment(self):
        value = self.accepted(post())
        value = self.accepted(post(value, actual("second", amount=500), "second"))
        before = copy.deepcopy(value)
        result = apply(value, {"operation": "reconcile_correction", "record_id": "spent",
            "replacement": actual(amount=1000), "reason": "Corrected total",
            "source_snapshots": [{"money_source_id": "cash", "balance_cents": 28500,
                "as_of": "2026-10-10T14:00:00Z", "reflected_event_ids": ["spent", "second"]}],
            "commitment_fulfillment": [{"commitment_id": "food", "date": START, "fulfilled_cents": 1000}]}, "correct")
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(value, before)

    def test_restriction_correction_is_explicit_and_auditable(self):
        value = self.accepted(apply(ledger(), {"operation": "correct_record", "collection": "money_sources",
            "record": source(restrictions=None), "reason": "Restrictions are not confirmed"}))
        self.assertIsNone(value["money_sources"][0]["restrictions"])
        self.assertEqual(calculate(value)["baseline"]["state"], "incomplete")

    def test_malformed_enum_and_snapshot_identifiers_do_not_escape_result_boundary(self):
        for field in ("kind", "state"):
            record = actual(**{field: []})
            result = apply(ledger(), {"operation": "record_expense", "record": record})
            self.assertEqual(result["status"], "rejected")
        self.unchanged(ledger(), {"operation": []}, "rejected")
        self.unchanged(ledger(), {"operation": "correct_record", "collection": [], "record": expense(), "reason": "Correction"}, "rejected")

    def test_reflected_fulfillment_cannot_reuse_total_already_matched_elsewhere(self):
        value = self.accepted(post())
        before = copy.deepcopy(value)
        result = post(value, actual("second", amount=1200), "second", commitment_fulfillment_reflected=True)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(value, before)

    def test_same_expense_can_move_to_another_explicit_match_with_correction(self):
        value = ledger(costs=[expense(), expense("other-food", 1500)])
        value = self.accepted(post(value))
        value = self.accepted(apply(value, {"operation": "correct_actual", "record_id": "spent",
            "replacement": actual(commitment_id="other-food"), "reason": "Corrected commitment match"}, "match-correction"))
        totals = {item["id"]: item.get("fulfilled_cents", 0) for item in value["expense_commitments"]}
        self.assertEqual(totals, {"food": 0, "other-food": 1200})
        self.assertEqual(value["money_sources"][0]["balance_cents"], 28800)

    def test_aid_receipt_correction_preserves_actual_money_and_audits_prior_stage(self):
        value = ledger(money=[source("cash", 0, type="received_assistance", aid_id="grant")],
                       aid=[{"id": "grant", "stage": "pending", "restrictions": []}])
        value = self.accepted(post(value, actual(kind="receipt", amount=5000, aid_id="grant")))
        self.assertEqual(value["actual_events"][0]["aid_before_receipt"]["stage"], "pending")
        value = self.accepted(apply(value, {"operation": "correct_actual", "record_id": "spent",
            "replacement": actual(kind="receipt", amount=4000, aid_id="grant"), "reason": "Receipt amount corrected"}, "correct"))
        self.assertEqual(value["money_sources"][0]["balance_cents"], 4000)
        self.assertEqual(value["aid"][0]["stage"], "received")

    def test_local_date_consistency_is_enforced(self):
        self.unchanged(ledger(), {"operation": "record_expense", "record": actual(date="2026-10-09")}, "rejected")

    def test_correction_replay_does_not_repeat_delta(self):
        value = self.accepted(post())
        payload = {"operation": "correct_actual", "record_id": "spent",
                   "replacement": actual(amount=1000), "reason": "Receipt corrected"}
        value = self.accepted(apply(value, payload, "correct"))
        replay = apply(value, payload, "correct")
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["next_ledger"], value)

    def test_unreceived_aid_source_cannot_be_spent(self):
        value = ledger(money=[source(type="received_assistance", aid_id="grant")],
                       aid=[{"id": "grant", "stage": "approved", "restrictions": []}])
        self.unchanged(value, {"operation": "record_expense", "record": actual()})

    def test_inaccessible_and_unknown_accessibility_require_clarification_for_new_spend(self):
        for accessible in (False, None):
            with self.subTest(accessible=accessible):
                self.unchanged(ledger(money=[source(accessible=accessible)]), {"operation": "record_expense", "record": actual()})

    def test_actual_spend_cannot_ignore_expiry_or_later_availability(self):
        for changes in ({"expires_at": "2026-10-10T11:00:00Z"}, {"available_at": "2026-10-10T13:00:00Z"}):
            with self.subTest(changes=changes):
                self.unchanged(ledger(money=[source(**changes)]), {"operation": "record_expense", "record": actual()})

    def test_dedicated_aid_source_cannot_bypass_receipt_match(self):
        value = ledger(money=[source(type="received_assistance", aid_id="grant")],
                       aid=[{"id": "grant", "stage": "approved", "restrictions": []}])
        self.unchanged(value, {"operation": "record_receipt", "record": actual(kind="receipt")}, "rejected")


if __name__ == "__main__":
    unittest.main()
