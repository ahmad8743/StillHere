"""Actual pinned Strands loop and outgoing Bedrock schemas; no credentials/network."""

import importlib.metadata
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from strands.models.model import Model

from backend.stillhere.agent import AgentConfig, AgentRuntime
from backend.stillhere.agent.provider import StrandsBedrockProvider
from backend.stillhere.agent_extensions import ExtensionConfig
from backend.stillhere.agent_extensions.registry import TOOLS
from backend.stillhere.agent_extensions.testing import (NOW, application_arguments, command, create_case,
                                                       run_proposal_test, seed_finance, seed_plan)
from backend.stillhere.service import CaseService


class ScriptedModel(Model):
    def __init__(self, steps):
        self.steps = iter(steps)
        self.calls = 0
        self.messages = []
        self.specs = []
        self.tool_results = {}

    def update_config(self, **kwargs): pass
    def get_config(self): return {"model_id": "scripted-extension-fixture"}

    async def structured_output(self, *args, **kwargs):
        raise AssertionError("No auxiliary model calls permitted.")
        yield

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
        self.calls += 1
        self.messages = messages
        self.specs = tool_specs
        for message in messages:
            for content in message["content"]:
                if "toolResult" in content:
                    output = content["toolResult"]
                    self.tool_results[output["toolUseId"]] = output
        step = next(self.steps)
        if isinstance(step, Exception): raise step
        yield {"messageStart": {"role": "assistant"}}
        if isinstance(step, dict):
            yield {"contentBlockStart": {"start": {"toolUse": {"toolUseId": "extension_"+str(self.calls), "name": step["name"]}}}}
            yield {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(step["input"])}}}}
            stop = "tool_use"
        else:
            yield {"contentBlockDelta": {"delta": {"text": step}}}
            stop = "end_turn"
        yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": stop}}
        yield {"metadata": {"usage": {"inputTokens": 20, "outputTokens": 10, "totalTokens": 30}}}


ALL_FLAGS = ExtensionConfig(**{key: True for key in vars(ExtensionConfig())})


class ExtensionSDKTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(importlib.metadata.version("strands-agents"), "1.59.0")
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "cases.sqlite3"
        self.service = CaseService(self.path, clock=lambda: NOW)
        self.token, self.snapshot = create_case(self.service)

    def runtime(self, steps, flags=ALL_FLAGS):
        config = AgentConfig(extensions=flags, max_turns=24, max_tool_calls=32, max_total_tokens=24000)
        model = ScriptedModel(steps)
        runtime = AgentRuntime(self.service, config, StrandsBedrockProvider(config, model))
        request = command(self.snapshot, "conversation.message", {"message_id": "sdk_user", "text": "Synthetic explicit reports and hypothetical comparison."}, "sdk")
        return runtime, model, request

    def test_proposed_actual_outgoing_converse_schemas_for_every_new_tool(self):
        if run_proposal_test(self): return
        import botocore
        from botocore.loaders import Loader
        from botocore.model import ServiceModel
        from botocore.validate import validate_parameters
        session = MagicMock()
        client = session.client.return_value
        client.converse.return_value = {"output": {"message": {"role": "assistant", "content": [{"text": "Unknown inputs retained."}]}},
            "stopReason": "end_turn", "usage": {"inputTokens": 20, "outputTokens": 10, "totalTokens": 30}, "metrics": {"latencyMs": 1}}
        config = AgentConfig(model_id="synthetic-profile", region="us-east-2", extensions=ALL_FLAGS)
        request = command(self.snapshot, "conversation.message", {"message_id": "outgoing", "text": "Read-only synthetic provider envelope check."})
        with patch("strands.models.bedrock.boto3.Session", return_value=session):
            result = AgentRuntime(self.service, config).handle(self.token, request)
        self.assertEqual(result["case_snapshot"]["conversation"]["turns"][-1]["state"], "complete")
        client.converse.assert_called_once()
        outgoing = client.converse.call_args.kwargs
        specs = {item["toolSpec"]["name"]: item["toolSpec"]["inputSchema"]["json"] for item in outgoing["toolConfig"]["tools"]}
        self.assertTrue({item.name for item in TOOLS} <= specs.keys())
        for item in TOOLS:
            schema = specs[item.name]
            self.assertEqual(schema["type"], "object")
            self.assertFalse(schema["additionalProperties"])
            for keyword in ("anyOf", "oneOf", "allOf", "$ref"):
                self.assertNotIn(keyword, schema)
            self.assertNotIn("$ref", json.dumps(schema))
            for name in ("token", "case_id", "role", "run_id", "consent", "agency_receipts"):
                self.assertNotIn(name, schema.get("properties", {}))
        self.assertIn("oneOf", specs["update_financial_state"]["properties"]["update"])
        self.assertNotIn(self.token, json.dumps(outgoing))
        self.assertEqual(outgoing["inferenceConfig"], {"maxTokens": 1024})
        loader = Loader(extra_search_paths=[str(Path(botocore.__file__).parent / "data")], include_default_search_paths=False)
        service = ServiceModel(loader.load_service_model("bedrock-runtime", "service-2"))
        validate_parameters(outgoing, service.operation_model("Converse").input_shape)

    def test_proposed_every_tool_called_in_real_sdk_saved_results_reply_restart_replay(self):
        if run_proposal_test(self): return
        self.snapshot = seed_finance(self.service, self.token, self.snapshot)
        self.snapshot = seed_plan(self.service, self.token, self.snapshot)
        enroll = command(self.snapshot, "check_in.enroll", {"consent": True, "follow_up_consent": True,
            "due_at": "2026-10-12T06:00:00Z", "time_zone": "America/Chicago", "grace_minutes": 5, "channel": "in_app"}, "enroll")
        self.snapshot = self.service.execute(self.token, enroll)["case_snapshot"]
        occurrence = self.snapshot["check_in"]["current_occurrence_id"]
        inputs = {
            "read_financial_summary": {}, "update_financial_state": {"update": {"operation": "record_expense", "record": {
                "id": "spent", "kind": "expense", "amount_cents": 1200, "currency": "USD", "source": "user_reported", "money_source_id": "cash", "category": "food", "commitment_id": "additional"}}},
            "calculate_cash_flow": {"start_date": "2026-10-12"},
            "set_financial_scenario": {"scenario": {"id": "possible", "label": "Possible aid", "receipts": [{"id": "conditional", "state": "hypothetical", "amount_cents": 5000, "currency": "USD", "restrictions": [], "date": "2026-10-18"}]}, "start_date": "2026-10-12"},
            "compare_financial_scenarios": {"start_date": "2026-10-12"},
            "prepare_application": application_arguments(self.snapshot),
            "update_application": {"application_id": "application_synthetic", "stage_change": {"stage": "submitted", "corrects_event_id": None}},
            "publish_dashboard_components": {"components": [{"id": "cash_card", "kind": "finance_overview", "record_ids": ["cash"], "display_order": 0}, {"id": "app_card", "kind": "aid_tracker", "record_ids": ["application_synthetic"], "display_order": 1}]},
            "read_check_in_status": {}, "record_check_in_reply": {"occurrence_id": occurrence, "reply": "okay_for_now"},
            "pause_check_ins": {"intent": "pause"}, "clear_shared_location": {}, "request_help": {"message": "Synthetic explicit help request"},
            "prepare_structured_reply": {"text": "Saved 28800 cents actual cash; 33800 cents is a hypothetical projection. Online remains provisional and fees unknown. Application submitted is user-reported; no external submission or welfare contact occurred.",
                "questions": [{"id": "next", "prompt": "What next?", "kind": "single_choice", "choices": [{"id": "finance", "label": "Finance"}, {"id": "plan", "label": "Plan"}], "allow_skip": True}]},
        }
        runtime, model, request = self.runtime([{"name": item.name, "input": inputs[item.name]} for item in TOOLS] + ["Structured reply prepared."])
        request["payload"]["help_request"] = {**inputs["request_help"], "consent": True}
        result = runtime.handle(self.token, request)
        saved = result["case_snapshot"]
        self.assertEqual(saved["conversation"]["turns"][-1]["state"], "complete", saved["conversation"])
        self.assertEqual(saved["conversation"]["turns"][-1]["questions"][0]["id"], "next")
        results = list(model.tool_results.values())
        self.assertEqual(len(results), len(TOOLS))
        for output in results:
            self.assertEqual(output["status"], "success", output)
            self.assertNotIn('"error"', json.dumps(output))
            self.assertNotIn('"status": "rejected"', json.dumps(output))
        self.assertEqual(saved["finance"]["ledger"]["money_sources"][0]["balance_cents"], 28800)
        self.assertEqual(saved["finance"]["scenarios"][0]["ending_projected_position_cents"], 33800)
        self.assertEqual(saved["applications"][0]["stage_report"]["stage"], "submitted")
        self.assertEqual(len(saved["components"]), 2)
        self.assertEqual(saved["check_in"]["status"], "paused")
        self.assertEqual(len(saved["follow_ups"]), 1)
        self.assertTrue(all(item["simulation"] for item in saved["follow_ups"]))
        self.assertNotIn(self.token, json.dumps(model.messages))
        restarted = CaseService(self.path, clock=lambda: NOW)
        self.assertEqual(restarted.read_case(self.token, saved["case_id"]), saved)
        calls = model.calls
        runtime.service = restarted
        self.assertEqual(runtime.handle(self.token, request)["case_snapshot"], saved)
        self.assertEqual(model.calls, calls)

    def test_proposed_raw_sdk_arguments_reject_extras_and_union_mixing(self):
        if run_proposal_test(self): return
        steps = [{"name": item.name, "input": {"case_id": "foreign", "role": "operator", "consent": True}} for item in TOOLS]
        steps += [{"name": "update_financial_state", "input": {"update": {"operation": "set_balance", "money_source_id": "cash", "balance_cents": 0, "as_of": NOW, "reflected_event_ids": [], "record": {}}}}, "Invalid inputs rejected."]
        runtime, model, request = self.runtime(steps)
        result = runtime.handle(self.token, request)
        saved = result["case_snapshot"]
        self.assertEqual(saved["conversation"]["turns"][-1]["state"], "complete")
        self.assertIn("Invalid tool arguments", str(model.messages))
        for key in ("facts", "applications", "components", "shared_location", "check_in", "follow_ups"):
            self.assertEqual(saved[key], self.snapshot[key])
        self.assertEqual(saved["finance"]["ledger"], self.snapshot["finance"]["ledger"])

    def test_proposed_provider_failure_after_accepted_write_is_saved_and_not_replayed(self):
        if run_proposal_test(self): return
        self.snapshot = seed_finance(self.service, self.token, self.snapshot)
        runtime, model, request = self.runtime([
            {"name": "update_financial_state", "input": {"update": {"operation": "set_balance", "money_source_id": "cash", "balance_cents": 25000, "as_of": NOW, "reflected_event_ids": []}}},
            RuntimeError("synthetic private provider detail")])
        result = runtime.handle(self.token, request)
        saved = result["case_snapshot"]
        self.assertEqual(saved["finance"]["ledger"]["money_sources"][0]["balance_cents"], 25000)
        self.assertEqual(saved["conversation"]["turns"][-1]["state"], "failed")
        self.assertNotIn("synthetic private provider detail", str(result))
        self.assertEqual(runtime.handle(self.token, request)["case_snapshot"], saved)
        self.assertEqual(model.calls, 2)

    def test_proposed_no_car_sdk_journey_uses_domain_boundary_without_zeroing_unknown_cost(self):
        if run_proposal_test(self, boundary=True): return
        self.snapshot = seed_finance(self.service, self.token, self.snapshot)
        self.snapshot = seed_plan(self.service, self.token, self.snapshot)
        args = application_arguments(self.snapshot)
        self.snapshot = self.service.seed_agent_extension_smoke_costs(self.token, self.snapshot["case_id"], args["action_id"], "2026-10-12")
        steps = [
            {"name": "set_financial_scenario", "input": {"scenario": {"id": "online", "label": "Hypothetical online", "alternative_ids": [args["action_id"]]}, "start_date": "2026-10-12"}},
            {"name": "compare_financial_scenarios", "input": {"start_date": "2026-10-12"}},
            {"name": "prepare_application", "input": args},
            {"name": "publish_dashboard_components", "input": {"components": [{"id": "app", "kind": "aid_tracker", "record_ids": [args["application_id"]], "display_order": 0}]}},
            {"name": "prepare_structured_reply", "input": {"text": "Online provisional, office transport unavailable. Costs unknown; hypothetical comparison incomplete.", "questions": []}},
            "Reply prepared.",
        ]
        runtime, model, request = self.runtime(steps)
        result = runtime.handle(self.token, request)
        saved = result["case_snapshot"]
        self.assertEqual(saved["conversation"]["turns"][-1]["state"], "complete")
        self.assertEqual(saved["finance"]["scenarios"][0]["state"], "incomplete")
        self.assertIsNone(saved["finance"]["scenarios"][0]["ending_projected_position_cents"])
        self.assertIsNone(saved["finance"]["scenarios"][0]["scenario_assumptions"]["action_costs"][0]["amount_cents"])
        self.assertEqual(len(saved["applications"]), 1)
        self.assertEqual(len(saved["components"]), 1)
        self.assertEqual(saved["facts"], self.snapshot["facts"])
        self.assertEqual(runtime.handle(self.token, request)["case_snapshot"], saved)
        self.assertEqual(model.calls, 6)

    def test_proposed_structured_output_remains_default_off_with_ordinary_text_compatible(self):
        if run_proposal_test(self): return
        class Provider:
            def reply(self, *args): return {"text": "Structured without enabling."}
        config = AgentConfig()
        request = command(self.snapshot, "conversation.message", {"message_id": "off", "text": "Synthetic plain request."}, "off")
        result = AgentRuntime(self.service, config, Provider()).handle(self.token, request)
        self.assertEqual(result["case_snapshot"]["conversation"]["turns"][-1]["issue"]["code"], "invalid_agent_reply")
        self.assertNotIn("questions", result["case_snapshot"]["conversation"]["turns"][-1])
        self.snapshot = result["case_snapshot"]
        runtime, model, request = self.runtime(["**Ordinary text remains compatible.**"], flags=ExtensionConfig())
        result = runtime.handle(self.token, request)
        self.assertEqual(result["case_snapshot"]["conversation"]["turns"][-1]["state"], "complete")
        self.assertEqual(result["case_snapshot"]["conversation"]["turns"][-1]["text"], "**Ordinary text remains compatible.**")


if __name__ == "__main__":
    unittest.main()
