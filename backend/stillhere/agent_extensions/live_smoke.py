"""USER-RUN bounded real Bedrock proof. No model override or mocked proof path.

Requires owner-applied shared wiring. All cases and SQLite files are disposable.
Only fixed labels/Boolean assertions/counters are printed, never provider text.
"""

import argparse
import importlib.metadata
import json
import logging
import tempfile
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from ..agent import AgentConfig, AgentRuntime
from ..agent.config import load_local_environment
from ..agent.provider import StrandsBedrockProvider
from ..contracts import utc_now
from ..service import CaseService
from .config import ExtensionConfig


class ProofFailure(Exception):
    pass


def require(condition, label):
    if not condition:
        raise ProofFailure(label)


class EvidenceRegistry:
    """Only actual validated runtime invocations count, never prompt/tool prose."""
    def __init__(self, registry):
        self.registry = registry
        self.by_name = registry.by_name
        self.calls = []
        original = self.registry.invoke

        def observed(name, arguments, context):
            output = original(name, arguments, context)
            self.calls.append((name, output))
            return output
        self.registry.invoke = observed

    def strands_tools(self):
        # Bind through this evidence wrapper, so SDK dispatch passes here.
        return self.registry.strands_tools()

    def validate_arguments(self, name, arguments):
        return self.registry.validate_arguments(name, arguments)

    def successful(self, name):
        return [output for tool, output in self.calls if tool == name and "error" not in output
                and output.get("status") in (None, "applied", "already_applied", "prepared")]


def send(service, token, snapshot, kind, payload, event, now):
    request = {"contract_version": "0.1", "case_id": snapshot["case_id"], "event_id": event,
               "expected_case_version": snapshot["case_version"], "occurred_at": now,
               "channel": "dashboard", "type": kind, "payload": payload}
    result = service.execute(token, request)
    require(result["status"] == "applied", "synthetic_fixture_rejected")
    return result["case_snapshot"]


def event_counts(service, case_id):
    with service._connection() as connection:
        return tuple(connection.execute("SELECT count(*) FROM " + table + " WHERE case_id=?", (case_id,)).fetchone()[0]
                     for table in ("events", "simulated_effects"))


def verify_restart_replay(runtime, evidence, service, path, token, request, saved, provider):
    restarted = CaseService(path)
    require(restarted.read_case(token, saved["case_id"]) == saved, "restart_readback_failed")
    counts = event_counts(restarted, saved["case_id"])
    calls = len(evidence.calls)
    invocations = provider.calls
    runtime.service = restarted
    replayed = runtime.handle(token, request)
    require(replayed["status"] == "already_applied", "turn_replay_failed")
    require(replayed["case_snapshot"] == saved, "replay_changed_snapshot")
    require(len(evidence.calls) == calls, "replay_invoked_tools")
    require(provider.calls == invocations, "replay_invoked_provider")
    require(event_counts(restarted, saved["case_id"]) == counts, "replay_created_effects")
    require(restarted.claim_agent_turn(token, saved["case_id"], request["event_id"], 30) is None,
            "replay_reclaimed_saved_turn")


class RealProofProvider:
    def __init__(self, config):
        self.provider = StrandsBedrockProvider(config)
        require(self.provider.model_override is None, "real_bedrock_required")
        self.calls = 0

    def reply(self, *arguments):
        self.calls += 1
        return self.provider.reply(*arguments)


