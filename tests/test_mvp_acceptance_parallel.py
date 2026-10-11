"""Independent MVP acceptance gates. A passing subset never establishes readiness.

Run the explicit groups using tests.acceptance_support.run. No expectedFailure,
private environment loading, live network/provider, or application-file edits.
All household state is established through CaseService, never fixture SQL.
SQL below only injects storage faults or inspects the disposable audit database.
"""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from backend.stillhere.agent import AgentConfig, AgentRuntime
from backend.stillhere.agent.registry import ToolRegistry, CASE_TOOLS
from backend.stillhere.agent.tools import AgentContext, AgentFailure
from backend.stillhere.contracts import validate
from backend.stillhere.server import CaseHTTPServer
from backend.stillhere.service import CaseService, ServiceError
from tests.acceptance_support.harness import (Journey, NOW, DAY, ZONE, PROGRAM, day,
                                              envelope, money, expense, support, scenario)
from tests.acceptance_support.http import MemoryHTTP, LoopbackHTTP


class AcceptanceCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="stillhere-acceptance-")
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "synthetic.sqlite3"
        self.now = NOW
        self.service = CaseService(self.path, clock=lambda: self.now)
        self.family = Journey(self.service)
        # Fail loudly if these tests accidentally acquire private configuration.
        guard = patch("backend.stillhere.agent.config.load_local_environment", side_effect=AssertionError("Acceptance must not load private configuration"))
        guard.start()
        self.addCleanup(guard.stop)

    def rows(self, table):
        allowed = {"events", "simulated_effects", "check_in_states", "agent_runs"}
        if table not in allowed:
            raise ValueError("Only disposable acceptance tables may be inspected")
        with self.service._connection() as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM " + table)]

    def fresh(self):
        return self.family.snapshot()

    def assert_issue(self, result, status, code):
        self.assertEqual(result["status"], status, result["issues"])
        self.assertIn(code, {item["code"] for item in result["issues"]})

    def operator_command(self, token, kind, payload, event_id):
        return self.service.execute_operator(token, envelope(self.fresh(), kind, payload, event_id, channel="operator", occurred_at=self.now))


class FamilyJourneyTests(AcceptanceCase):
    def test_complete_synthetic_family_journey_uses_persisted_records(self):
        family = self.family
        family.correct("adult_count", 1)
        family.correct("children_count", 2)
        family.correct("housing_status", "home_lost")
        family.correct("document_issuing_state", "CO")
        family.seed_finance()
        lease = family.claim()
        from backend.stillhere.resources import ResourceCatalog, build_query
        snapshot = self.fresh()
        referrals = ResourceCatalog(clock=lambda: NOW).collect(build_query(snapshot, {"location_scope": "current"}), snapshot["case_version"], lease["deadline"])
        family.accept(self.service.commit_agent_resources(family.token, family.case_id, lease["parent"], lease["run_id"], referrals, snapshot["case_version"]))
        snapshot = family.revise(lease)
        self.assertEqual(snapshot["plan"]["household_eligibility"], "unknown")
        self.assertTrue(snapshot["plan"]["actions"])
        self.assertTrue(snapshot["resources"]["items"])
        self.assertTrue(all(item["source_ids"] for item in snapshot["resources"]["items"]))
        family.prepare(lease)
        family.accept(family.derive(lease, "finance.calculate", {"start_date": DAY}))
        snapshot = self.fresh()
        resource = snapshot["resources"]["items"][0]["id"]
        descriptors = [{"id": "urgent", "kind": "urgent_resource", "record_ids": [resource], "display_order": 0},
                       {"id": "tasks", "kind": "task_list", "record_ids": [], "display_order": 1},
                       {"id": "money", "kind": "finance_overview", "record_ids": ["family_cash"], "display_order": 2}]
        family.accept(family.derive(lease, "dashboard.publish", {"components": descriptors}))
        saved = self.service.finish_agent_turn(family.token, family.case_id, lease["parent"], lease["run_id"], "Synthetic plan saved; availability and eligibility remain unknown.")
        self.assertEqual(saved["facts"]["children_count"]["value"], 2)
        self.assertEqual(saved["finance"]["baseline"]["first_gap"]["amount_cents"], 5500)
        self.assertEqual(saved["components"], descriptors)
        self.assertEqual(CaseService(self.path, clock=lambda: NOW).read_case(family.token, family.case_id), saved)

    def test_all_four_canonical_finance_scenarios_through_commands(self):
        self.family.seed_finance()
        baseline = self.fresh()["finance"]["baseline"]
        self.assertEqual((baseline["first_gap"]["day"], baseline["first_gap"]["amount_cents"], baseline["ending_projected_position_cents"]), (5, 5500, -64000))
        self.family.finance("set_support", support())
        baseline = self.fresh()["finance"]["baseline"]
        self.assertEqual((baseline["first_gap"]["day"], baseline["first_gap"]["amount_cents"], baseline["ending_projected_position_cents"]), (11, 2500, -22000))
        self.family.send("scenario.set", {"scenario": scenario("day8", 8), "start_date": DAY})
        self.family.send("scenario.set", {"scenario": scenario("day12", 12), "start_date": DAY})
        results = {item["scenario_id"]: item for item in self.fresh()["finance"]["scenarios"]}
        self.assertIsNone(results["day8"]["first_gap"])
        self.assertEqual(results["day8"]["ending_projected_position_cents"], 28000)
        self.assertEqual((results["day12"]["first_gap"]["day"], results["day12"]["first_gap"]["amount_cents"], results["day12"]["ending_projected_position_cents"]), (11, 2500, 28000))
        self.assertEqual(self.fresh()["finance"]["ledger"]["money_sources"][0]["balance_cents"], 30000)
        self.assertEqual(self.fresh()["finance"]["ledger"]["actual_events"], [])

    def test_no_car_replanning_preserves_completed_work_and_unrelated_program(self):
        self.family.correct("document_issuing_state", "CO")
        lease = self.family.claim()
        first = self.family.revise(lease)
        online = next(action for action in first["plan"]["actions"] if action["execution_mode"] == "online")
        self.family.send("task.update", {"action_id": online["id"], "status": "completed"}, "completed")
        self.family.revise(lease, "co_state_id_proof_options")
        self.family.correct("mobility", "no_car")
        self.family.correct("office_transport_available", False)
        revised = self.family.revise(lease)
        actions = {action["id"]: action for action in revised["plan"]["actions"]}
        self.assertEqual(actions[online["id"]]["status"], "completed")
        self.assertEqual(actions[online["id"]]["history"][-1]["event_id"], "completed")
        office = next(action for action in actions.values() if action["path_id"] == "co_id_office_renewal")
        self.assertEqual(office["status"], "blocked")
        self.assertIn(online["id"], office["alternative_ids"])
        self.assertIsNone(office["costs"]["transport_cents"])
        self.assertTrue(all(action["input_freshness"] == "stale" for action in actions.values() if action["program_id"] != PROGRAM))

    def test_application_stage_and_correspondence_do_not_create_money_or_agency_outcome(self):
        self.family.seed_finance()
        lease = self.family.claim()
        args = self.family.prepare(lease)
        before = deepcopy(self.fresh()["finance"]["ledger"])
        _, snapshot = self.family.send("application.update", {"application_id": args["application_id"],
                       "stage_change": {"stage": "approved", "corrects_event_id": None},
                       "correspondence": {"id": "decision", "kind": "decision_notice", "evidence_ids": []}}, "approval")
        app = snapshot["applications"][0]
        self.assertEqual(app["stage_report"]["stage"], "approved")
        self.assertIsNone(app["agency_outcome"])
        self.assertEqual(snapshot["finance"]["ledger"], before)
        self.assertEqual(app["history"][-1]["event_id"], "approval")
        self.assertTrue(app["official_url"].startswith("https://"))
        self.assertEqual(snapshot["evidence"], [])

    def test_skipped_intake_and_distinct_locations_do_not_share_location(self):
        partial = Journey(self.service, intake=False)
        partial.send("intake.submit", {"crisis_type": "unsure", "needs": ["unsure"]})
        self.assertIsNone(partial.snapshot()["facts"]["crisis_type"]["value"])
        self.family.correct("damaged_location", {"state": "LA", "place": "Synthetic damaged home"})
        self.family.correct("document_issuing_state", "CO")
        from backend.stillhere.resources import build_query
        query = build_query(self.fresh(), {"location_scope": "current"})
        self.assertIn("CO", json.dumps(query))
        self.assertNotIn("Synthetic damaged home", json.dumps(query))
        self.assertIsNone(self.fresh()["shared_location"])


