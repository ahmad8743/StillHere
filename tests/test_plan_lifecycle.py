"""Synthetic C05 plan commits/task reports; no private configuration or provider calls."""

import copy
import json
import io
import os
import tempfile
import time
import unittest
from pathlib import Path
from contextlib import redirect_stdout
from unittest.mock import patch

from backend.stillhere.agent import AgentConfig, AgentRuntime
from backend.stillhere.agent.registry import CASE_TOOLS, PLAN_REVISION_TOOL, TASK_TOOL, ToolRegistry
from backend.stillhere.agent.tools import AgentContext, AgentFailure
from backend.stillhere.contracts import validate
from backend.stillhere.planner.plans import revise_plan
from backend.stillhere.service import CaseService

NOW = "2026-10-11T06:00:00Z"
PROGRAM = "co_state_id_replacement"


class PlanRevisionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(); self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "synthetic.sqlite3"
        self.service = CaseService(self.path, clock=lambda: NOW)
        self.token = self.service.create_session()["session_token"]
        self.case_id = self.service.create_case(self.token, {"contract_version": "0.1", "event_id": "create", "time_zone": "America/Chicago"})["case_snapshot"]["case_id"]
        self.correct("document_issuing_state", "CO")
        self.registry = ToolRegistry(CASE_TOOLS + (PLAN_REVISION_TOOL, TASK_TOOL))

    def snapshot(self):
        return self.service.read_case(self.token, self.case_id)

    def command(self, event="chat", kind="conversation.message", payload=None):
        return {"contract_version": "0.1", "case_id": self.case_id, "event_id": event,
                "expected_case_version": self.snapshot()["case_version"], "occurred_at": NOW, "channel": "chat", "type": kind,
                "payload": payload or {"message_id": "user_" + event, "text": "Revise my recovery plan."}}

    def correct(self, key, value, event=None):
        return self.service.execute(self.token, self.command(event or key, "fact.correct", {"fact_key": key, "value": value, "observed_at": NOW}))

    def claim(self):
        self.service.execute(self.token, self.command())
        claim = self.service.claim_agent_turn(self.token, self.case_id, "chat", 60)
        return AgentContext(self.service, self.token, self.case_id, "chat", claim["run_id"], claim["snapshot"]["case_version"],
                            time.monotonic() + 60, 32, 48000)

    def revise(self, context, **extra):
        return self.invoke("revise_recovery_plan", {"program_id": PROGRAM, **extra}, context)

    def invoke(self, name, payload, context):
        result = self.registry.invoke(name, payload, context)
        if "plan_summary" in result:
            validate("RecoveryMutationResult", result)
            return {**result, "case_snapshot": self.snapshot() if result["plan_summary"] is not None else None}
        return result

    def test_atomic_versioned_plan_projection_is_sourced_provisional_and_does_not_mutate_facts_money_or_policy(self):
        context = self.claim(); before = self.snapshot(); catalog = self.service.read_program_catalog()
        result = self.revise(context)
        self.assertEqual(result["status"], "applied")
        after = result["case_snapshot"]
        self.assertEqual(after["case_version"], before["case_version"] + 1)
        plan = after["plan"]
        self.assertEqual((plan["state"], plan["version"], plan["input_case_version"]), ("provisional", 1, before["case_version"]))
        self.assertEqual(len(plan["actions"]), 2)
        self.assertTrue(plan["questions"])
        self.assertTrue(all(action["status"] == "waiting" for action in plan["actions"]))
        for action in plan["actions"]:
            validate("RecoveryPlanAction", action)
            self.assertTrue(action["source_records"])
            self.assertIsNone(action["costs"]["fee_cents"])
            self.assertIsNone(action["deadline"])
        for key in ("facts", "needs", "evidence", "resources", "applications", "check_in", "shared_location", "follow_ups", "components"):
            self.assertEqual(after[key], before[key])
        self.assertEqual(after["finance"]["ledger"], before["finance"]["ledger"])
        self.assertEqual(self.service.read_program_catalog(), catalog)
        self.assertEqual(CaseService(self.path).read_case(self.token, self.case_id), after)
        with self.service._connection() as connection:
            audit = connection.execute("SELECT before_case_json FROM events WHERE case_id=? AND event_id=?", (self.case_id, result["event_id"])).fetchone()
        self.assertEqual(json.loads(audit[0]), before)

    def test_same_turn_duplicate_plan_revision_is_one_effect_even_after_own_version_increment(self):
        context = self.claim()
        first = self.revise(context); second = self.revise(context)
        self.assertEqual(second["status"], "already_applied")
        self.assertEqual(second["event_id"], first["event_id"])
        self.assertEqual(second["case_snapshot"], first["case_snapshot"])

    def test_fact_change_allows_a_new_revision_with_stable_actions_and_clears_pending_marker(self):
        context = self.claim(); first = self.revise(context)
        changed = self.registry.invoke("correct_fact", {"fact_key": "office_transport_available", "value": False, "observed_at": NOW}, context)
        self.assertEqual(changed["case_snapshot"]["plan"]["state"], "pending")
        revised = self.revise(context)
        self.assertEqual(revised["status"], "applied")
        self.assertNotEqual(revised["event_id"], first["event_id"])
        self.assertEqual(revised["case_snapshot"]["plan"]["version"], 2)
        self.assertNotIn("pending_input_case_version", revised["case_snapshot"]["plan"])
        self.assertEqual([a["id"] for a in revised["case_snapshot"]["plan"]["actions"]], [a["id"] for a in first["case_snapshot"]["plan"]["actions"]])
        self.assertEqual(revised["case_snapshot"]["plan"]["actions"][1]["status"], "blocked")

    def test_model_cannot_supply_a_plan_facts_costs_identity_or_authority(self):
        context = self.claim(); before = self.snapshot()
        for extra in ({"plan": {}}, {"case_id": "other"}, {"facts": {}}, {"costs": {"fee_cents": 0}}, {"role": "operator"}, {"as_of": NOW}):
            self.assertEqual(self.revise(context, **extra)["error"]["code"], "invalid_tool_input")
        self.assertEqual(self.snapshot(), before)

    def test_wrong_household_cannot_read_catalog_or_commit_a_plan(self):
        context = self.claim(); context.token = self.service.create_session()["session_token"]
        with patch.object(self.service, "read_program_catalog") as lookup:
            self.assertEqual(self.revise(context)["status"], "rejected")
        lookup.assert_not_called()
        self.assertEqual(self.snapshot()["plan"]["state"], "not_requested")

    def test_stale_expected_version_blocks_revisions_and_later_mutations(self):
        context = self.claim(); self.correct("mobility", "no_car", "concurrent")
        result = self.revise(context)
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(result["case_snapshot"]["plan"]["state"], "not_requested")
        with self.assertRaises(AgentFailure):
            self.revise(context)

    def test_expired_run_or_deadline_during_catalog_read_cannot_commit(self):
        context = self.claim(); before = self.snapshot()
        with patch("backend.stillhere.planner.service.time.monotonic", side_effect=[0, 0, context.deadline + 1]):
            self.assertEqual(self.revise(context)["issues"][0]["code"], "agent_timeout")
        self.assertEqual(self.snapshot(), before)
        context.deadline = time.monotonic() + 60
        self.service.clock = lambda: "2026-10-11T06:02:00Z"
        self.assertEqual(self.revise(context)["issues"][0]["code"], "agent_run_inactive")
        self.assertEqual(self.snapshot(), before)

    def test_failed_unknown_conflicting_and_stale_rules_retain_previous_plan(self):
        context = self.claim(); self.revise(context)
        self.registry.invoke("correct_fact", {"fact_key": "document_issuing_state", "value": None, "observed_at": NOW}, context)
        before = self.snapshot()
        self.assertEqual(self.revise(context)["status"], "needs_clarification")
        self.assertEqual(self.snapshot(), before)
        self.registry.invoke("correct_fact", {"fact_key": "document_issuing_state", "value": "CO", "observed_at": NOW}, context)
        catalog = self.service.read_program_catalog()
        catalog["version"] = "synthetic.conflicting"
        extra = copy.deepcopy(catalog["rules"][0]); extra["version"] = "synthetic.v2"
        catalog["rules"].append(extra)
        before = self.snapshot()
        with patch.object(self.service, "read_program_catalog", return_value=catalog):
            self.assertEqual(self.revise(context)["status"], "needs_clarification")
        self.assertEqual(self.snapshot(), before)
        catalog["rules"] = []
        catalog["version"] = "synthetic.no_match"
        with patch.object(self.service, "read_program_catalog", return_value=catalog):
            self.assertEqual(self.revise(context)["status"], "needs_clarification")
        catalog = self.service.read_program_catalog(); catalog["version"] = "synthetic.stale"
        catalog["rules"][0]["review_expires_at"] = NOW
        with patch.object(self.service, "read_program_catalog", return_value=catalog):
            self.assertEqual(self.revise(context)["status"], "needs_clarification")
        catalog = self.service.read_program_catalog(); catalog["version"] = "synthetic.invalid"
        catalog["rules"][0]["paths"][0]["nodes"][0]["children"].append("online_root")
        with patch.object(self.service, "read_program_catalog", return_value=catalog):
            self.assertEqual(self.revise(context)["status"], "unavailable")
        self.assertEqual(self.snapshot(), before)

    def test_result_limit_prevents_commit_and_sql_failure_rolls_back_snapshot_and_audit(self):
        context = self.claim(); before = self.snapshot()
        context.max_result_chars = 100
        result = self.service.revise_agent_plan(self.token, self.case_id, context.event_id, context.run_id, {"program_id": PROGRAM}, context.expected_version, context.deadline, 100)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(self.snapshot(), before)
        context.max_result_chars = 48000
        with self.service._connection() as connection:
            connection.execute("CREATE TRIGGER synthetic_plan_failure BEFORE INSERT ON events WHEN NEW.command_json LIKE '%plan.revise%' BEGIN SELECT RAISE(ABORT, 'synthetic'); END")
        self.assertEqual(self.revise(context)["status"], "unavailable")
        self.assertEqual(self.snapshot(), before)

    def test_runtime_provider_failure_after_commit_retains_plan_and_does_not_repeat_on_replay(self):
        class Provider:
            calls = 0
            def reply(inner, snapshot, history, text, context, registry):
                inner.calls += 1
                result = registry.invoke("revise_recovery_plan", {"program_id": PROGRAM}, context)
                self.assertEqual(result["status"], "applied")
                raise RuntimeError("synthetic provider failure")
        provider = Provider(); runtime = AgentRuntime(self.service, AgentConfig(enable_plan_revision=True), provider)
        command = self.command(); result = runtime.handle(self.token, command)
        self.assertEqual(result["case_snapshot"]["conversation"]["turns"][-1]["state"], "failed")
        self.assertEqual(len(result["case_snapshot"]["plan"]["actions"]), 2)
        self.assertEqual(runtime.handle(self.token, command)["case_snapshot"], result["case_snapshot"])
        self.assertEqual(provider.calls, 1)

    def test_independent_opt_in_with_synthetic_environment(self):
        with patch.dict(os.environ, {"STILLHERE_AGENT_ENABLE_PLAN_REVISION": "true"}, clear=True):
            config = AgentConfig.from_environment()
            self.assertEqual(set(AgentRuntime(self.service, config).registry.by_name), {"read_case", "correct_fact", "revise_recovery_plan"})
            self.assertFalse(config.enable_planner)
            os.environ["STILLHERE_AGENT_ENABLE_PLAN_REVISION"] = "yes"
            with self.assertRaises(ValueError):
                AgentConfig.from_environment()