def run_mode(mode, config):
    now = utc_now()
    local = datetime.fromisoformat(now.replace("Z", "+00:00")).astimezone(ZoneInfo("America/Chicago"))
    tomorrow = (local + timedelta(days=1)).date().isoformat()
    later = (local + timedelta(days=7)).date().isoformat()
    with tempfile.TemporaryDirectory(prefix="stillhere-new-tools-live-") as directory:
        path = Path(directory) / "cases.sqlite3"
        service = CaseService(path)
        token = service.create_session()["session_token"]
        snapshot = service.create_case(token, {"contract_version": "0.1", "event_id": "live_create",
                                               "time_zone": "America/Chicago"})["case_snapshot"]
        require(snapshot["household_mode"] == "synthetic", "synthetic_case_required")
        flags = ExtensionConfig(structured_replies=True)
        if mode in ("finance", "outputs", "no-car"):
            cash = {"id": "cash", "type": "cash", "currency": "USD", "balance_cents": 30000,
                    "accessible": True, "as_of": now, "restrictions": [], "reflected_event_ids": []}
            snapshot = send(service, token, snapshot, "finance.update", {"operation": "set_money_source", "record": cash}, "live_cash", now)
        if mode in ("applications", "no-car"):
            from ..agent_extensions.testing import application_arguments
            import time
            for key, value in (("document_issuing_state", "CO"), ("credential_lost", True), ("mobility", "no_car"),
                               ("office_transport_available", False), ("internet_access", True)):
                snapshot = send(service, token, snapshot, "fact.correct", {"fact_key": key, "value": value, "observed_at": now}, "live_"+key, now)
            # Fixture planning is explicit and independent of the required NEW model tools.
            request = {"contract_version": "0.1", "case_id": snapshot["case_id"], "event_id": "live_fixture_plan",
                       "expected_case_version": snapshot["case_version"], "occurred_at": now, "channel": "chat",
                       "type": "conversation.message", "payload": {"message_id": "fixture_plan_user", "text": "Prepare a synthetic plan fixture."}}
            require(service.execute(token, request)["status"] == "applied", "synthetic_fixture_rejected")
            claim = service.claim_agent_turn(token, snapshot["case_id"], request["event_id"], 30)
            prepared = service.revise_agent_plan(token, snapshot["case_id"], request["event_id"], claim["run_id"],
                        {"program_id": "co_state_id_replacement"}, claim["snapshot"]["case_version"], time.monotonic()+30, 48000)
            require(prepared["status"] == "applied", "synthetic_fixture_rejected")
            snapshot = service.finish_agent_turn(token, snapshot["case_id"], request["event_id"], claim["run_id"], "Synthetic fixture plan saved.")
            app_args = application_arguments(snapshot)
        if mode == "finance":
            flags = replace(flags, finance_updates=True, finance_calculation=True, finance_scenarios=True)
            expense = {"operation": "record_expense", "record": {"id": "live_spent", "kind": "expense", "currency": "USD", "source": "user_reported",
                        "money_source_id": "cash", "amount_cents": 1200, "category": "food", "commitment_id": "additional"}}
            scenario = {"scenario": {"id": "live_possible", "label": "Possible synthetic assistance", "receipts": [{"id": "possible", "state": "hypothetical", "amount_cents": 5000,
                         "date": later, "currency": "USD", "restrictions": []}]}, "start_date": tomorrow}
            text = ("Synthetic explicit household report: I spent 1200 cents of cash on additional food. Call update_financial_state with " + json.dumps({"update": expense}) +
                    ". I request this hypothetical scenario: call set_financial_scenario with " + json.dumps(scenario) +
                    ". Call calculate_cash_flow and compare_financial_scenarios with start_date " + tomorrow +
                    ". Call read_financial_summary. Then prepare_structured_reply: report actual cash in cents and the scenario ending projected cents exactly as tools return. Include the word hypothetical and preserve warnings. Use no questions.")
            required = {"update_financial_state", "set_financial_scenario", "calculate_cash_flow", "compare_financial_scenarios", "read_financial_summary", "prepare_structured_reply"}
        elif mode == "applications":
            flags = replace(flags, applications=True)
            text = ("Synthetic household request: call prepare_application with " + json.dumps(app_args) +
                    ". I explicitly report this synthetic application submitted: call update_application with " + json.dumps({"application_id": app_args["application_id"], "stage_change": {"stage": "submitted", "corrects_event_id": None}}) +
                    ". Finish using prepare_structured_reply: include the returned official_url, submitted, user-reported, unknown and no external submission. Do not grant approval or receipt; ask one optional text question about missing requirements.")
            required = {"prepare_application", "update_application", "prepare_structured_reply"}
        elif mode == "outputs":
            flags = replace(flags, finance_calculation=True, dashboard=True)
            descriptors = {"components": [{"id": "live_cash_card", "kind": "finance_overview", "record_ids": ["cash"], "display_order": 0}]}
            text = ("Synthetic household request: call calculate_cash_flow with start_date " + tomorrow +
                    ". Call publish_dashboard_components with " + json.dumps(descriptors) +
                    ". Finish with prepare_structured_reply: include 30000 cents, projected, unknown, saved dashboard and one single_choice question with two unique choices and allow_skip true. No preselected choice.")
            required = {"calculate_cash_flow", "publish_dashboard_components", "prepare_structured_reply"}
        else:
            require(hasattr(service, "seed_agent_extension_smoke_costs"), "domain_boundary_integration_pending")
            snapshot = service.seed_agent_extension_smoke_costs(token, snapshot["case_id"], app_args["action_id"], tomorrow)
            flags = replace(flags, finance_calculation=True, finance_scenarios=True, applications=True, dashboard=True)
            scenario = {"scenario": {"id": "live_no_car", "label": "Hypothetical online path", "alternative_ids": [app_args["action_id"]]}, "start_date": tomorrow}
            text = ("Synthetic no-car journey: office transport is explicitly unavailable; online remains provisional, eligibility and fees unknown. "
                    "Call set_financial_scenario with " + json.dumps(scenario) + "; then compare_financial_scenarios with start_date " + tomorrow +
                    ". The backend supplies explicitly dated unknown costs; inspect incomplete, never treat null as zero. Call prepare_application with " + json.dumps(app_args) +
                    ". Publish finance_overview cash and aid_tracker application_synthetic descriptors, then prepare_structured_reply with one optional question. "
                    "Mention online, office, unknown, incomplete and hypothetical and the application's exact official_url. Never submit, grant consent or complete an action.")
            required = {"set_financial_scenario", "compare_financial_scenarios", "prepare_application", "publish_dashboard_components", "prepare_structured_reply"}
        config = replace(config, extensions=flags, timeout_seconds=60, max_turns=10, max_tool_calls=12,
                         max_output_tokens=1024, max_total_tokens=120000, max_context_chars=48000)
        # This path constructs the real provider; no injection or scripted model exists.
        provider = RealProofProvider(config)
        runtime = AgentRuntime(service, config, provider=provider)
        evidence = EvidenceRegistry(runtime.registry)
        runtime.registry = evidence
        before_catalog = service.read_program_catalog()
        baseline_money = snapshot["finance"]["ledger"]
        original_facts = snapshot["facts"]
        request = {"contract_version": "0.1", "case_id": snapshot["case_id"], "event_id": "live_new_tools",
                   "expected_case_version": snapshot["case_version"], "occurred_at": utc_now(), "channel": "chat",
                   "type": "conversation.message", "payload": {"message_id": "live_new_tools_user", "text": text}}
        require(len(text) <= 4000, "smoke_prompt_limit")
        result = runtime.handle(token, request)
        saved = result["case_snapshot"]
        require(saved is not None and saved["conversation"]["turns"][-1]["state"] == "complete", "live_turn_incomplete")
        for name in required:
            require(bool(evidence.successful(name)), "mandatory_new_tool_missing")
        for _, output in evidence.calls:
            require("error" not in output and output.get("status") not in ("rejected", "conflict", "unavailable", "needs_clarification"), "tool_operation_failed")
        reply = saved["conversation"]["turns"][-1]
        grounded = reply["text"].lower()
        if mode == "finance":
            require(saved["finance"]["ledger"]["money_sources"][0]["balance_cents"] == 28800, "actual_cash_not_persisted")
            require(len(saved["finance"]["ledger"]["actual_events"]) == 1, "actual_event_not_persisted")
            require(saved["finance"]["baseline"]["ending_projected_position_cents"] == 28800, "baseline_not_persisted")
            require(saved["finance"]["scenarios"][0]["ending_projected_position_cents"] == 33800, "scenario_not_persisted")
            require(all(word in grounded for word in ("28800", "33800", "hypothetical")), "reply_not_grounded")
        elif mode in ("applications", "no-car"):
            application = saved["applications"][0]
            require(application["id"] == app_args["application_id"], "application_not_persisted")
            require(application["official_url"].lower() in grounded, "reply_source_missing")
            require(application["agency_outcome"] is None and saved["finance"]["ledger"]["money_sources"] == baseline_money["money_sources"], "invented_approval_or_money")
            if mode == "applications":
                require(application["stage_report"]["stage"] == "submitted", "stage_report_not_persisted")
                require(all(word in grounded for word in ("submitted", "user-reported", "unknown", "no external submission")), "reply_not_grounded")
            else:
                require(saved["finance"]["scenarios"][0]["state"] == "incomplete", "unknown_cost_not_preserved")
                require(saved["finance"]["scenarios"][0]["ending_projected_position_cents"] is None, "unknown_cost_became_zero")
                require(all(word in grounded for word in ("online", "office", "unknown", "incomplete", "hypothetical")), "reply_not_grounded")
        if mode in ("outputs", "no-car"):
            require(bool(saved["components"]) and bool(saved.get("dashboard_output")), "dashboard_not_persisted")
            require(bool(reply.get("questions")), "question_not_persisted")
            if mode == "outputs":
                require(any(item["id"] == "live_cash_card" and item["kind"] == "finance_overview" and item["record_ids"] == ["cash"] for item in saved["components"]), "dashboard_reference_missing")
                require(all(word in grounded for word in ("30000", "projected", "unknown", "saved dashboard")), "reply_not_grounded")
            else:
                require({"finance_overview", "aid_tracker"} <= {item["kind"] for item in saved["components"]}, "dashboard_reference_missing")
                require(any(app_args["application_id"] in item["record_ids"] for item in saved["components"] if item["kind"] == "aid_tracker"), "dashboard_reference_missing")
        require(service.read_program_catalog() == before_catalog, "policy_changed")
        require(saved["facts"] == original_facts, "unrequested_fact_change")
        require(saved["shared_location"] is None and saved["check_in"]["enrolled"] is False and not saved["follow_ups"], "consent_or_outreach_changed")
        verify_restart_replay(runtime, evidence, service, path, token, request, saved, provider)
        return len(evidence.calls)


