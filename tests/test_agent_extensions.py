"""Owned adapters plus disposable tests of the exact unapplied owner proposal."""

import copy
import tempfile
import time
import unittest
from pathlib import Path

from backend.stillhere.agent.tools import AgentFailure
from backend.stillhere.agent_extensions import ExtensionConfig, correlate_answer, create_registry, normalize_reply
from backend.stillhere.agent_extensions.adapters import child_event_id
from backend.stillhere.agent_extensions.registry import TOOLS
from backend.stillhere.agent_extensions.schema import validate
from backend.stillhere.agent_extensions.testing import (NOW, application_arguments, command, context_for,
    create_case, run_proposal_test, seed_finance, seed_plan)
from backend.stillhere.contracts import InvalidInput
from backend.stillhere.service import CaseService


QUESTION = {"id": "q_transport", "prompt": "Which transport is available?", "kind": "single_choice",
            "choices": [{"id": "bus", "label": "Bus"}, {"id": "ride", "label": "Ride"}], "allow_skip": True}


class ExtensionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "cases.sqlite3"
        self.now = NOW
        self.service = CaseService(self.path, clock=lambda: self.now)
        self.token, self.snapshot = create_case(self.service)

    def all_tools(self):
        return create_registry(config=ExtensionConfig(**{key: True for key in vars(ExtensionConfig())}))

    def test_default_off_and_each_family_independent(self):
        self.assertEqual(create_registry().definitions, ())
        for family in vars(ExtensionConfig()):
            registry = create_registry(config=ExtensionConfig(**{family: True}))
            self.assertTrue(registry.definitions)
            self.assertTrue(all(item.family == family for item in registry.definitions))
        for name in ("schedule_check_in", "share_location", "provision_operator", "follow_up.record"):
            self.assertNotIn(name, self.all_tools().by_name)

    def test_synthetic_environment_flags_strict_and_default_off(self):
        self.assertEqual(ExtensionConfig.from_environment({}), ExtensionConfig())
        self.assertTrue(ExtensionConfig.from_environment({"STILLHERE_AGENT_ENABLE_FINANCE_UPDATES": "true"}).finance_updates)
        with self.assertRaises(ValueError):
            ExtensionConfig.from_environment({"STILLHERE_AGENT_ENABLE_CHECK_INS": "1"})
        with self.assertRaises(ValueError):
            ExtensionConfig(check_ins=1)

    def test_stable_child_events_are_logical_and_parent_scoped(self):
        a = child_event_id("case", "parent", "finance.update", {"b": 1, "a": 2})
        self.assertEqual(a, child_event_id("case", "parent", "finance.update", {"a": 2, "b": 1}))
        self.assertNotEqual(a, child_event_id("case", "other", "finance.update", {"a": 2, "b": 1}))

    def test_arguments_reject_forged_authority_context_consent_for_every_tool(self):
        registry = self.all_tools()
        for item in TOOLS:
            for key in ("case_id", "token", "run_id", "expected_version", "role", "authority", "consent", "agency_receipts"):
                with self.subTest(tool=item.name, key=key), self.assertRaises(InvalidInput):
                    registry.validate_arguments(item.name, {key: True})

    def test_finance_union_cannot_mix_operations_or_extra_fields(self):
        for update in ({"operation": "record_expense"}, {"operation": "set_balance", "money_source_id": "cash", "balance_cents": 1, "as_of": NOW, "reflected_event_ids": [], "record": {}},
                       {"operation": "set_money_source", "record": {"role": "operator"}}):
            with self.assertRaises(InvalidInput):
                validate("FinancialUpdateArguments", {"update": update})

    def test_bounded_arguments_reject_cycles_nonfinite_and_oversized(self):
        cyclic = {}; cyclic["update"] = cyclic
        for arguments in (cyclic, {"update": float("nan")}, {"update": "x"*17000}):
            with self.assertRaises(InvalidInput):
                self.all_tools().validate_arguments("update_financial_state", arguments)

    def test_budget_expiry_and_calls_precede_effects(self):
        context, _ = context_for(self.service, self.token, self.snapshot)
        context.deadline = 0
        with self.assertRaises(AgentFailure):
            self.all_tools().invoke("read_check_in_status", {}, context)
        context.deadline = time.monotonic()+30; context.calls = context.max_tool_calls
        with self.assertRaises(AgentFailure):
            self.all_tools().invoke("read_check_in_status", {}, context)

    def test_read_does_not_silently_reconcile_concurrent_versions(self):
        context, _ = context_for(self.service, self.token, self.snapshot)
        self.service.execute(self.token, command(self.service.read_case(self.token, self.snapshot["case_id"]), "fact.correct",
                             {"fact_key": "mobility", "value": "no_car", "observed_at": NOW}, "concurrent"))
        with self.assertRaises(AgentFailure):
            self.all_tools().invoke("read_check_in_status", {}, context)
        self.assertTrue(context.writes_conflicted)

    def test_structured_validation_text_compatibility_and_exact_correlation(self):
        self.assertEqual(normalize_reply(self.snapshot, "**ordinary Markdown**", now=NOW)["questions"], [])
        result = normalize_reply(self.snapshot, {"text": "Unknown transport.", "questions": [QUESTION]}, now=NOW)
        self.snapshot["conversation"]["turns"].append({"id": "saved", "role": "assistant", "state": "complete", **result})
        payload = {"message_id": "answer", "text": "Bus", "reply_to_turn_id": "saved", "question_id": "q_transport", "choice_id": "bus"}
        self.assertEqual(correlate_answer(self.snapshot, payload)["choice_ids"], ["bus"])
        self.assertIsNone(correlate_answer(self.snapshot, {"message_id": "legacy", "text": "legacy"}))
        with self.assertRaises(InvalidInput):
            correlate_answer(self.snapshot, {"message_id": "legacy", "text": "legacy", "choice_id": "anything"})
        for changes in ({"reply_to_turn_id": "other_household"}, {"question_id": "other"}, {"choice_id": "foreign"},
                        {"choice_ids": ["bus"]}, {"skipped": True}):
            with self.assertRaises(InvalidInput):
                correlate_answer(self.snapshot, {**payload, **changes})
        skipped = {key: value for key, value in payload.items() if key != "choice_id"}
        self.assertTrue(correlate_answer(self.snapshot, {**skipped, "skipped": True})["skipped"])
        self.snapshot["conversation"]["turns"].append({"role": "user", "reply_to_turn_id": "saved", "question_id": "q_transport"})
        with self.assertRaises(InvalidInput):
            correlate_answer(self.snapshot, payload)

    def test_questions_cardinality_duplicate_ids_markup_and_preselection_denied(self):
        from backend.stillhere.outputs.validation import OutputValidationError
        for question in ({**QUESTION, "choices": QUESTION["choices"][:1]}, {**QUESTION, "kind": "text"},
                         {**QUESTION, "allow_skip": False}, {**QUESTION, "selected": "bus"},
                         {**QUESTION, "choices": [{"id": "q_transport", "label": "Same"}, QUESTION["choices"][1]]}):
            with self.assertRaises(OutputValidationError):
                normalize_reply(self.snapshot, {"text": "Bounded reply.", "questions": [question]}, now=NOW)
        with self.assertRaises(OutputValidationError):
            normalize_reply(self.snapshot, {"text": "<script>bad</script>"}, now=NOW)

    def test_proposed_finance_mutations_restart_and_exact_child_replay(self):
        if run_proposal_test(self): return
        self.snapshot = seed_finance(self.service, self.token, self.snapshot)
        context, request = context_for(self.service, self.token, self.snapshot)
        registry = self.all_tools()
        args = {"update": {"operation": "record_expense", "record": {"id": "spent", "kind": "expense", "currency": "USD",
                            "amount_cents": 1200, "money_source_id": "cash", "category": "food", "commitment_id": "additional", "source": "user_reported"}}}
        accepted = registry.invoke("update_financial_state", args, context)
        self.assertEqual(accepted["status"], "applied", accepted)
        duplicate = registry.invoke("update_financial_state", args, context)
        self.assertEqual(duplicate["status"], "already_applied")
        self.assertEqual(duplicate["event_id"], child_event_id(context.case_id, context.event_id, "finance.update", args["update"]))
        scenario = {"scenario": {"id": "hypothesis", "label": "Possible help", "receipts": [{"id": "possible", "state": "hypothetical", "amount_cents": 5000, "date": "2026-10-18", "currency": "USD", "restrictions": []}]}, "start_date": "2026-10-12"}
        self.assertEqual(registry.invoke("set_financial_scenario", scenario, context)["status"], "applied")
        comparison = registry.invoke("compare_financial_scenarios", {"start_date": "2026-10-12"}, context)
        self.assertEqual(comparison["summary"]["finance"]["baseline"]["ending_projected_position_cents"], 28800)
        self.assertEqual(comparison["summary"]["finance"]["scenarios"][0]["ending_projected_position_cents"], 33800)
        after = self.service.finish_agent_turn(self.token, context.case_id, context.event_id, context.run_id, "Saved hypothetical comparison.")
        restarted = CaseService(self.path, clock=lambda: NOW)
        self.assertEqual(restarted.read_case(self.token, context.case_id), after)
        self.assertEqual(restarted.execute(self.token, request)["case_snapshot"], after)
        self.assertIsNone(restarted.claim_agent_turn(self.token, context.case_id, context.event_id, 30))
        self.assertEqual(len(after["finance"]["ledger"]["actual_events"]), 1)
        self.assertEqual(after["finance"]["ledger"]["money_sources"][0]["balance_cents"], 28800)

    def test_proposed_authorization_denies_operator_enrollment_location_and_forged_help(self):
        if run_proposal_test(self): return
        context, _ = context_for(self.service, self.token, self.snapshot)
        for operation in ("check_in.enroll", "location.share", "provision_operator", "follow_up.acknowledge", "follow_up.record", "check_in.process_due"):
            result = self.service.execute_agent_extension_command(self.token, context.case_id, context.event_id, context.run_id,
                            operation, {"consent": True, "role": "operator"}, context.expected_version, context.deadline)
            self.assertEqual(result["status"], "rejected", operation)
            self.assertEqual(result["issues"][0]["code"], "tool_forbidden")
        result = self.all_tools().invoke("request_help", {"message": "Synthetic help"}, context)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["issues"][0]["code"], "explicit_help_consent_required")
        self.assertEqual(self.service.read_case(self.token, context.case_id)["follow_ups"], [])
        # The exact same text is insufficient; only explicit saved direct-control data qualifies.
        self.service.finish_agent_turn(self.token, context.case_id, context.event_id, context.run_id, "Consent required.")
        snapshot = self.service.read_case(self.token, context.case_id)
        help_payload = {"message": "Synthetic help"}
        context, _ = context_for(self.service, self.token, snapshot, "consented", help_request={**help_payload, "consent": True})
        self.assertEqual(self.all_tools().invoke("request_help", help_payload, context)["status"], "applied")
        self.assertEqual(len(self.service.read_case(self.token, context.case_id)["follow_ups"]), 1)

    def test_proposed_scope_stale_version_expired_run_and_oversize_rollback(self):
        if run_proposal_test(self): return
        self.snapshot = seed_finance(self.service, self.token, self.snapshot)
        context, _ = context_for(self.service, self.token, self.snapshot)
        args = {"operation": "set_balance", "money_source_id": "cash", "balance_cents": 20000, "as_of": NOW, "reflected_event_ids": []}
        other, other_case = create_case(self.service)
        result = self.service.execute_agent_extension_command(other, context.case_id, context.event_id, context.run_id,
                "finance.update", args, context.expected_version, context.deadline)
        self.assertIsNone(result["case_snapshot"])
        result = self.service.execute_agent_extension_command(self.token, other_case["case_id"], context.event_id, context.run_id,
                "finance.update", args, context.expected_version, context.deadline)
        self.assertIsNone(result["case_snapshot"])
        result = self.service.execute_agent_extension_command(self.token, context.case_id, context.event_id, context.run_id,
                "finance.update", args, context.expected_version-1, context.deadline)
        self.assertEqual(result["status"], "conflict")
        before = self.service.read_case(self.token, context.case_id)
        result = self.service.execute_agent_extension_command(self.token, context.case_id, context.event_id, context.run_id,
                "finance.update", args, context.expected_version, context.deadline, 10)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(self.service.read_case(self.token, context.case_id), before)
        self.now = "2026-10-11T06:01:00Z"
        result = self.service.execute_agent_extension_command(self.token, context.case_id, context.event_id, context.run_id,
                "finance.update", args, context.expected_version, context.deadline)
        self.assertEqual(result["issues"][0]["code"], "agent_run_inactive")
        self.assertEqual(self.service.read_case(self.token, context.case_id), before)

    def test_proposed_application_prepare_update_dashboard_and_approval_without_money(self):
        if run_proposal_test(self): return
        self.snapshot = seed_plan(self.service, self.token, self.snapshot)
        context, _ = context_for(self.service, self.token, self.snapshot)
        registry = self.all_tools()
        prepared = registry.invoke("prepare_application", application_arguments(self.snapshot), context)
        self.assertEqual(prepared["status"], "applied", prepared)
        before_money = copy.deepcopy(self.snapshot["finance"]["ledger"])
        approved = registry.invoke("update_application", {"application_id": "application_synthetic", "stage_change": {"stage": "approved", "corrects_event_id": None}}, context)
        self.assertEqual(approved["status"], "applied", approved)
        app = self.service.read_case(self.token, context.case_id)["applications"][0]
        self.assertEqual(app["stage_report"]["stage"], "approved")
        self.assertIsNone(app["agency_outcome"])
        self.assertEqual(self.service.read_case(self.token, context.case_id)["finance"]["ledger"], before_money)
        dashboard = registry.invoke("publish_dashboard_components", {"components": [{"id": "aid", "kind": "aid_tracker", "record_ids": [app["id"]], "display_order": 0}]}, context)
        self.assertEqual(dashboard["status"], "applied", dashboard)
        bad = registry.invoke("publish_dashboard_components", {"components": [{"id": "aid", "kind": "aid_tracker", "record_ids": ["foreign_household"], "display_order": 0}]}, context)
        self.assertEqual(bad["status"], "rejected")

    def test_proposed_structured_finish_answer_replay_multiple_choice_and_race(self):
        if run_proposal_test(self): return
        from backend.stillhere.outputs import prepare_structured_reply
        context, _ = context_for(self.service, self.token, self.snapshot)
        snap = self.service.read_case(self.token, context.case_id)
        question = {**QUESTION, "kind": "multiple_choice"}
        prepared = prepare_structured_reply(snap, {"text": "Transport remains unknown.", "questions": [question]}, now=NOW)
        saved = self.service.finish_agent_turn(self.token, context.case_id, context.event_id, context.run_id, reply=prepared)
        turn = saved["conversation"]["turns"][-1]
        answer = command(saved, "conversation.message", {"message_id": "answer", "text": "Bus and ride", "reply_to_turn_id": turn["id"], "question_id": question["id"], "choice_ids": ["bus", "ride"]}, "answer")
        result = self.service.execute(self.token, answer)
        self.assertEqual(result["status"], "applied", result)
        self.assertEqual(self.service.execute(self.token, answer)["status"], "already_applied")
        saved = result["case_snapshot"]
        user = next(t for t in saved["conversation"]["turns"] if t["id"] == "answer")
        self.assertEqual(user["choice_ids"], ["bus", "ride"])
        second = command(saved, "conversation.message", {**answer["payload"], "message_id": "second"}, "second")
        self.assertEqual(self.service.execute(self.token, second)["status"], "rejected")
        # A concurrent write makes the prepared version stale at the finish boundary.
        claim = self.service.claim_agent_turn(self.token, context.case_id, "answer", 30)
        snap = claim["snapshot"]
        prepared = prepare_structured_reply(snap, {"text": "Stale reply."}, now=NOW)
        self.service.execute(self.token, command(snap, "fact.correct", {"fact_key": "mobility", "value": "no_car", "observed_at": NOW}, "race"))
        saved = self.service.finish_agent_turn(self.token, context.case_id, "answer", claim["run_id"], reply=prepared)
        self.assertEqual(saved["conversation"]["turns"][-1]["state"], "failed")
        self.assertNotIn("questions", saved["conversation"]["turns"][-1])

    def test_proposed_domain_no_car_dated_null_cost_and_report_during_outage(self):
        if run_proposal_test(self, boundary=True): return
        self.snapshot = seed_finance(self.service, self.token, self.snapshot)
        self.snapshot = seed_plan(self.service, self.token, self.snapshot)
        args = application_arguments(self.snapshot)
        self.snapshot = self.service.seed_agent_extension_smoke_costs(self.token, self.snapshot["case_id"], args["action_id"], "2026-10-12")
        context, _ = context_for(self.service, self.token, self.snapshot)
        registry = self.all_tools()
        scenario = {"scenario": {"id": "unknown_online", "label": "Hypothetical online path", "alternative_ids": [args["action_id"]]}, "start_date": "2026-10-12"}
        result = registry.invoke("set_financial_scenario", scenario, context)
        self.assertEqual(result["status"], "applied", result)
        result = registry.invoke("compare_financial_scenarios", {"start_date": "2026-10-12"}, context)
        self.assertEqual(result["status"], "applied", result)
        scenario_result = result["summary"]["finance"]["scenarios"][0]
        self.assertEqual(scenario_result["state"], "incomplete")
        self.assertIsNone(scenario_result["ending_projected_position_cents"])
        self.assertEqual(registry.invoke("prepare_application", args, context)["status"], "applied")
        from unittest.mock import patch
        from backend.stillhere.service import ServiceError
        before = self.service.read_case(self.token, context.case_id)
        with patch.object(self.service, "_application_rules", side_effect=ServiceError(503, "application_rules_unavailable", "Synthetic outage")):
            reported = registry.invoke("update_application", {"application_id": args["application_id"], "stage_change": {"stage": "approved", "corrects_event_id": None}}, context)
        self.assertEqual(reported["status"], "applied", reported)
        after = self.service.read_case(self.token, context.case_id)
        self.assertEqual(after["applications"][0]["preparation_state"], "pending")
        self.assertEqual(after["applications"][0]["prepared_at"], before["applications"][0]["prepared_at"])
        self.assertEqual(after["applications"][0]["stage_report"]["stage"], "approved")
        self.assertIsNone(after["applications"][0]["agency_outcome"])
        self.assertEqual(after["finance"]["ledger"], before["finance"]["ledger"])

    def test_proposed_domain_unknown_date_requires_clarification_without_scenario_write(self):
        if run_proposal_test(self, boundary=True): return
        self.snapshot = seed_finance(self.service, self.token, self.snapshot)
        self.snapshot = seed_plan(self.service, self.token, self.snapshot)
        args = application_arguments(self.snapshot)
        context, _ = context_for(self.service, self.token, self.snapshot)
        before = self.service.read_case(self.token, context.case_id)
        result = self.all_tools().invoke("set_financial_scenario", {"scenario": {"id": "undated", "label": "Unknown cost date", "alternative_ids": [args["action_id"]]}, "start_date": "2026-10-12"}, context)
        self.assertEqual(result["status"], "needs_clarification", result)
        self.assertEqual(self.service.read_case(self.token, context.case_id), before)

    def test_live_harness_refuses_unacknowledged_runs_without_loading_configuration(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import patch
        from backend.stillhere.agent_extensions.live_smoke import main
        output = StringIO()
        with redirect_stdout(output), patch("backend.stillhere.agent_extensions.live_smoke.load_local_environment") as loader:
            self.assertEqual(main(["--mode", "finance", "--env-file", "private-must-not-load"]), 2)
        loader.assert_not_called()
        self.assertIn('"live_status": "pending"', output.getvalue())

    def test_proposed_finance_denies_forged_backend_ownership_and_provenance_directly(self):
        if run_proposal_test(self): return
        context, _ = context_for(self.service, self.token, self.snapshot)
        for field in ("origin", "planner_cost_id", "rule_id", "rule_version", "actual_event_ids", "verification_state", "role", "authority"):
            payload = {"operation": "set_commitment", "record": {"id": "fake", "category": "documents", "amount_cents": 100, "date": "2026-10-12", "essential": False, "priority": 10, field: "forged"}}
            result = self.service.execute_agent_extension_command(self.token, context.case_id, context.event_id, context.run_id,
                "finance.update", payload, context.expected_version, context.deadline)
            self.assertEqual(result["status"], "rejected", field)
            direct = self.service.execute(self.token, command(self.service.read_case(self.token, context.case_id), "finance.update", payload, "direct_"+field))
            self.assertEqual(direct["status"], "rejected", field)
        self.assertEqual(self.service.read_case(self.token, context.case_id)["finance"]["ledger"]["expense_commitments"], [])

    def test_proposed_reply_stage_invalidated_by_later_domain_write(self):
        if run_proposal_test(self): return
        self.snapshot = seed_finance(self.service, self.token, self.snapshot)
        context, _ = context_for(self.service, self.token, self.snapshot)
        registry = self.all_tools()
        staged = registry.invoke("prepare_structured_reply", {"text": "Cash unchanged."}, context)
        result = registry.invoke("update_financial_state", {"update": {"operation": "set_balance", "money_source_id": "cash", "balance_cents": 20000, "as_of": NOW, "reflected_event_ids": []}}, context)
        self.assertEqual(result["status"], "applied")
        saved = self.service.finish_agent_turn(self.token, context.case_id, context.event_id, context.run_id, reply=staged)
        self.assertEqual(saved["conversation"]["turns"][-1]["state"], "failed")
        self.assertEqual(saved["finance"]["ledger"]["money_sources"][0]["balance_cents"], 20000)

    def test_unwired_command_factory_fails_closed_before_any_effect(self):
        context, _ = context_for(self.service, self.token, self.snapshot)
        service = context.service
        class MissingAPI:
            def __getattr__(self, name):
                if name == "execute_agent_extension_command": raise AttributeError(name)
                return getattr(service, name)
        context.service = MissingAPI()
        before = self.service.read_case(self.token, context.case_id)
        with self.assertRaises(AgentFailure) as caught:
            self.all_tools().invoke("update_financial_state", {"update": {"operation": "set_balance", "money_source_id": "cash", "balance_cents": 1, "as_of": NOW, "reflected_event_ids": []}}, context)
        self.assertEqual(caught.exception.issue["code"], "extension_integration_required")
        self.assertEqual(self.service.read_case(self.token, context.case_id), before)

    def test_proposed_saved_action_quote_change_requires_explicit_refresh(self):
        if run_proposal_test(self, boundary=True): return
        self.snapshot = seed_finance(self.service, self.token, self.snapshot)
        self.snapshot = seed_plan(self.service, self.token, self.snapshot)
        args = application_arguments(self.snapshot)
        self.snapshot = self.service.seed_agent_extension_smoke_costs(self.token, self.snapshot["case_id"], args["action_id"], "2026-10-12")
        context, _ = context_for(self.service, self.token, self.snapshot)
        registry = self.all_tools()
        scenario = {"scenario": {"id": "retained_quote", "label": "Hypothetical path", "alternative_ids": [args["action_id"]]}, "start_date": "2026-10-12"}
        self.assertEqual(registry.invoke("set_financial_scenario", scenario, context)["status"], "applied")
        self.service.finish_agent_turn(self.token, context.case_id, context.event_id, context.run_id, "Hypothetical quote saved.")
        changed = self.service.seed_agent_extension_smoke_costs(self.token, context.case_id, args["action_id"], "2026-10-13")
        old_snapshot = copy.deepcopy(changed["finance"]["ledger"]["scenarios"][0]["action_cost_snapshot"])
        context, _ = context_for(self.service, self.token, changed, "new_quote")
        before = self.service.read_case(self.token, context.case_id)
        rejected = registry.invoke("compare_financial_scenarios", {"start_date": "2026-10-12"}, context)
        self.assertEqual(rejected["status"], "rejected")
        self.assertEqual(self.service.read_case(self.token, context.case_id), before)
        self.assertEqual(registry.invoke("set_financial_scenario", scenario, context)["status"], "applied")
        new_snapshot = self.service.read_case(self.token, context.case_id)["finance"]["ledger"]["scenarios"][0]["action_cost_snapshot"]
        self.assertNotEqual(new_snapshot, old_snapshot)
        self.assertEqual(registry.invoke("compare_financial_scenarios", {"start_date": "2026-10-12"}, context)["status"], "applied")

    def test_proposed_case_service_rejects_nonfinite_cyclic_and_invalid_arguments(self):
        if run_proposal_test(self): return
        context, _ = context_for(self.service, self.token, self.snapshot)
        cyclic = {}; cyclic["record"] = cyclic
        before = self.service.read_case(self.token, context.case_id)
        for arguments in (cyclic, {"operation": "set_balance", "balance_cents": float("nan")}, {}, {"role": "operator"}):
            result = self.service.execute_agent_extension_command(self.token, context.case_id, context.event_id, context.run_id,
                "finance.update", arguments, context.expected_version, context.deadline)
            self.assertEqual(result["status"], "rejected")
        self.assertEqual(self.service.read_case(self.token, context.case_id), before)


if __name__ == "__main__":
    unittest.main()