class TaskReportTests(unittest.TestCase):
    setUp = PlanRevisionTests.setUp
    snapshot = PlanRevisionTests.snapshot
    command = PlanRevisionTests.command
    correct = PlanRevisionTests.correct
    claim = PlanRevisionTests.claim
    revise = PlanRevisionTests.revise
    invoke = PlanRevisionTests.invoke

    def prepared(self):
        context = self.claim()
        self.assertEqual(self.revise(context)["status"], "applied")
        return context, self.snapshot()["plan"]["actions"]

    def task(self, action_id, event="task", **payload):
        return self.service.execute(self.token, self.command(event, "task.update", {"action_id": action_id, **payload}))

    def test_completed_report_is_durable_audited_and_replay_does_not_append_history(self):
        context, actions = self.prepared(); before = self.snapshot()
        command = self.command("complete", "task.update", {"action_id": actions[0]["id"], "status": "completed"})
        result = self.service.execute(self.token, command)
        self.assertEqual(result["status"], "applied")
        after = result["case_snapshot"]; action = after["plan"]["actions"][0]
        self.assertEqual(action["status"], "completed")
        self.assertEqual(action["history"][-1]["provenance"], "user_reported")
        self.assertEqual(action["history"][-1]["occurred_at"], NOW)
        self.assertEqual(after["plan"]["state"], "pending")
        self.assertEqual(after["plan"]["pending_input_case_version"], after["case_version"])
        self.assertEqual(after["case_version"], before["case_version"] + 1)
        self.assertEqual(self.service.execute(self.token, command)["case_snapshot"], after)
        self.assertEqual(CaseService(self.path).read_case(self.token, self.case_id), after)
        for key in ("facts", "evidence", "applications", "shared_location", "check_in", "sources"):
            self.assertEqual(after[key], before[key])
        self.assertEqual(after["finance"]["ledger"], before["finance"]["ledger"])

    def test_duplicate_task_after_own_revision_preserves_current_version_for_following_tools(self):
        context, actions = self.prepared()
        payload = {"action_id": actions[0]["id"], "status": "completed"}
        self.invoke("update_task", payload, context)
        self.revise(context)
        expected = context.expected_version
        replay = self.invoke("update_task", payload, context)
        self.assertEqual(replay["status"], "already_applied")
        self.assertEqual(context.expected_version, expected)
        self.assertFalse(context.writes_conflicted)
        self.assertEqual(self.revise(context)["status"], "already_applied")

    def test_duplicate_effect_after_concurrent_change_cannot_silently_reconcile_agent_authority(self):
        context, actions = self.prepared()
        payload = {"action_id": actions[0]["id"], "status": "completed"}
        self.invoke("update_task", payload, context)
        self.correct("email_access", True, "outside_run")
        replay = self.invoke("update_task", payload, context)
        self.assertEqual(replay["status"], "already_applied")
        self.assertTrue(context.writes_conflicted)
        self.assertEqual(replay["issues"][0]["code"], "version_conflict")
        with self.assertRaises(AgentFailure):
            self.revise(context)

    def test_future_task_reports_are_rejected_without_versions_or_history(self):
        context, actions = self.prepared(); before = self.snapshot()
        command = self.command("future", "task.update", {"action_id": actions[0]["id"], "status": "completed"})
        command["occurred_at"] = "2026-10-12T00:00:00Z"
        self.assertEqual(self.service.execute(self.token, command)["status"], "rejected")
        self.assertEqual(self.snapshot(), before)

    def test_completed_and_skipped_actions_survive_reassessment_with_unknown_eligibility(self):
        context, actions = self.prepared()
        self.invoke("update_task", {"action_id": actions[0]["id"], "status": "completed"}, context)
        self.invoke("update_task", {"action_id": actions[1]["id"], "status": "skipped"}, context)
        revised = self.revise(context)
        self.assertEqual(revised["status"], "applied")
        plan = revised["case_snapshot"]["plan"]
        self.assertEqual([a["status"] for a in plan["actions"]], ["completed", "skipped"])
        self.assertTrue(all(a["history"] for a in plan["actions"]))
        self.assertEqual(plan["household_eligibility"], "unknown")
        self.assertEqual(self.revise(context)["status"], "already_applied")

    def test_no_car_report_keeps_other_transport_unanswered_and_online_alternative_intact(self):
        context, actions = self.prepared()
        result = self.invoke("update_task", {"action_id": actions[1]["id"], "inability_reason": "no_car"}, context)
        self.assertEqual(result["status"], "applied")
        office = result["case_snapshot"]["plan"]["actions"][1]
        self.assertEqual(office["status"], "waiting")
        self.assertTrue(any(q["code"] == "task_access_unresolved" for q in office["questions"]))
        self.assertIn(actions[0]["id"], office["alternative_ids"])
        self.assertNotIn("mobility", result["case_snapshot"]["facts"])
        revised = self.revise(context)
        self.assertEqual(revised["case_snapshot"]["plan"]["actions"][1]["status"], "waiting")
        self.assertEqual(revised["case_snapshot"]["plan"]["actions"][0]["status"], "waiting")

    def test_transport_inability_blocks_only_office_and_remains_reported_after_revision(self):
        context, actions = self.prepared()
        result = self.invoke("update_task", {"action_id": actions[1]["id"], "inability_reason": "transport_unavailable"}, context)
        self.assertEqual(result["case_snapshot"]["plan"]["actions"][1]["status"], "blocked")
        self.assertEqual(result["case_snapshot"]["plan"]["actions"][0]["status"], "waiting")
        self.assertNotIn("office_transport_available", result["case_snapshot"]["facts"])
        revised = self.revise(context)
        self.assertEqual(revised["case_snapshot"]["plan"]["actions"][1]["status"], "blocked")
        self.assertIsNone(revised["case_snapshot"]["plan"]["actions"][1]["costs"]["transport_cents"])
        self.assertTrue(any(b.get("action_id") == actions[1]["id"] for b in revised["case_snapshot"]["plan"]["blockers"]))

    def test_completion_cannot_be_undone_by_skip_or_inability(self):
        context, actions = self.prepared()
        self.task(actions[0]["id"], "completed", status="completed")
        before = self.snapshot()
        for event, payload in (("skip", {"status": "skipped"}), ("unable", {"inability_reason": "other"})):
            self.assertEqual(self.task(actions[0]["id"], event, **payload)["status"], "rejected")
            self.assertEqual(self.snapshot(), before)

    def test_explicit_resolution_clears_only_the_report_and_does_not_invent_ready_requirements(self):
        context, actions = self.prepared()
        self.invoke("update_task", {"action_id": actions[1]["id"], "inability_reason": "transport_unavailable"}, context)
        result = self.invoke("update_task", {"action_id": actions[1]["id"], "inability_reason": None}, context)
        office = result["case_snapshot"]["plan"]["actions"][1]
        self.assertIsNone(office["inability_reason"])
        self.assertEqual(office["status"], "waiting")
        self.assertFalse(any(b["code"] == "task_inability_reported" for b in office["blockers"]))
        self.assertNotIn("office_transport_available", result["case_snapshot"]["facts"])
        self.assertEqual(self.revise(context)["case_snapshot"]["plan"]["actions"][1]["status"], "waiting")

    def test_replacing_a_definite_inability_with_no_car_does_not_keep_the_old_report_as_a_blocker(self):
        context, actions = self.prepared()
        self.invoke("update_task", {"action_id": actions[1]["id"], "inability_reason": "transport_unavailable"}, context)
        result = self.invoke("update_task", {"action_id": actions[1]["id"], "inability_reason": "no_car"}, context)
        office = result["case_snapshot"]["plan"]["actions"][1]
        self.assertEqual(office["status"], "waiting")
        self.assertFalse(any(b["code"] == "task_inability_reported" for b in office["blockers"]))
        self.assertTrue(any(q["code"] == "task_access_unresolved" for q in office["questions"]))

    def test_malformed_ambiguous_private_and_wrong_route_reports_are_rejected_without_effects(self):
        context, actions = self.prepared(); before = self.snapshot()
        payloads = ({"status": "ready"}, {"status": "completed", "inability_reason": "other"}, {},
                    {"inability_reason": "invented"}, {"status": "completed", "role": "operator"},
                    {"inability_reason": "no_car"}, {"inability_reason": "transport_unavailable"},
                    {"status": "completed", "document_number": "synthetic"})
        for index, payload in enumerate(payloads):
            self.assertEqual(self.task(actions[0]["id"], "invalid_" + str(index), **payload)["status"], "rejected")
            self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.task("missing", "not_found", status="completed")["status"], "rejected")

    def test_cross_household_task_id_is_not_authority_and_version_conflict_is_visible(self):
        context, actions = self.prepared()
        command = self.command("complete", "task.update", {"action_id": actions[0]["id"], "status": "completed"})
        other = self.service.create_session()["session_token"]
        self.assertEqual(self.service.execute(other, command)["status"], "rejected")
        self.correct("email_access", True, "concurrent")
        self.assertEqual(self.service.execute(self.token, command)["status"], "conflict")
        self.assertEqual(self.snapshot()["plan"]["actions"][0]["status"], "waiting")

    def test_removed_published_path_preserves_completed_action_and_pinned_source_times(self):
        context, actions = self.prepared()
        self.invoke("update_task", {"action_id": actions[0]["id"], "status": "completed"}, context)
        before = self.snapshot()["plan"]["actions"][0]
        catalog = self.service.read_program_catalog(); catalog["version"] = "synthetic.removed"
        catalog["rules"][0]["paths"] = [catalog["rules"][0]["paths"][1]]
        catalog["rules"][0]["version"] = "synthetic.next"
        with patch.object(self.service, "read_program_catalog", return_value=catalog):
            result = self.revise(context)
        self.assertEqual(result["status"], "applied")
        retained = next(a for a in result["case_snapshot"]["plan"]["actions"] if a["id"] == before["id"])
        self.assertEqual(retained["status"], "completed")
        self.assertFalse(retained["is_current"])
        self.assertEqual(retained["history"], before["history"])
        self.assertEqual(retained["source_records"], before["source_records"])

    def test_second_program_revision_keeps_previous_program_actions(self):
        context, actions = self.prepared()
        self.invoke("update_task", {"action_id": actions[0]["id"], "status": "completed"}, context)
        result = self.invoke("revise_recovery_plan", {"program_id": "co_state_id_proof_options"}, context)
        self.assertEqual(result["status"], "applied")
        self.assertEqual(len(result["case_snapshot"]["plan"]["actions"]), 4)
        retained = next(a for a in result["case_snapshot"]["plan"]["actions"] if a["id"] == actions[0]["id"])
        self.assertEqual(retained["status"], "completed")

    def test_revising_one_program_does_not_refresh_other_programs_after_fact_corrections(self):
        context, actions = self.prepared()
        self.registry.invoke("correct_fact", {"fact_key": "office_transport_available", "value": False, "observed_at": NOW}, context)
        result = self.invoke("revise_recovery_plan", {"program_id": "co_state_id_proof_options"}, context)
        plan = result["case_snapshot"]["plan"]
        self.assertEqual(plan["state"], "pending")
        self.assertTrue(all(a["input_freshness"] == "stale" for a in plan["actions"] if a["program_id"] == PROGRAM))
        result = self.revise(context)
        self.assertEqual(result["case_snapshot"]["plan"]["state"], "provisional")
        office = next(a for a in result["case_snapshot"]["plan"]["actions"] if a["path_id"] == "co_id_office_renewal")
        self.assertEqual((office["status"], office["input_freshness"]), ("blocked", "current"))

    def test_task_history_preserves_report_and_receipt_times_and_rolls_back_storage_failure(self):
        context, actions = self.prepared(); before = self.snapshot()
        with self.service._connection() as connection:
            connection.execute("CREATE TRIGGER synthetic_task_failure BEFORE UPDATE OF applied_version ON events WHEN NEW.command_json LIKE '%task.update%' BEGIN SELECT RAISE(ABORT, 'synthetic'); END")
        self.assertEqual(self.task(actions[0]["id"], status="skipped")["status"], "unavailable")
        self.assertEqual(self.snapshot(), before)
        with self.service._connection() as connection:
            connection.execute("DROP TRIGGER synthetic_task_failure")
        self.service.clock = lambda: "2026-10-11T06:00:10Z"
        result = self.task(actions[0]["id"], "dated", status="skipped")
        history = result["case_snapshot"]["plan"]["actions"][0]["history"][-1]
        self.assertEqual(history["occurred_at"], NOW)
        self.assertEqual(history["received_at"], "2026-10-11T06:00:10Z")

    def test_expired_agent_task_authority_cannot_write_and_flag_is_independent(self):
        context, actions = self.prepared(); before = self.snapshot()
        self.service.clock = lambda: "2026-10-11T06:02:00Z"
        result = self.invoke("update_task", {"action_id": actions[0]["id"], "status": "completed"}, context)
        self.assertEqual(result["issues"][0]["code"], "agent_run_inactive")
        self.assertEqual(self.snapshot(), before)
        with patch.dict(os.environ, {"STILLHERE_AGENT_ENABLE_TASKS": "true"}, clear=True):
            config = AgentConfig.from_environment()
            self.assertEqual(set(AgentRuntime(self.service, config).registry.by_name), {"read_case", "correct_fact", "update_task"})
            os.environ["STILLHERE_AGENT_ENABLE_TASKS"] = "yes"
            with self.assertRaises(ValueError):
                AgentConfig.from_environment()