class TransactionTests(AcceptanceCase):
    def test_lost_response_replay_after_restart_applies_spending_once(self):
        self.family.seed_finance()
        request, saved = self.family.send("finance.update", {"operation": "record_expense", "record": expense()}, "lost_response")
        restarted = CaseService(self.path, clock=lambda: "2026-10-11T05:02:00Z")
        replay = restarted.execute(self.family.token, request)
        self.assertEqual(replay["status"], "already_applied")
        self.assertEqual(replay["case_snapshot"], saved)
        self.assertEqual(saved["finance"]["ledger"]["money_sources"][0]["balance_cents"], 28800)
        self.assertEqual(len(saved["finance"]["ledger"]["actual_events"]), 1)
        self.assertEqual(saved["finance"]["baseline"]["ending_projected_position_cents"], -64000)
        self.assertEqual(sum(row["event_id"] == "lost_response" for row in self.rows("events")), 1)

    def test_changed_payload_event_reuse_and_cross_household_replay_are_rejected(self):
        self.family.seed_finance()
        request, before = self.family.send("finance.update", {"operation": "record_expense", "record": expense()}, "stable")
        altered = deepcopy(request)
        altered["payload"]["record"]["amount_cents"] = 1300
        self.assert_issue(self.service.execute(self.family.token, altered), "rejected", "event_id_reused")
        stranger = Journey(self.service)
        result = self.service.execute(stranger.token, request)
        self.assert_issue(result, "rejected", "case_unavailable")
        self.assertIsNone(result["case_snapshot"])
        self.assertEqual(self.fresh(), before)

    def test_two_sqlite_writers_race_one_wins_one_visible_conflict(self):
        requests = [self.family.request("fact.correct", {"fact_key": "mobility", "value": value, "observed_at": NOW}, "race_"+str(i))
                    for i, value in enumerate(("no_car", "has_car"))]
        barrier = threading.Barrier(2)
        def execute(request):
            independent = CaseService(self.path, clock=lambda: NOW)
            barrier.wait(timeout=5)
            return independent.execute(self.family.token, request)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(execute, requests))
        self.assertCountEqual([item["status"] for item in results], ["applied", "conflict"])
        loser = requests[next(i for i, result in enumerate(results) if result["status"] == "conflict")]
        changed = deepcopy(loser)
        changed["payload"]["value"] = "changed_after_conflict"
        changed["expected_case_version"] = self.fresh()["case_version"]
        self.assert_issue(self.service.execute(self.family.token, changed), "rejected", "event_id_reused")
        loser["expected_case_version"] = self.fresh()["case_version"]
        self.assertEqual(self.service.execute(self.family.token, loser)["status"], "applied")
        self.assertEqual(self.fresh()["case_version"], 3)

    def test_finance_failure_after_tentative_write_rolls_back_event_ledger_forecast_audit(self):
        self.family.seed_finance()
        before, events = self.fresh(), self.rows("events")
        with self.service._connection() as connection:
            connection.execute("CREATE TRIGGER reject_acceptance BEFORE UPDATE OF applied_version ON events WHEN NEW.event_id='rollback_money' BEGIN SELECT RAISE(ABORT,'synthetic'); END")
        request = self.family.request("finance.update", {"operation": "record_expense", "record": expense()}, "rollback_money")
        self.assert_issue(self.service.execute(self.family.token, request), "unavailable", "storage_unavailable")
        self.assertEqual(self.fresh(), before)
        self.assertEqual(self.rows("events"), events)

    def test_worker_failure_rolls_back_private_state_effects_snapshot_and_audit(self):
        self.family.enroll()
        before = self.fresh()
        tables = {name: self.rows(name) for name in ("events", "check_in_states", "simulated_effects")}
        with self.service._connection() as connection:
            connection.execute("CREATE TRIGGER reject_worker BEFORE INSERT ON events WHEN NEW.event_id LIKE 'worker_%' BEGIN SELECT RAISE(ABORT,'synthetic'); END")
        self.now = "2026-10-11T05:11:00Z"
        with self.assertRaises(sqlite3.DatabaseError):
            self.service.process_due_check_ins()
        self.assertEqual(self.fresh(), before)
        for name, records in tables.items():
            self.assertEqual(self.rows(name), records)

    def test_stale_derived_result_after_user_write_cannot_overwrite_new_inputs(self):
        lease = self.family.claim()
        version = self.fresh()["case_version"]
        self.family.correct("mobility", "no_car")
        before = self.fresh()
        result = self.family.derive(lease, "dashboard.publish", {"components": []}, expected_version=version)
        self.assert_issue(result, "conflict", "version_conflict")
        self.assertEqual(self.fresh(), before)

    def test_expired_lease_and_deadline_cannot_publish(self):
        lease = self.family.claim(seconds=1)
        before = self.fresh()
        expired_deadline = {**lease, "deadline": 0}
        self.assert_issue(self.family.derive(expired_deadline, "dashboard.publish", {"components": []}), "rejected", "agent_timeout")
        self.now = "2026-10-11T05:01:00Z"
        self.assert_issue(self.family.derive(lease, "dashboard.publish", {"components": []}), "rejected", "agent_run_inactive")
        self.assertEqual(self.fresh(), before)

    def test_compact_result_limit_prevents_derived_publication(self):
        lease = self.family.claim()
        before, events = self.fresh(), self.rows("events")
        self.assert_issue(self.family.derive(lease, "dashboard.publish", {"components": []}, max_result_chars=10), "rejected", "agent_context_limit")
        self.assertEqual(self.fresh(), before)
        self.assertEqual(self.rows("events"), events)

    def test_provider_failure_after_write_retains_effect_and_replay_does_not_invoke_provider(self):
        class FailingProvider:
            calls = 0
            def reply(inner, snapshot, history, text, context, registry):
                inner.calls += 1
                registry.invoke("correct_fact", {"fact_key": "mobility", "value": "no_car", "observed_at": NOW}, context)
                raise RuntimeError("synthetic private exception text")
        provider = FailingProvider()
        runtime = AgentRuntime(self.service, AgentConfig(), provider)
        request = self.family.request("conversation.message", {"message_id": "failure_message", "text": "Synthetic request"}, "failure_chat", channel="chat")
        result = runtime.handle(self.family.token, request)
        self.assertEqual(result["case_snapshot"]["facts"]["mobility"]["value"], "no_car")
        turn = result["case_snapshot"]["conversation"]["turns"][-1]
        self.assertEqual((turn["state"], turn["issue"]["code"]), ("failed", "agent_provider_unavailable"))
        self.assertNotIn("synthetic private exception text", json.dumps(result))
        self.assertEqual(runtime.handle(self.family.token, request)["case_snapshot"], result["case_snapshot"])
        self.assertEqual(provider.calls, 1)

    def test_interrupted_agent_expiration_preserves_writes_and_revokes_old_run(self):
        old = self.family.claim(seconds=1)
        snapshot = self.fresh()
        self.family.accept(self.service.execute_agent_command(self.family.token, self.family.case_id, old["parent"], old["run_id"], "fact.correct", {"fact_key": "mobility", "value": "no_car", "observed_at": NOW}, snapshot["case_version"]))
        self.now = "2026-10-11T05:01:00Z"
        restarted = CaseService(self.path, clock=lambda: self.now)
        request = envelope(self.fresh(), "conversation.message", {"message_id": "next_message", "text": "Continue"}, "next_chat", channel="chat", occurred_at=self.now)
        self.family.accept(restarted.execute(self.family.token, request))
        claim = restarted.claim_agent_turn(self.family.token, self.family.case_id, "next_chat", 60)
        self.assertIsNotNone(claim)
        snapshot = self.fresh()
        self.assertEqual(snapshot["facts"]["mobility"]["value"], "no_car")
        turn = next(item for item in snapshot["conversation"]["turns"] if item.get("event_id") == old["parent"])
        self.assertEqual(turn["issue"]["code"], "agent_interrupted")
        result = self.family.derive(old, "dashboard.publish", {"components": []})
        self.assert_issue(result, "rejected", "agent_run_inactive")