def main(argv=None):
    parser = argparse.ArgumentParser(description="User-run genuine Bedrock new-tool smoke; synthetic disposable cases only")
    parser.add_argument("--mode", choices=("finance", "applications", "outputs", "no-car", "all"), required=True)
    parser.add_argument("--run-live", action="store_true", help="Required acknowledgment of real bounded Bedrock inference")
    parser.add_argument("--env-file", help="User-run explicit configuration loading only; never prints values")
    args = parser.parse_args(argv)
    if not args.run_live:
        print(json.dumps({"proof_mode": args.mode, "live_status": "pending", "code": "user_run_live_required"}, sort_keys=True))
        return 2
    # Fail before even loading private config when shared integration is missing.
    if not hasattr(CaseService, "execute_agent_extension_command") or "extensions" not in AgentConfig.__dataclass_fields__:
        print(json.dumps({"proof_mode": args.mode, "live_status": "pending", "code": "shared_wiring_pending"}, sort_keys=True))
        return 2
    old_logging = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        require(importlib.metadata.version("strands-agents") == "1.59.0", "sdk_version_mismatch")
        if args.env_file:
            load_local_environment(args.env_file)
        config = AgentConfig.from_environment()
        require(not config.missing_provider_settings, "provider_configuration_missing")
        # Disable other adapters regardless of process flags; proof uses only new ones.
        config = replace(config, enable_intake=False, enable_incidents=False, enable_resources=False,
                         enable_rules=False, enable_official_sources=False, enable_rule_review=False,
                         enable_planner=False, enable_plan_revision=False, enable_tasks=False)
        modes = ("finance", "applications", "outputs", "no-car") if args.mode == "all" else (args.mode,)
        for mode in modes:
            calls = run_mode(mode, config)
            print(json.dumps({"proof_mode": mode, "live_status": "passed", "code": "new_tool_proof_passed",
                              "mandatory_assertions": True, "restart_readback": True,
                              "replay_without_effects": True, "tool_calls": calls}, sort_keys=True))
        return 0
    except ProofFailure as error:
        print(json.dumps({"proof_mode": args.mode, "live_status": "pending", "code": str(error)}, sort_keys=True))
        return 1
    except Exception:
        # Never print/log provider exception messages, configuration, IDs or text.
        print(json.dumps({"proof_mode": args.mode, "live_status": "pending", "code": "live_proof_unavailable"}, sort_keys=True))
        return 1
    finally:
        logging.disable(old_logging)


if __name__ == "__main__":
    raise SystemExit(main())