class PlanSmokeTests(unittest.TestCase):
    def smoke(self, behavior="valid"):
        from backend.stillhere.agent.smoke import main
        class Provider:
            def reply(inner, snapshot, history, text, context, registry):
                if behavior == "missing":
                    return "Synthetic plain reply"
                saved = registry.invoke("revise_recovery_plan", {"program_id": PROGRAM}, context)
                online = next(a for a in saved["plan_summary"]["actions"] if a["execution_mode"] == "online")
                registry.invoke("update_task", {"action_id": online["id"], "status": "completed"}, context)
                if behavior != "no_revision":
                    registry.invoke("revise_recovery_plan", {"program_id": PROGRAM}, context)
                if behavior == "mutation":
                    registry.invoke("correct_fact", {"fact_key": "email_access", "value": True, "observed_at": NOW}, context)
                if behavior == "bad_reply":
                    return "Synthetic reply with no evidence"
                return "Saved plan preserving reported completed work; costs and eligibility unknown. " + online["official_url"]
        def runtime(service, config, diagnostics=None):
            return AgentRuntime(service, config, Provider(), diagnostics=diagnostics)
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "safe.jsonl"; output = io.StringIO()
            with patch("sys.argv", ["smoke", "--plan", "--log-file", str(log)]), \
                 patch("backend.stillhere.agent.smoke.AgentConfig.from_environment", return_value=AgentConfig(model_id="synthetic", region="synthetic")), \
                 patch("backend.stillhere.agent.smoke.AgentRuntime", side_effect=runtime), \
                 patch("backend.stillhere.agent.smoke.load_local_environment") as load, redirect_stdout(output):
                status = main()
            load.assert_not_called()
            return status, output.getvalue(), log.read_text()

    def test_user_run_plan_proof_assertions_pass_through_a_synthetic_provider_without_environment_loading(self):
        status, output, log = self.smoke()
        self.assertEqual(status, 0)
        self.assertIn("saved plan", output)
        self.assertEqual(json.loads(log.splitlines()[-1])["mode"], "plan")
        self.assertNotIn(PROGRAM, log)
        self.assertNotIn("synthetic", log)

    def test_proof_rejects_missing_save_or_missing_preserving_revision(self):
        for behavior in ("missing", "no_revision"):
            status, output, log = self.smoke(behavior)
            self.assertEqual(status, 1)
            self.assertIn("plan_workflow_missing", log)
            self.assertNotIn('"event": "smoke_passed"', log)

    def test_proof_rejects_an_uncited_reply_and_unintended_fact_write(self):
        for behavior, code in (("bad_reply", "plan_workflow_reply_missing"), ("mutation", "plan_workflow_side_effect")):
            status, output, log = self.smoke(behavior)
            self.assertEqual(status, 1)
            self.assertIn(code, log)
            self.assertNotIn('"event": "smoke_passed"', log)