class FinanceIntegrityTests(AcceptanceCase):
    def test_unreceived_approved_denied_delayed_aid_is_not_accessible_cash(self):
        self.family.seed_finance()
        for stage in ("approved", "denied", "pending"):
            self.family.finance("set_aid", {"id": "aid", "stage": stage, "amount_cents": 50000, "date": day(12), "restrictions": []})
            self.assertEqual(self.fresh()["finance"]["baseline"]["opening_accessible_cents"], 30000)
            self.assertEqual(self.fresh()["finance"]["ledger"]["money_sources"][0]["balance_cents"], 30000)

    def test_ambiguous_match_requires_clarification_without_ledger_or_forecast_write(self):
        self.family.seed_finance()
        before = self.fresh()
        record = expense()
        del record["commitment_id"]
        del record["commitment_date"]
        result = self.service.execute(self.family.token, self.family.request("finance.update", {"operation": "record_expense", "record": record}, "ambiguous"))
        self.assertEqual(result["status"], "needs_clarification", result["issues"])
        self.assertEqual(self.fresh(), before)

    def test_unknown_is_incomplete_and_boolean_money_is_rejected(self):
        self.family.finance("set_money_source", money(amount=None))
        self.assertEqual(self.fresh()["finance"]["baseline"]["state"], "incomplete")
        self.assertIsNone(self.fresh()["finance"]["baseline"]["opening_accessible_cents"])
        before = self.fresh()
        result = self.service.execute(self.family.token, self.family.request("finance.update", {"operation": "set_money_source", "record": money("boolean", True)}))
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(self.fresh(), before)

    def test_transfer_changes_location_of_money_without_income_or_double_forecast_effect(self):
        self.family.seed_finance()
        self.family.finance("set_money_source", money("account", 0, type="account"))
        self.family.finance("record_transfer", {"id": "move", "kind": "transfer", "amount_cents": 10000,
             "currency": "USD", "source": "user_reported", "money_source_id": "family_cash", "to_money_source_id": "account"})
        sources = self.fresh()["finance"]["ledger"]["money_sources"]
        self.assertEqual(sum(item["balance_cents"] for item in sources), 30000)
        self.assertEqual(self.fresh()["finance"]["baseline"]["ending_projected_position_cents"], -64000)

    def test_restricted_funds_and_overlapping_support_do_not_cover_incompatible_costs_twice(self):
        self.family.finance("set_money_source", money(amount=0))
        self.family.finance("set_money_source", money("food_voucher", 10000, restrictions=["food"]))
        self.family.finance("set_commitment", {"id": "rent", "category": "lodging", "amount_cents": 4000, "date": DAY, "essential": True})
        self.family.finance("set_commitment", {"id": "food", "category": "food", "amount_cents": 2000, "date": DAY, "essential": True})
        for identity in ("one", "two"):
            self.family.finance("set_support", support(id=identity, categories=["food"]))
        baseline = self.fresh()["finance"]["baseline"]
        self.assertEqual(baseline["first_gap"]["amount_cents"], 4000)
        self.assertEqual(baseline["daily_projections"][0]["support_coverage_cents"], 2000)

    def test_finance_gap_marks_plan_pending_and_preserves_completion(self):
        self.family.correct("document_issuing_state", "CO")
        lease = self.family.claim()
        snapshot = self.family.revise(lease)
        action = snapshot["plan"]["actions"][0]
        self.family.send("task.update", {"action_id": action["id"], "status": "completed"})
        self.family.seed_finance()
        snapshot = self.fresh()
        self.assertEqual(snapshot["plan"]["state"], "pending")
        self.assertTrue(snapshot["finance"]["reassessment"]["required"])
        self.assertEqual(next(item for item in snapshot["plan"]["actions"] if item["id"] == action["id"])["status"], "completed")


