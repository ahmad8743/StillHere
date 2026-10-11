"""Real pinned SDK loop, scripted model transport; requires no AWS credentials."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.stillhere.agent import AgentConfig, AgentRuntime
from backend.stillhere.agent.provider import StrandsBedrockProvider
from backend.stillhere.agent.diagnostics import SafeDiagnostics
from backend.stillhere.agent.registry import CASE_TOOLS, INTAKE_TOOL, ToolRegistry
from backend.stillhere.service import CaseService

SDK_AVAILABLE = importlib.util.find_spec("strands") is not None
if SDK_AVAILABLE:
    from strands.models.model import Model

    class ScriptedModel(Model):
        def __init__(self, steps):
            self.steps = iter(steps)
            self.calls = 0
            self.specs = []
            self.messages = []

        def update_config(self, **kwargs):
            pass

        def get_config(self):
            return {"model_id": "scripted-test-model"}

        async def structured_output(self, *args, **kwargs):
            raise AssertionError("No auxiliary model calls are part of this slice.")
            yield

        async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
            self.calls += 1
            self.specs = tool_specs
            self.messages = messages
            step = next(self.steps)
            if isinstance(step, Exception):
                raise step
            yield {"messageStart": {"role": "assistant"}}
            if isinstance(step, dict):
                yield {"contentBlockStart": {"start": {"toolUse": {"toolUseId": "sdk_generated_" + str(self.calls), "name": step["name"]}}}}
                yield {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(step["input"])}}}}
                stop = "tool_use"
            else:
                yield {"contentBlockDelta": {"delta": {"text": step}}}
                stop = "end_turn"
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": stop}}
            yield {"metadata": {"usage": {"inputTokens": 20, "outputTokens": 10, "totalTokens": 30}}}


@unittest.skipUnless(SDK_AVAILABLE, "Install backend/requirements-agent.txt for real SDK integration checks")
class StrandsIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.service = CaseService(Path(self.directory.name) / "cases.sqlite3")
        self.token = self.service.create_session()["session_token"]
        self.case = self.service.create_case(self.token, {
            "contract_version": "0.1", "event_id": "create", "time_zone": "America/Chicago",
        })["case_snapshot"]

    def command(self):
        return {"contract_version": "0.1", "case_id": self.case["case_id"], "event_id": "chat_sdk",
                "expected_case_version": 1, "occurred_at": "2026-10-10T15:00:00Z", "channel": "chat",
                "type": "conversation.message", "payload": {"message_id": "user_sdk", "text": "I have no car."}}

    def fact_step(self, **extra):
        return {"name": "correct_fact", "input": {"fact_key": "mobility", "value": "no_car", "observed_at": "2026-10-10T15:00:00Z", **extra}}

    def knowledge_runtime(self, steps, fail_source=False):
        from backend.stillhere.knowledge.official import OfficialSourceFetcher, OfficialSourceFailure
        class Transport:
            calls = 0
            def get_text(inner, source, deadline):
                inner.calls += 1
                if fail_source:
                    raise OfficialSourceFailure("source_http_error")
                return "Synthetic public evidence about email access and renewal documents; this is a scripted fixture.", False
        case = self.service.read_case(self.token,self.case["case_id"])
        correction = {"contract_version":"0.1", "case_id":case["case_id"], "event_id":"sdk_issuer", "expected_case_version":case["case_version"],
                      "occurred_at":"2026-10-11T04:00:00Z", "channel":"chat", "type":"fact.correct",
                      "payload":{"fact_key":"document_issuing_state", "value":"CO", "observed_at":"2026-10-11T04:00:00Z"}}
        self.service.execute(self.token,correction)
        model = ScriptedModel(steps)
        config = AgentConfig(enable_rule_review=True)
        transport = Transport()
        runtime = AgentRuntime(self.service,config,StrandsBedrockProvider(config,model),official_fetcher=OfficialSourceFetcher(transport))
        command = self.command()
        command["expected_case_version"] = self.service.read_case(self.token,self.case["case_id"])["case_version"]
        return runtime,model,transport,command

    def test_sdk_official_fetch_candidate_discrepancy_and_saved_reply_are_public_scoped_and_unpublished(self):
        from backend.stillhere.knowledge.review import ManualReviewAuthority
        args = {"program_id":"co_state_id_replacement", "base_version":"2026-10-10.1", "source_id":"source_rule_co_renewal"}
        runtime,model,transport,command = self.knowledge_runtime([
            {"name":"fetch_official_source", "input":{"source_id":args["source_id"]}},
            {"name":"propose_rule_candidate", "input":{**args,"requirement_keys":["email_access"],"relationship":"all_of","evidence_start":0,"evidence_end":50}},
            {"name":"report_rule_discrepancy", "input":{**args,"reason":"requirements_changed","evidence_start":0,"evidence_end":50}},
            "Synthetic public evidence is queued for manual review; policy remains unpublished."])
        before = self.service.read_case(self.token,self.case["case_id"])
        catalog = self.service.read_program_catalog()
        result = runtime.handle(self.token,command)
        after = result["case_snapshot"]
        self.assertEqual(after["conversation"]["turns"][-1]["state"],"complete")
        self.assertEqual(transport.calls,1)
        queued = self.service.read_review_queue(ManualReviewAuthority("synthetic_reviewer"))
        self.assertEqual(len(queued),2)
        self.assertEqual({item["kind"] for item in queued},{"candidate","discrepancy"})
        self.assertTrue(all(item["review_state"]=="pending" for item in queued))
        self.assertEqual(self.service.read_program_catalog(),catalog)
        for key in ("facts","evidence","resources","plan","applications","sources","shared_location"):
            self.assertEqual(after[key],before[key])
        self.assertNotIn(self.token,json.dumps(model.messages))
        specs = {spec["name"]:spec["inputSchema"]["json"] for spec in model.specs}
        self.assertEqual(set(specs["fetch_official_source"]["properties"]),{"source_id"})
        self.assertNotIn("summary",specs["propose_rule_candidate"]["properties"])
        self.assertNotIn("publish_rules",specs)
        self.assertEqual(runtime.handle(self.token,command)["case_snapshot"]["case_version"],after["case_version"])
        self.assertEqual(transport.calls,1)

    def test_sdk_failed_source_reports_pending_discrepancy_without_publishing_cached_text(self):
        from backend.stillhere.knowledge.review import ManualReviewAuthority
        args = {"program_id":"co_state_id_replacement","base_version":"2026-10-10.1","source_id":"source_rule_co_renewal","reason":"source_unavailable"}
        runtime,model,transport,command = self.knowledge_runtime([
            {"name":"fetch_official_source","input":{"source_id":args["source_id"]}},
            {"name":"report_rule_discrepancy","input":args},
            "Synthetic failed source reported; retained seeded excerpt is unreviewed."],fail_source=True)
        result = runtime.handle(self.token,command)
        self.assertEqual(result["case_snapshot"]["conversation"]["turns"][-1]["state"],"complete")
        queued = self.service.read_review_queue(ManualReviewAuthority("synthetic_reviewer"))
        self.assertEqual(len(queued),1)
        self.assertEqual(queued[0]["source_state"],"unavailable")
        self.assertEqual(queued[0]["receipt"]["data_mode"],"seeded")
        self.assertEqual(queued[0]["review_state"],"pending")
        self.assertIsNone(queued[0]["evidence_excerpt"])

    def test_sdk_raw_source_arguments_cannot_select_url_or_household_authority(self):
        runtime,model,transport,command = self.knowledge_runtime([
            {"name":"fetch_official_source","input":{"source_id":"source_rule_co_renewal","url":"https://example.invalid/","role":"operator"}},
            {"name":"fetch_official_source","input":{"source_id":"source_rule_co_renewal"}},
            "Synthetic safe public source retrieved after invalid authority/URL were rejected."])
        result = runtime.handle(self.token,command)
        self.assertEqual(result["case_snapshot"]["conversation"]["turns"][-1]["state"],"complete")
        self.assertEqual(transport.calls,1)
        self.assertIn("Invalid tool arguments; use the exact registered schema.",json.dumps(model.messages))

    def runtime(self, steps, config=None, registry=None):
        model = ScriptedModel(steps)
        config = config or AgentConfig()
        return AgentRuntime(self.service, config, StrandsBedrockProvider(config, model), registry), model

    def test_real_sdk_reads_writes_and_saves_reply_without_credentials(self):
        runtime, model = self.runtime([{"name": "read_case", "input": {}}, self.fact_step(), "Your reported mobility is saved."])
        result = runtime.handle(self.token, self.command())
        turn = result["case_snapshot"]["conversation"]["turns"][-1]
        self.assertEqual(turn["state"], "complete", turn)
        self.assertEqual(turn["text"], "Your reported mobility is saved.")
        self.assertEqual(result["case_snapshot"]["facts"]["mobility"]["value"], "no_car")
        self.assertEqual([s["name"] for s in model.specs], ["read_case", "correct_fact"])
        self.assertNotIn(self.token, str(model.messages))
        self.assertEqual(runtime.handle(self.token, self.command())["status"], "already_applied")
        self.assertEqual(model.calls, 3)

    def test_sdk_raw_schema_hook_rejects_model_authority_before_filtering(self):
        runtime, model = self.runtime([self.fact_step(case_id="model_chosen_other_case"), "Please provide a valid correction."])
        result = runtime.handle(self.token, self.command())
        self.assertEqual(result["case_snapshot"]["facts"], {})
        self.assertEqual(result["case_snapshot"]["conversation"]["turns"][-1]["state"], "complete")
        self.assertIn("Invalid tool arguments", str(model.messages))

    def test_sdk_intake_adapter_uses_the_same_command_path(self):
        registry = ToolRegistry(CASE_TOOLS + (INTAKE_TOOL,))
        runtime, _ = self.runtime([{"name": "submit_intake", "input": {"selections": {"needs": ["shelter"]}}}, "Shelter need reported."], registry=registry)
        result = runtime.handle(self.token, self.command())
        self.assertEqual(result["case_snapshot"]["conversation"]["turns"][-1]["state"], "complete")
        self.assertEqual(result["case_snapshot"]["needs"][0]["state"], "unknown")

    def test_sdk_incident_tool_uses_case_geography_and_saves_attributed_results(self):
        from tests.test_incidents import GEO, NOW, FixtureTransport
        from backend.stillhere.incidents import IncidentFacade
        self.case = self.service.create_case(self.token, {
            "contract_version": "0.1", "event_id": "create_incident", "time_zone": "America/Denver",
            "intake": {"current_location": GEO}})["case_snapshot"]
        model = ScriptedModel([
            {"name": "get_incident_context", "input": {"location_scope": "current", "latitude": 0}},
            {"name": "get_incident_context", "input": {"location_scope": "current"}},
            "Official context is saved; declaration flags do not establish household eligibility."])
        config = AgentConfig(enable_incidents=True)
        transport = FixtureTransport()
        self.service.clock = lambda: NOW
        runtime = AgentRuntime(self.service, config, StrandsBedrockProvider(config, model),
                               incident_facade=IncidentFacade(transport, clock=lambda: NOW))
        result = runtime.handle(self.token, self.command())
        self.assertEqual(result["case_snapshot"]["conversation"]["turns"][-1]["state"], "complete")
        self.assertEqual(result["case_snapshot"]["incident_context"]["current"]["state"], "available")
        self.assertEqual(len(transport.calls), 3)
        self.assertIn("Invalid tool arguments", str(model.messages))
        self.assertNotIn(self.token, str(model.messages))
        self.assertIn("get_incident_context", [spec["name"] for spec in model.specs])

    def test_sdk_resource_tool_validates_scope_saves_seeded_referrals_and_replays(self):
        from tests.test_resources import GEO, NOW
        self.service.clock = lambda: NOW
        self.case = self.service.create_case(self.token, {
            "contract_version": "0.1", "event_id": "create_resources", "time_zone": "America/Denver",
            "intake": {"current_location": GEO, "needs": ["shelter", "transport"]}})["case_snapshot"]
        model = ScriptedModel([
            {"name": "find_resources", "input": {"location_scope": "current", "case_id": "model_selected"}},
            {"name": "find_resources", "input": {"location_scope": "current"}},
            "Reviewed seeded referrals are saved; contact providers to confirm availability."])
        config = AgentConfig(enable_resources=True)
        runtime = AgentRuntime(self.service, config, StrandsBedrockProvider(config, model))
        result = runtime.handle(self.token, self.command())
        snapshot = result["case_snapshot"]
        self.assertEqual(snapshot["conversation"]["turns"][-1]["state"], "complete")
        self.assertEqual(len(snapshot["resources"]["items"]), 2)
        self.assertEqual(len(snapshot["sources"]), 2)
        self.assertTrue(all(item["availability"]["state"] == "unknown" for item in snapshot["resources"]["items"]))
        self.assertIn("Invalid tool arguments", str(model.messages))
        self.assertNotIn(self.token, str(model.messages))
        spec = next(spec for spec in model.specs if spec["name"] == "find_resources")
        self.assertEqual(spec["inputSchema"]["json"]["required"], ["location_scope"])
        replay = runtime.handle(self.token, self.command())
        self.assertEqual(replay["case_snapshot"]["case_version"], snapshot["case_version"])
        self.assertEqual(model.calls, 3)

    def test_sdk_rule_tool_validates_inputs_and_keeps_domain_state_unchanged(self):
        from tests.test_program_rules import NOW, PROGRAM
        self.service.clock = lambda: NOW
        self.service.execute(self.token, {"contract_version":"0.1", "case_id":self.case["case_id"], "event_id":"issuer",
            "expected_case_version":1, "occurred_at":NOW, "channel":"dashboard", "type":"fact.correct",
            "payload":{"fact_key":"document_issuing_state", "value":"CO", "observed_at":NOW}})
        self.case = self.service.read_case(self.token,self.case["case_id"])
        model = ScriptedModel([
            {"name":"retrieve_program_rules", "input":{"program_id":PROGRAM,"issuing_state":"CO"}},
            {"name":"retrieve_program_rules", "input":{"program_id":PROGRAM}},
            "Reviewed partial online/office alternatives are available; prerequisites remain unknown."])
        config = AgentConfig(enable_rules=True)
        runtime = AgentRuntime(self.service,config,StrandsBedrockProvider(config,model))
        command = self.command(); command["expected_case_version"]=self.case["case_version"]
        result = runtime.handle(self.token,command); case=result["case_snapshot"]
        self.assertEqual(case["conversation"]["turns"][-1]["state"],"complete")
        for key in ("facts","resources","plan","evidence","sources","applications","check_in","shared_location"):
            self.assertEqual(case[key],self.case[key])
        self.assertIn("Invalid tool arguments",str(model.messages))
        self.assertIn("co_id_online_renewal",str(model.messages))
        self.assertNotIn(self.token,str(model.messages))
        spec=next(s for s in model.specs if s["name"]=="retrieve_program_rules")
        self.assertEqual(spec["inputSchema"]["json"]["required"],["program_id"])
        self.assertEqual(runtime.handle(self.token,command)["case_snapshot"]["case_version"],case["case_version"])
        self.assertEqual(model.calls,3)

    def test_sdk_rule_tool_preserves_unknown_issuer_despite_current_colorado_location(self):
        from tests.test_program_rules import PROGRAM
        self.case = self.service.create_case(self.token,{"contract_version":"0.1","event_id":"unknown_issuer_case",
                    "time_zone":"America/Denver","intake":{"current_location":{"place":"Synthetic Denver","state":"CO"}}})["case_snapshot"]
        runtime, model = self.runtime([{"name":"retrieve_program_rules","input":{"program_id":PROGRAM}},
                                      "Please report the document's issuing state."],config=AgentConfig(enable_rules=True))
        result=runtime.handle(self.token,self.command())
        self.assertEqual(result["case_snapshot"]["conversation"]["turns"][-1]["state"],"complete")
        self.assertIn("rule_issuing_jurisdiction_unknown",str(model.messages))
        self.assertNotIn("co_id_online_renewal",str(model.messages))
        self.assertNotIn("document_issuing_state",result["case_snapshot"]["facts"])

    def test_sdk_failure_after_tool_keeps_the_saved_fact(self):
        runtime, _ = self.runtime([self.fact_step(), RuntimeError("private provider error")])
        result = runtime.handle(self.token, self.command())
        self.assertEqual(result["case_snapshot"]["facts"]["mobility"]["value"], "no_car")
        self.assertEqual(result["case_snapshot"]["conversation"]["turns"][-1]["state"], "failed")
        self.assertNotIn("private provider error", str(result))

    def test_sdk_fresh_national_source_returns_live_guidance_and_replays_without_refetch(self):
        from backend.stillhere.knowledge.official import OfficialSourceFetcher
        from tests.test_live_fetch_example import FixtureTransport, SOURCE_ID, QUOTE, URL
        transport = FixtureTransport()
        model = ScriptedModel([{"name": "fetch_official_source", "input": {"source_id": SOURCE_ID}}, QUOTE + " " + URL])
        config = AgentConfig(enable_official_sources=True)
        runtime = AgentRuntime(self.service, config, StrandsBedrockProvider(config, model),
                               official_fetcher=OfficialSourceFetcher(transport))
        catalog = self.service.read_program_catalog()
        command = self.command()
        result = runtime.handle(self.token, command)
        case = result["case_snapshot"]
        self.assertEqual(case["conversation"]["turns"][-1]["state"], "complete")
        self.assertEqual(case["facts"], self.case["facts"])
        self.assertEqual(self.service.read_program_catalog(), catalog)
        self.assertIn(QUOTE, str(model.messages))
        self.assertIn("live", str(model.messages))
        self.assertNotIn(self.token, str(model.messages))
        spec = next(s for s in model.specs if s["name"] == "fetch_official_source")
        self.assertIn(SOURCE_ID, spec["inputSchema"]["json"]["properties"]["source_id"]["enum"])
        self.assertNotIn("propose_rule_candidate", {s["name"] for s in model.specs})
        self.assertEqual(runtime.handle(self.token, command)["case_snapshot"]["case_version"], case["case_version"])
        self.assertEqual(transport.calls, 1)
        self.assertEqual(model.calls, 2)

    def test_real_sdk_wrapped_aws_failure_retains_code_in_safe_log(self):
        from botocore.exceptions import ClientError
        AccessDeniedException = type("AccessDeniedException", (ClientError,), {})
        error = AccessDeniedException({"Error": {"Code": "AccessDeniedException", "Message": "Model is not available for this account. secret_fixture_message"}}, "Converse")
        runtime, _ = self.runtime([error])
        path = Path(self.directory.name) / "synthetic-log.jsonl"
        runtime.diagnostics = SafeDiagnostics(path)
        runtime.handle(self.token, self.command())
        records = [json.loads(line) for line in path.read_text().splitlines()]
        failure = next(entry for entry in records if entry["event"] == "provider_failed")
        self.assertEqual(failure["code"], "AccessDeniedException")
        self.assertEqual(failure["error_type"], "ClientError")
        self.assertEqual(failure["reason"], "account_model_access_denied")
        self.assertNotIn("secret_fixture", path.read_text())

    def test_sdk_loop_limit_is_visible_and_keeps_effects(self):
        runtime, _ = self.runtime([self.fact_step()], AgentConfig(max_turns=1))
        result = runtime.handle(self.token, self.command())
        self.assertEqual(result["case_snapshot"]["facts"]["mobility"]["value"], "no_car")
        turn = result["case_snapshot"]["conversation"]["turns"][-1]
        self.assertEqual(turn["issue"]["code"], "agent_limit_or_stop")

    def test_sdk_resource_missing_after_tool_retains_safe_reason_and_saved_fact(self):
        from botocore.exceptions import ClientError
        path = Path(self.directory.name) / "synthetic-log.jsonl"
        diagnostics = SafeDiagnostics(path)
        error = ClientError({"Error": {"Code": "ResourceNotFoundException",
                            "Message": "Model use case details have not been submitted for this account. secret_fixture_value"}}, "Converse")
        config = AgentConfig()
        model = ScriptedModel([self.fact_step(), error])
        provider = StrandsBedrockProvider(config, model, diagnostics)
        runtime = AgentRuntime(self.service, config, provider, diagnostics=diagnostics)
        result = runtime.handle(self.token, self.command())
        self.assertEqual(result["case_snapshot"]["facts"]["mobility"]["value"], "no_car")
        self.assertEqual(result["case_snapshot"]["conversation"]["turns"][-1]["state"], "failed")
        self.assertEqual(diagnostics.provider_failure["code"], "ResourceNotFoundException")
        self.assertEqual(diagnostics.provider_failure["reason"], "anthropic_use_case_required")
        records = [json.loads(line) for line in path.read_text().splitlines()]
        self.assertEqual(sum(entry["event"] == "tool_call_complete" for entry in records), 1)
        self.assertNotIn("secret_fixture", path.read_text())
        self.assertNotIn("secret_fixture", str(result))

    def test_bedrock_factory_gets_explicit_model_region_timeouts_and_output_cap(self):
        config = AgentConfig(model_id="demo-profile", region="demo-region")
        model = ScriptedModel(["How can I help?"])
        with patch("strands.models.BedrockModel", return_value=model) as factory:
            runtime = AgentRuntime(self.service, config)
            result = runtime.handle(self.token, self.command())
        self.assertEqual(result["case_snapshot"]["conversation"]["turns"][-1]["state"], "complete")
        settings = factory.call_args.kwargs
        self.assertEqual(settings["model_id"], "demo-profile")
        self.assertEqual(settings["region_name"], "demo-region")
        self.assertEqual(settings["max_tokens"], 1024)
        self.assertEqual(settings["boto_client_config"].retries["total_max_attempts"], 2)

    def test_real_bedrock_request_omits_sampling_fields_and_validates_converse_shape(self):
        import botocore
        from botocore.loaders import Loader
        from botocore.model import ServiceModel
        from botocore.validate import validate_parameters
        session = MagicMock()
        client = session.client.return_value
        client.converse.return_value = {
            "output": {"message": {"role": "assistant", "content": [{"text": "How can I help?"}]}},
            "stopReason": "end_turn", "usage": {"inputTokens": 20, "outputTokens": 10, "totalTokens": 30},
            "metrics": {"latencyMs": 1},
        }
        config = AgentConfig(model_id="us.openai.gpt-6-luna", region="us-east-2")
        # Replace the SDK session before construction: never inspect a user's AWS
        # profile, environment credentials or network during this request check.
        with patch("strands.models.bedrock.boto3.Session", return_value=session):
            result = AgentRuntime(self.service, config).handle(self.token, self.command())
        self.assertEqual(result["case_snapshot"]["conversation"]["turns"][-1]["state"], "complete")
        client.converse.assert_called_once()
        request = client.converse.call_args.kwargs
        self.assertEqual(request["inferenceConfig"], {"maxTokens": 1024})
        self.assertNotIn("additionalModelRequestFields", request)
        self.assertEqual(len(request["toolConfig"]["tools"]), 2)
        self.assertNotIn(self.token, json.dumps(request))
        for tool in request["toolConfig"]["tools"]:
            self.assertNotIn("strict", tool["toolSpec"])
            self.assertNotIn("$ref", json.dumps(tool["toolSpec"]["inputSchema"]))
        loader = Loader(extra_search_paths=[str(Path(botocore.__file__).parent / "data")], include_default_search_paths=False)
        service = ServiceModel(loader.load_service_model("bedrock-runtime", "service-2"))
        validate_parameters(request, service.operation_model("Converse").input_shape)