class CheckInOperatorTests(AcceptanceCase):
    def test_check_later_reschedules_once_and_model_cannot_enroll_or_share(self):
        self.family.enroll()
        occurrence = self.fresh()["check_in"]["current_occurrence_id"]
        self.now = "2026-10-11T05:01:00Z"
        request, saved = self.family.send("check_in.reply", {"occurrence_id": occurrence, "reply": "check_later", "next_due_at": "2026-10-11T05:20:00Z"}, "check_later", occurred_at=self.now)
        self.assertNotEqual(saved["check_in"]["current_occurrence_id"], occurrence)
        self.assertEqual(saved["check_in"]["schedule"]["due_at"], "2026-10-11T05:20:00Z")
        self.assertEqual(self.service.execute(self.family.token, request)["case_snapshot"], saved)
        lease = self.family.claim()
        for kind, payload in (("check_in.enroll", {"consent": True}), ("location.share", {"consent": True}), ("follow_up.acknowledge", {})):
            result = self.service.execute_agent_command(self.family.token, self.family.case_id, lease["parent"], lease["run_id"], kind, payload, self.fresh()["case_version"])
            self.assert_issue(result, "rejected", "tool_forbidden")
        before = self.fresh()
        request = envelope(before, "check_in.pause", {"intent": "pause"}, "system_spoof", channel="system", occurred_at=self.now)
        self.assert_issue(self.service.execute(self.family.token, request), "rejected", "channel_forbidden")
        self.assertEqual(self.fresh(), before)

    def test_reminder_overdue_acknowledgment_late_reply_attempt_and_outcome(self):
        self.family.enroll()
        operator = self.service.provision_operator([self.family.case_id], operator_id="synthetic_operator")
        self.now = "2026-10-11T05:05:00Z"
        self.assertEqual(self.service.process_due_check_ins()["processed_cases"], 1)
        self.assertEqual(self.fresh()["check_in"]["status"], "reminder_attempted")
        self.assertEqual(self.fresh()["follow_ups"], [])
        self.now = "2026-10-11T05:10:00Z"
        self.service.process_due_check_ins()
        snapshot = self.fresh()
        self.assertEqual(snapshot["check_in"]["status"], "overdue")
        self.assertEqual(len(snapshot["follow_ups"]), 1)
        self.assertEqual(len(snapshot["check_in"]["attempts"]), 1)
        request_id = snapshot["follow_ups"][0]["id"]
        result = self.operator_command(operator["session_token"], "follow_up.acknowledge", {"request_id": request_id}, "ack")
        self.assertEqual(result["status"], "applied", result["issues"])
        self.assertNotIn("case_snapshot", result)
        self.now = "2026-10-11T05:11:00Z"
        self.family.send("check_in.reply", {"occurrence_id": snapshot["check_in"]["current_occurrence_id"], "reply": "okay_for_now"}, "late", occurred_at="2026-10-11T05:06:00Z")
        snapshot = self.fresh()
        self.assertTrue(snapshot["check_in"]["last_report"]["late"])
        self.assertEqual(snapshot["check_in"]["last_report"]["reported_at"], "2026-10-11T05:06:00Z")
        self.assertEqual(snapshot["check_in"]["last_report"]["received_at"], self.now)
        self.assertEqual(snapshot["follow_ups"][0]["status"], "assigned_acknowledged")
        self.assertEqual(snapshot["follow_ups"][0]["report_updates"][-1]["notify_operator_id"], operator["operator_id"])
        common = {"request_id": request_id, "simulation": True, "unresolved_need_ids": [], "next_action": "Synthetic review"}
        self.assertEqual(self.operator_command(operator["session_token"], "follow_up.record", {**common, "kind": "attempt", "channel": "phone_simulator", "result": "reported_contact"}, "attempt")["status"], "applied")
        self.assertEqual(self.operator_command(operator["session_token"], "follow_up.record", {**common, "kind": "outcome", "outcome": "review_complete"}, "outcome")["status"], "applied")
        self.assertEqual(self.fresh()["follow_ups"][0]["status"], "outcome_recorded")
        self.assertEqual(self.service.process_due_check_ins()["processed_cases"], 0)
        self.assertTrue(all(json.loads(row["effect_json"])["simulation"] is True for row in self.rows("simulated_effects")))

    def test_pause_prevents_future_attempts_and_location_clear_removes_projection(self):
        self.family.enroll()
        self.family.help()
        operator = self.service.provision_operator([self.family.case_id])
        self.family.send("location.share", {"consent": True, "source": "user_entered", "place": "Synthetic shelter", "observed_at": NOW,
                 "purpose": "simulated_follow_up", "recipients": "case_handlers"})
        self.assertIsNotNone(self.service.read_operator_queue(operator["session_token"])["cases"][0]["reviews"][0]["shared_location"])
        self.family.send("location.clear", {})
        self.family.send("check_in.pause", {"intent": "pause"})
        self.now = "2026-10-12T05:00:00Z"
        self.assertEqual(self.service.process_due_check_ins()["processed_cases"], 0)
        self.assertIsNone(self.service.read_operator_queue(operator["session_token"])["cases"][0]["reviews"][0]["shared_location"])
        self.assertEqual(len(self.fresh()["follow_ups"]), 1)
        self.assertEqual(self.fresh()["check_in"]["attempts"], [])

    def test_location_expiry_and_assigned_handler_policy_never_claim_current_destination(self):
        self.family.help()
        first = self.service.provision_operator([self.family.case_id], operator_id="first")
        second = self.service.provision_operator([self.family.case_id], operator_id="second")
        self.family.send("location.share", {"consent": True, "source": "user_entered", "place": "Synthetic last-shared place", "observed_at": NOW,
                 "expires_at": "2026-10-11T05:10:00Z", "purpose": "simulated_follow_up", "recipients": "assigned_handler"})
        def location(operator):
            return self.service.read_operator_queue(operator["session_token"])["cases"][0]["reviews"][0]["shared_location"]
        self.assertIsNone(location(first))
        request_id = self.fresh()["follow_ups"][0]["id"]
        self.assertEqual(self.operator_command(first["session_token"], "follow_up.acknowledge", {"request_id": request_id}, "ack")["status"], "applied")
        self.assertFalse(location(first)["verified_current_destination"])
        self.assertIsNone(location(second))
        self.now = "2026-10-11T05:10:00Z"
        self.assertIsNone(location(first))

    def test_scoped_read_only_operator_minimal_projection_revocation_and_household_isolation(self):
        self.family.help()
        other = Journey(self.service)
        other.help()
        operator = self.service.provision_operator([self.family.case_id], permissions={"follow_up.read"})
        queue = self.service.read_operator_queue(operator["session_token"])
        self.assertEqual(len(queue["cases"]), 1)
        view = queue["cases"][0]
        for field in ("facts", "finance", "conversation", "evidence", "case_snapshot", "session_token"):
            self.assertNotIn(field, view)
        self.assertEqual(view["reviews"][0]["relevant_needs"], [])
        request_id = self.fresh()["follow_ups"][0]["id"]
        self.assertEqual(self.operator_command(operator["session_token"], "follow_up.acknowledge", {"request_id": request_id}, "denied")["status"], "rejected")
        for case_id in (other.case_id, "missing"):
            with self.assertRaises(ServiceError) as error:
                self.service.read_operator_queue(operator["session_token"], case_id)
            self.assertEqual(error.exception.issue["code"], "case_unavailable")
        with self.assertRaises(ServiceError):
            self.service.read_case(operator["session_token"], self.family.case_id)
        self.service.revoke_operator(operator["operator_id"])
        with self.assertRaises(ServiceError):
            self.service.read_operator_queue(operator["session_token"])

    def test_operator_replay_requires_same_actor_and_another_operator_cannot_steal_assignment(self):
        self.family.help()
        first = self.service.provision_operator([self.family.case_id], operator_id="first")
        second = self.service.provision_operator([self.family.case_id], operator_id="second")
        request = envelope(self.fresh(), "follow_up.acknowledge", {"request_id": self.fresh()["follow_ups"][0]["id"]}, "ack", channel="operator")
        result = self.service.execute_operator(first["session_token"], request)
        self.assertEqual(result["status"], "applied")
        before = self.fresh()
        self.assertEqual(self.service.execute_operator(first["session_token"], request)["status"], "already_applied")
        self.assert_issue(self.service.execute_operator(second["session_token"], request), "rejected", "event_id_reused")
        request.update(event_id="steal", expected_case_version=before["case_version"])
        self.assertEqual(self.service.execute_operator(second["session_token"], request)["status"], "rejected")
        self.assertEqual(self.fresh(), before)

    def test_missed_activity_without_enrollment_does_not_create_follow_up_and_help_is_immediate(self):
        self.now = "2026-10-13T05:00:00Z"
        self.assertEqual(self.service.process_due_check_ins()["processed_cases"], 0)
        self.assertEqual(self.fresh()["follow_ups"], [])
        self.family.help()
        snapshot = self.fresh()
        self.assertFalse(snapshot["check_in"]["enrolled"])
        self.assertEqual(snapshot["follow_ups"][0]["status"], "requested")
        self.assertTrue(any("911" in notice["message"] and "211" in notice["message"] for notice in snapshot["notices"]))

    def test_two_independent_worker_processes_do_not_duplicate_effects(self):
        self.family.enroll(grace=0)
        command = [sys.executable, "-m", "backend.stillhere.worker", "--db", str(self.path), "--once"]
        environment = {"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"}
        def run(_):
            return subprocess.run(command, env=environment, capture_output=True, text=True, timeout=20)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(run, range(2)))
        self.assertTrue(all(result.returncode == 0 for result in results), [result.stderr for result in results])
        self.assertEqual(sum(json.loads(result.stdout)["processed_cases"] for result in results), 1)
        self.assertEqual(len(self.fresh()["follow_ups"]), 1)
        self.assertEqual(len(self.fresh()["check_in"]["attempts"]), 1)
        self.assertEqual(len({row["effect_id"] for row in self.rows("simulated_effects")}), len(self.rows("simulated_effects")))

    def test_independent_worker_sigkill_then_restart_has_one_durable_effect_set(self):
        self.family.enroll(grace=0)
        environment = {"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"}
        process = subprocess.Popen([sys.executable, "-m", "backend.stillhere.worker", "--db", str(self.path), "--interval", "0.1"], env=environment,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        def reap():
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)
        self.addCleanup(reap)
        limit = time.monotonic()+10
        while self.fresh()["check_in"]["status"] != "overdue" and time.monotonic() < limit:
            time.sleep(0.02)
        self.assertEqual(self.fresh()["check_in"]["status"], "overdue")
        process.kill()
        process.wait(timeout=10)
        effects, snapshot = self.rows("simulated_effects"), self.fresh()
        restarted = subprocess.run([sys.executable, "-m", "backend.stillhere.worker", "--db", str(self.path), "--once"], env=environment, capture_output=True, text=True, timeout=20)
        self.assertEqual(restarted.returncode, 0, restarted.stderr)
        self.assertEqual(json.loads(restarted.stdout)["processed_cases"], 0)
        self.assertEqual(self.rows("simulated_effects"), effects)
        self.assertEqual(self.fresh(), snapshot)

    def test_worker_sigkill_during_real_transaction_rolls_back_and_restart_catches_up_once(self):
        self.family.enroll(grace=0)
        before = self.fresh()
        tables = {name: self.rows(name) for name in ("events", "check_in_states", "simulated_effects")}
        marker = self.path.with_name("transaction_open.marker")
        environment = {"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"}
        process = subprocess.Popen([sys.executable, "-m", "tests.acceptance_support.worker_probe", "--db", str(self.path), "--marker", str(marker)],
                    env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        def reap():
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)
        self.addCleanup(reap)
        limit = time.monotonic()+10
        while not marker.exists() and time.monotonic() < limit and process.poll() is None:
            time.sleep(0.02)
        self.assertTrue(marker.exists(), "Fault probe did not reach the CaseService worker transaction")
        # WAL readers must still see only the previously committed snapshot.
        self.assertEqual(self.fresh(), before)
        process.kill()
        process.wait(timeout=10)
        self.assertEqual(self.fresh(), before)
        for name, rows in tables.items():
            self.assertEqual(self.rows(name), rows)
        for expected in (1, 0):
            restarted = subprocess.run([sys.executable, "-m", "backend.stillhere.worker", "--db", str(self.path), "--once"],
                          env=environment, capture_output=True, text=True, timeout=20)
            self.assertEqual(restarted.returncode, 0, restarted.stderr)
            self.assertEqual(json.loads(restarted.stdout)["processed_cases"], expected)
        self.assertEqual(len(self.fresh()["follow_ups"]), 1)
        self.assertEqual(len(self.fresh()["check_in"]["attempts"]), 1)


class OutputAndBudgetTests(AcceptanceCase):
    def test_dashboard_reference_allowlist_replay_and_rejection_preserve_previous_components(self):
        lease = self.family.claim()
        valid = {"components": [{"id": "tasks", "kind": "task_list", "record_ids": [], "display_order": 0}]}
        first = self.family.derive(lease, "dashboard.publish", valid)
        self.family.accept(first)
        before = self.fresh()
        self.assertEqual(self.family.derive(lease, "dashboard.publish", valid)["status"], "already_applied")
        for arguments in ({"components": [{"id": "wrong", "kind": "urgent_resource", "record_ids": ["family_cash"], "display_order": 0}]},
                          {"components": [{"id": "code", "kind": "html", "record_ids": [], "display_order": 0}]},
                          {"components": [], "role": "operator"}):
            self.assertEqual(self.family.derive(lease, "dashboard.publish", arguments)["status"], "rejected")
            self.assertEqual(self.fresh(), before)

    def test_tool_budget_is_terminal_and_late_calls_do_not_write(self):
        lease = self.family.claim()
        context = AgentContext(self.service, self.family.token, self.family.case_id, lease["parent"], lease["run_id"], self.fresh()["case_version"], lease["deadline"], 1, 48000)
        registry = ToolRegistry(CASE_TOOLS)
        registry.invoke("read_case", {}, context)
        before = self.fresh()
        with self.assertRaises(AgentFailure) as error:
            registry.invoke("correct_fact", {"fact_key": "mobility", "value": "no_car", "observed_at": NOW}, context)
        self.assertEqual(error.exception.issue["code"], "agent_tool_limit")
        self.assertEqual(self.fresh(), before)

    def test_per_case_agent_claim_is_exclusive_across_service_instances(self):
        request = self.family.request("conversation.message", {"message_id": "queued", "text": "Synthetic"}, "queued")
        self.family.accept(self.service.execute(self.family.token, request))
        barrier = threading.Barrier(2)
        def claim(_):
            service = CaseService(self.path, clock=lambda: NOW)
            barrier.wait(timeout=5)
            return service.claim_agent_turn(self.family.token, self.family.case_id, "queued", 60)
        with ThreadPoolExecutor(max_workers=2) as executor:
            claims = list(executor.map(claim, range(2)))
        self.assertEqual(sum(item is not None for item in claims), 1)


class SourceAcceptanceTests(AcceptanceCase):
    def collect(self, lease, *, failure=False):
        from backend.stillhere.incidents import IncidentFacade, build_query
        from backend.stillhere.incidents.transport import SourceFailure
        class SyntheticTransport:
            def get_json(inner, url, deadline):
                if failure:
                    raise SourceFailure("source_timeout_or_network")
                return ({"DisasterDeclarationsSummaries": []} if "fema.gov" in url
                        else {"type": "FeatureCollection", "features": []})
        snapshot = self.fresh()
        query = build_query(snapshot, {"location_scope": "current"}, NOW)
        result = IncidentFacade(SyntheticTransport(), clock=lambda: NOW).collect(query, snapshot["case_version"], lease["deadline"])
        committed = self.service.commit_agent_incident_context(self.family.token, self.family.case_id,
                            lease["parent"], lease["run_id"], result, snapshot["case_version"])
        self.family.accept(committed)
        return result

    def test_no_matching_declaration_keeps_nonfederal_referrals_and_unknown_eligibility(self):
        self.family.correct("current_location", {"state": "CO", "county_fips": "08031", "latitude": 39.7392, "longitude": -104.9903})
        lease = self.family.claim()
        result = self.collect(lease)
        self.assertEqual(result["providers"]["openfema"]["state"], "no_match")
        from backend.stillhere.resources import ResourceCatalog, build_query
        snapshot = self.fresh()
        referrals = ResourceCatalog(clock=lambda: NOW).collect(build_query(snapshot, {"location_scope": "current"}), snapshot["case_version"], lease["deadline"])
        self.family.accept(self.service.commit_agent_resources(self.family.token, self.family.case_id, lease["parent"], lease["run_id"], referrals, snapshot["case_version"]))
        self.assertTrue(self.fresh()["resources"]["items"])
        self.assertNotIn("eligibility", self.fresh()["facts"])

    def test_source_failure_is_unavailable_with_official_fallback_not_no_match(self):
        self.family.correct("current_location", {"state": "CO", "county_fips": "08031", "latitude": 39.7392, "longitude": -104.9903})
        lease = self.family.claim()
        result = self.collect(lease, failure=True)
        self.assertEqual(result["state"], "unavailable")
        self.assertTrue(all(provider["state"] == "unavailable" and provider["source"]["referral_url"].startswith("https://")
                            for provider in result["providers"].values()))
        self.assertEqual(self.fresh()["incident_context"]["current"]["state"], "unavailable")

    def test_resource_failure_retains_previous_referrals_and_fact_changes_mark_them_stale(self):
        from backend.stillhere.resources import ResourceCatalog, build_query
        lease = self.family.claim()
        snapshot = self.fresh()
        query = build_query(snapshot, {"location_scope": "current"})
        result = ResourceCatalog(clock=lambda: NOW).collect(query, snapshot["case_version"], lease["deadline"])
        self.family.accept(self.service.commit_agent_resources(self.family.token, self.family.case_id, lease["parent"], lease["run_id"], result, snapshot["case_version"]))
        self.family.correct("current_location", {"state": "LA", "place": "Synthetic new location"})
        before = self.fresh()
        self.assertEqual(before["resources"]["search"]["freshness"], "stale")
        def fail():
            raise OSError("synthetic catalog failure")
        failed = ResourceCatalog(loader=fail, clock=lambda: NOW).collect(build_query(before, {"location_scope": "current"}), before["case_version"], lease["deadline"])
        result = self.service.commit_agent_resources(self.family.token, self.family.case_id, lease["parent"], lease["run_id"], failed, before["case_version"])
        self.assert_issue(result, "unavailable", "resource_catalog_unavailable")
        self.assertEqual(self.fresh(), before)


class ProposalBoundaryTests(AcceptanceCase):
    """Detached proposals based on real saved cases; explicitly NOT durable wiring."""

    def costed(self, amount):
        from backend.stillhere.planner import set_action_costs
        self.family.seed_finance()
        self.family.correct("document_issuing_state", "CO")
        lease = self.family.claim()
        snapshot = self.family.revise(lease)
        action = next(item for item in snapshot["plan"]["actions"] if item["execution_mode"] == "online")
        updates = [{"action_id": action["id"], "rule_id": action["rule_id"], "rule_version": action["rule_version"],
            "items": [{"id": "synthetic_quote", "category": "documents", "amount_cents": amount,
                       "date": day(2), "due_at": None, "state": "user_reported", "observed_at": NOW, "source_ids": [], "essential": False}]}]
        return snapshot, set_action_costs(snapshot["plan"], updates, as_of=NOW), action["id"]

    def test_dated_null_action_cost_proposal_keeps_baseline_and_essentials_and_makes_scenario_incomplete(self):
        from backend.stillhere.boundaries import reconcile_action_costs
        from backend.stillhere.finance import compare_financial_scenarios
        snapshot, plan, action_id = self.costed(None)
        before = deepcopy(snapshot)
        result = reconcile_action_costs(plan, snapshot["finance"]["ledger"], [action_id],
                    input_case_version=snapshot["case_version"], as_of=NOW, time_zone=ZONE, start_date=DAY)
        self.assertEqual(result["state"], "proposed", result["issues"])
        self.assertIsNone(result["action_alternatives"][0]["costs"][0]["amount_cents"])
        calculation = compare_financial_scenarios(snapshot["finance"]["ledger"], start_date=DAY, time_zone=ZONE,
                       input_case_version=snapshot["case_version"], action_alternatives=result["action_alternatives"],
                       scenarios=[{"id": "unknown_path", "label": "Synthetic unknown fee", "alternative_ids": [action_id]}])
        self.assertEqual(calculation["baseline"]["state"], "complete")
        self.assertEqual(calculation["scenarios"][0]["state"], "incomplete")
        self.assertEqual(snapshot, before)
        self.assertEqual(self.fresh(), before)

    def test_unknown_cost_date_suppresses_entire_executable_proposal(self):
        from backend.stillhere.boundaries import reconcile_action_costs
        snapshot, plan, action_id = self.costed(1000)
        next(action for action in plan["actions"] if action["id"] == action_id)["cost_items"][0]["date"] = None
        result = reconcile_action_costs(plan, snapshot["finance"]["ledger"], [action_id],
                    input_case_version=snapshot["case_version"], as_of=NOW, time_zone=ZONE, start_date=DAY)
        self.assertEqual(result["state"], "needs_clarification")
        self.assertEqual(result["action_alternatives"], [])
        self.assertEqual(result["remove_commitment_ids"], [])
        self.assertIsNone(result["comparison_ledger"])
        self.assertEqual(self.fresh(), snapshot)

    def test_application_report_only_proposal_and_invalidation_preserve_stage_money_and_case(self):
        from backend.stillhere.boundaries import report_application_only, invalidate_applications
        lease = self.family.claim()
        args = self.family.prepare(lease)
        before = self.fresh()
        result = report_application_only(before, {"application_id": args["application_id"],
                         "stage_change": {"stage": "approved", "corrects_event_id": None}},
                         event_id="pure_approval", occurred_at=NOW, received_at=NOW)
        self.assertEqual(result["application"]["stage_report"]["stage"], "approved")
        self.assertEqual(result["application"]["preparation_state"], "pending")
        self.assertIsNone(result["application"]["agency_outcome"])
        invalidated = invalidate_applications(before, target_case_version=before["case_version"]+1, changed_fact_keys=["document_issuing_state"])
        self.assertEqual(invalidated["applications"][0]["preparation_state"], "pending")
        self.assertEqual(self.fresh(), before)


class RequiredIntegrationGates(AcceptanceCase):
    """Required behaviors remain ordinary failures until assembled; never skip them."""

    def test_household_finance_cannot_mint_backend_planner_ownership(self):
        self.family.seed_finance()
        before = self.fresh()
        payload = {"operation": "set_commitment", "record": {
            "id": "forged_owned_cost", "category": "documents", "amount_cents": 1000,
            "essential": False, "date": DAY, "origin": "recovery_planner",
            "planner_cost_id": "invented_cost", "planner_commitment_id": "invented_binding",
            "rule_id": "invented_rule", "rule_version": "invented_version",
            "fulfilled_cents": 0, "actual_event_ids": []}}
        result = self.service.execute(self.family.token,
                    envelope(before, "finance.update", payload, "forged_cost_ownership"))
        self.assertEqual(result["status"], "rejected",
                         "MVP blocker: household input can mint metadata consumed as backend planner ownership")
        self.assertEqual(self.fresh(), before)

    def test_expired_agent_run_is_visible_on_resume_after_process_restart(self):
        lease = self.family.claim(seconds=1)
        self.now = "2026-10-11T05:01:00Z"
        restarted = CaseService(self.path, clock=lambda: self.now)
        snapshot = restarted.read_case(self.family.token, self.family.case_id)
        turn = next(item for item in snapshot["conversation"]["turns"] if item.get("event_id") == lease["parent"])
        self.assertEqual(turn["state"], "failed", "MVP blocker: an expired interrupted run still appears running on resume until a new claim is attempted")
        self.assertEqual(turn["issue"]["code"], "agent_interrupted")

    def test_same_fact_report_does_not_leave_replay_plan_permanently_stale(self):
        self.family.correct("document_issuing_state", "CO")
        lease = self.family.claim()
        self.family.revise(lease)
        self.family.correct("document_issuing_state", "CO")
        revised = self.family.revise(lease)
        self.assertTrue(all(action["input_freshness"] == "current" for action in revised["plan"]["actions"]),
                        "MVP blocker: identical fact report invalidated actions, then plan replay suppressed reassessment")

    def test_explicit_finance_recalculation_accepts_current_inputs(self):
        self.family.seed_finance()
        lease = self.family.claim()
        result = self.family.derive(lease, "finance.calculate", {"start_date": DAY})
        self.assertEqual(result["status"], "applied", result["issues"])
        self.assertEqual(result["case_snapshot"]["finance"]["baseline"]["first_gap"]["amount_cents"], 5500)

    def test_new_finance_adapter_chat_control_parity_requires_real_case_service(self):
        from backend.stillhere.agent_extensions import ExtensionConfig, create_registry
        self.family.seed_finance()
        lease = self.family.claim()
        config = ExtensionConfig(finance_updates=True)
        registry = create_registry(ToolRegistry(CASE_TOOLS), config)
        context = AgentContext(self.service, self.family.token, self.family.case_id, lease["parent"], lease["run_id"], self.fresh()["case_version"], lease["deadline"], 10, 48000)
        result = registry.invoke("update_financial_state", {"update": {"operation": "record_expense", "record": expense()}}, context)
        self.assertEqual(result.get("status"), "applied", result)
        self.assertEqual(self.fresh()["finance"]["ledger"]["money_sources"][0]["balance_cents"], 28800)

    def test_forged_choice_without_persisted_question_is_rejected(self):
        before = self.fresh()
        request = self.family.request("conversation.message", {"message_id": "forged_answer", "text": "Yes", "choice_id": "nonexistent_choice"}, "forged")
        result = self.service.execute(self.family.token, request)
        self.assertEqual(result["status"], "rejected", "MVP blocker: arbitrary choice_id was accepted without a persisted complete assistant question")
        self.assertEqual(self.fresh(), before)

    def test_fact_correction_invalidates_application_preparation_preserving_stage(self):
        lease = self.family.claim()
        args = self.family.prepare(lease)
        self.family.send("application.update", {"application_id": args["application_id"], "stage_change": {"stage": "submitted", "corrects_event_id": None}}, "submitted")
        prior = self.fresh()["applications"][0]
        self.family.correct("document_issuing_state", "LA")
        app = self.fresh()["applications"][0]
        self.assertEqual(app["stage_report"], prior["stage_report"])
        self.assertIn(app["preparation_state"], ("pending", "stale"), "MVP blocker: corrected issuing jurisdiction retained apparently usable application preparation")

    def test_reported_application_status_saves_while_rules_are_unavailable(self):
        lease = self.family.claim()
        args = self.family.prepare(lease)
        request = self.family.request("application.update", {"application_id": args["application_id"], "stage_change": {"stage": "submitted", "corrects_event_id": None}}, "offline_stage")
        with patch.object(self.service, "_application_rules", side_effect=ServiceError(503, "application_rules_unavailable", "Synthetic rule failure", True)):
            result = self.service.execute(self.family.token, request)
        self.assertEqual(result["status"], "applied", "MVP blocker: rule outage prevented durable household status report")
        self.assertEqual(result["case_snapshot"]["applications"][0]["stage_report"]["stage"], "submitted")
        self.assertIn(result["case_snapshot"]["applications"][0]["preparation_state"], ("pending", "stale"))

    def test_completion_correction_is_auditable_durable_and_replay_safe(self):
        self.family.correct("document_issuing_state", "CO")
        lease = self.family.claim()
        action = self.family.revise(lease)["plan"]["actions"][0]
        self.family.send("task.update", {"action_id": action["id"], "status": "completed"}, "completed")
        request = self.family.request("task.update", {"action_id": action["id"], "completion_event_id": "completed", "reason_code": "reported_in_error"}, "correct_completion")
        result = self.service.execute(self.family.token, request)
        self.assertEqual(result["status"], "applied", "MVP blocker: proposed completion correction is not assembled")
        corrected = next(item for item in result["case_snapshot"]["plan"]["actions"] if item["id"] == action["id"])
        self.assertNotEqual(corrected["status"], "completed")
        self.assertEqual(corrected["history"][-1]["correction_of"], "completed")
        self.assertEqual(self.service.execute(self.family.token, request)["status"], "already_applied")

    def test_structured_reply_persists_two_skippable_questions(self):
        class Provider:
            def reply(inner, *args):
                return {"text": "Which step is possible?", "questions": [
                    {"id": "transport", "prompt": "Do you have transport?", "kind": "single_choice", "allow_skip": True,
                     "choices": [{"id": "yes", "label": "Yes"}, {"id": "unsure", "label": "Unsure"}]},
                    {"id": "next_step", "prompt": "What would help next?", "kind": "text", "allow_skip": True, "choices": []}]}
        runtime = AgentRuntime(self.service, AgentConfig(), Provider())
        request = self.family.request("conversation.message", {"message_id": "question_message", "text": "Help"}, "question_chat")
        result = runtime.handle(self.family.token, request)
        turn = result["case_snapshot"]["conversation"]["turns"][-1]
        self.assertEqual(turn["state"], "complete", "MVP blocker: structured reply was not validated and persisted")
        self.assertEqual(turn["questions"][0]["id"], "transport")
        self.assertEqual(len(turn["questions"]), 2)
        self.assertTrue(all(question["allow_skip"] for question in turn["questions"]))

    def test_dashboard_metadata_recomputes_source_expiry_on_authorized_read(self):
        from datetime import datetime, timedelta
        self.family.correct("document_issuing_state", "CO")
        lease = self.family.claim()
        snapshot = self.family.revise(lease)
        source = snapshot["sources"][0]
        args = {"components": [{"id": "source_card", "kind": "source_details", "record_ids": [source["id"]], "display_order": 0}]}
        self.family.accept(self.family.derive(lease, "dashboard.publish", args))
        self.now = (datetime.fromisoformat(source["expires_at"].replace("Z", "+00:00")) + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
        view = self.fresh()["dashboard_output"]["component_states"][0]
        self.assertEqual(view["freshness"], "stale", "MVP blocker: persisted component metadata froze source freshness after expiry")

    def test_structured_answer_replay_forged_multichoice_stale_and_skip_behavior(self):
        class Provider:
            calls = 0
            def reply(inner, *args):
                inner.calls += 1
                return {"text": "Choose your priorities.", "questions": [{"id": "priority_"+str(inner.calls),
                    "prompt": "What would help?", "kind": "multiple_choice", "allow_skip": True,
                    "choices": [{"id": "food_"+str(inner.calls), "label": "Food"}, {"id": "shelter_"+str(inner.calls), "label": "Shelter"}]}]}
        provider = Provider()
        runtime = AgentRuntime(self.service, AgentConfig(), provider)
        initial = self.family.request("conversation.message", {"message_id": "question_seed", "text": "Help"}, "question_seed")
        saved = runtime.handle(self.family.token, initial)["case_snapshot"]
        turn = saved["conversation"]["turns"][-1]
        self.assertEqual(turn["state"], "complete", "Structured answer acceptance requires durable structured replies")
        question = turn["questions"][0]
        answer = {"message_id": "selected", "text": "Food and shelter", "reply_to_turn_id": turn["id"],
                  "question_id": question["id"], "choice_ids": [choice["id"] for choice in question["choices"]]}
        forged = {**answer, "choice_ids": ["forged"]}
        self.assertEqual(self.service.execute(self.family.token, envelope(saved, "conversation.message", forged, "forged_multiple"))["status"], "rejected")
        request = envelope(saved, "conversation.message", answer, "answer_multiple")
        result = runtime.handle(self.family.token, request)
        self.assertEqual(result["status"], "applied")
        self.assertEqual(runtime.handle(self.family.token, request)["status"], "already_applied")
        self.assertEqual(provider.calls, 2)
        stale = {**answer, "message_id": "stale_answer"}
        self.assertEqual(self.service.execute(self.family.token, envelope(self.fresh(), "conversation.message", stale, "stale_multiple"))["status"], "rejected")
        latest = self.fresh()["conversation"]["turns"][-1]
        skip = {"message_id": "skip", "text": "Skip", "reply_to_turn_id": latest["id"], "question_id": latest["questions"][0]["id"], "skipped": True}
        snapshot = self.family.accept(self.service.execute(self.family.token, envelope(self.fresh(), "conversation.message", skip, "skip_question")))
        self.assertEqual(snapshot["finance"]["ledger"]["actual_events"], [])
        self.assertFalse(snapshot["check_in"]["enrolled"])

    def test_operator_read_is_access_audited_with_minimal_metadata(self):
        self.family.help()
        operator = self.service.provision_operator([self.family.case_id], operator_id="audit_operator")
        self.service.read_operator_queue(operator["session_token"], self.family.case_id)
        with self.service._connection() as connection:
            tables = {row["name"] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertIn("access_audit", tables, "MVP blocker: operator projection reads leave no durable access audit")
            rows = [dict(row) for row in connection.execute("SELECT * FROM access_audit")]
        self.assertTrue(rows)
        serialized = json.dumps(rows)
        self.assertIn("audit_operator", serialized)
        self.assertNotIn(operator["session_token"], serialized)
        self.assertNotIn("Synthetic food request", serialized)
        other = Journey(self.service)
        with self.assertRaises(ServiceError):
            self.service.read_operator_queue(operator["session_token"], other.case_id)
        self.service.revoke_operator(operator["operator_id"])
        with self.assertRaises(ServiceError):
            self.service.read_operator_queue(operator["session_token"])
        with self.service._connection() as connection:
            outcomes = {row["outcome"] for row in connection.execute("SELECT outcome FROM access_audit")}
        self.assertTrue({"granted", "case_unavailable", "unauthorized"} <= outcomes)


class AdapterAssertions:
    """Assertions shared across offline dispatch and actual HTTP, kept distinct."""
    def create_http_family(self):
        status, session, _ = self.client.request("POST", "/v1/sessions", {"contract_version": "0.1"})
        self.assertEqual(status, 201)
        token = session["session_token"]
        status, result, headers = self.client.request("POST", "/v1/cases", {"contract_version": "0.1", "event_id": "http_create", "time_zone": ZONE}, token)
        self.assertEqual(status, 200)
        validate("CommandResult", result)
        return token, result["case_snapshot"]

    def test_adapter_finance_resume_replay_conflict_scope_and_operator_authority(self):
        token, snapshot = self.create_http_family()
        request = envelope(snapshot, "finance.update", {"operation": "set_money_source", "record": money()}, "http_money")
        status, result, headers = self.client.request("POST", "/v1/commands", request, token)
        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "applied", result["issues"])
        if self.transport == "loopback":
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(self.client.request("POST", "/v1/commands", request, token)[1]["status"], "already_applied")
        conflicting = {**request, "event_id": "http_conflict"}
        self.assertEqual(self.client.request("POST", "/v1/commands", conflicting, token)[0], 409)
        self.assertEqual(self.client.request("GET", "/v1/cases/" + snapshot["case_id"], token=token)[1], result["case_snapshot"])
        stranger = self.client.request("POST", "/v1/sessions", {"contract_version": "0.1"})[1]["session_token"]
        for case_id in (snapshot["case_id"], "absent"):
            self.assertEqual(self.client.request("GET", "/v1/cases/" + case_id, token=stranger)[0], 404)
        self.assertEqual(self.client.request("GET", "/v1/operator/queue", token=token)[0], 401)
        self.assertEqual(self.client.request("POST", "/v1/sessions", {"contract_version": "0.1", "role": "operator"})[0], 400)
        self.assertEqual(self.client.request("POST", "/v1/operator/provision", {"case_ids": [snapshot["case_id"]]}, token)[0], 404)

    def test_adapter_strict_json_body_and_version_headers(self):
        for raw in ('{"contract_version":"0.1","contract_version":"0.1"}', '{"x":NaN}', '[]', '{'):
            self.assertEqual(self.client.request("POST", "/v1/sessions", raw=raw)[0], 400)
        self.assertEqual(self.client.request("POST", "/v1/sessions", {"contract_version": "0.1"}, headers={"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.client.request("POST", "/v1/sessions", raw=" " * 65537)[0], 400)
        token, snapshot = self.create_http_family()
        self.assertEqual(self.client.request("GET", "/v1/cases/" + snapshot["case_id"], token=token, headers={"X-Contract-Version": "wrong"})[0], 400)

    def test_adapter_simulated_operator_projection_and_revocation(self):
        token, snapshot = self.create_http_family()
        request = envelope(snapshot, "help.request", {"consent": True, "message": "Synthetic request"}, "http_help")
        status, result, _ = self.client.request("POST", "/v1/commands", request, token)
        self.assertEqual(status, 200)
        operator = self.service.provision_operator([snapshot["case_id"]])
        status, queue, _ = self.client.request("GET", "/v1/operator/queue", token=operator["session_token"])
        self.assertEqual(status, 200)
        self.assertNotIn("finance", queue["cases"][0])
        request_id = queue["cases"][0]["reviews"][0]["request_id"]
        ack = envelope(result["case_snapshot"], "follow_up.acknowledge", {"request_id": request_id}, "http_ack", channel="operator")
        status, accepted, _ = self.client.request("POST", "/v1/operator/commands", ack, operator["session_token"])
        self.assertEqual(status, 200)
        self.assertNotIn("case_snapshot", accepted)
        self.service.revoke_operator(operator["operator_id"])
        self.assertEqual(self.client.request("GET", "/v1/operator/queue", token=operator["session_token"])[0], 401)


class OfflineHandlerTests(AdapterAssertions, AcceptanceCase):
    transport = "memory"
    def setUp(self):
        super().setUp()
        self.client = MemoryHTTP(self.service, AgentRuntime(self.service, AgentConfig()))


class RealHTTPTests(AdapterAssertions, AcceptanceCase):
    transport = "loopback"
    def setUp(self):
        super().setUp()
        # PermissionError remains an error and the runner labels it blocked.
        self.server = CaseHTTPServer(("127.0.0.1", 0), self.service, AgentRuntime(self.service, AgentConfig()))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        self.client = LoopbackHTTP(self.server)

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
