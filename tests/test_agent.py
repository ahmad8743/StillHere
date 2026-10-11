import copy
import importlib.util
import io
import json
import sqlite3
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from backend.stillhere.agent import AgentConfig, AgentRuntime
from backend.stillhere.agent.registry import CASE_TOOLS, INTAKE_TOOL, ToolRegistry, inline_schema
from backend.stillhere.agent.tools import AgentContext, AgentFailure
from backend.stillhere.contracts import validate
from backend.stillhere.commands import assistant_turn_id
from backend.stillhere.agent.config import load_local_environment
from backend.stillhere.agent.diagnostics import SafeDiagnostics
from backend.stillhere.agent.smoke import main as smoke_main
from backend.stillhere.service import CaseService, ServiceError

NOW = "2026-10-10T15:00:00Z"


class ScriptedProvider:
    def __init__(self, action=None):
        self.action = action
        self.calls = 0
        self.histories = []

    def reply(self, snapshot, history, text, context, registry):
        self.calls += 1
        self.histories.append(history)
        if self.action:
            self.action(context, registry)
        return "Your reported mobility is saved."


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "cases.sqlite3"
        self.now = NOW
        self.service = CaseService(self.path, clock=lambda: self.now)
        self.token = self.service.create_session()["session_token"]
        self.case = self.service.create_case(self.token, {
            "contract_version": "0.1", "event_id": "create", "time_zone": "America/Chicago",
        })["case_snapshot"]
        self.case_id = self.case["case_id"]

    def message(self, event="chat_1", version=None, text="I have no car."):
        return {"contract_version": "0.1", "case_id": self.case_id, "event_id": event,
                "expected_case_version": version or self.snapshot()["case_version"], "occurred_at": NOW,
                "channel": "chat", "type": "conversation.message",
                "payload": {"message_id": "message_" + event, "text": text}}

    def snapshot(self):
        return self.service.read_case(self.token, self.case_id)

    def payload(self):
        return {"fact_key": "mobility", "value": "no_car", "observed_at": NOW}

    def claimed_context(self):
        self.service.execute(self.token, self.message())
        claim = self.service.claim_agent_turn(self.token, self.case_id, "chat_1", 60)
        return AgentContext(self.service, self.token, self.case_id, "chat_1", claim["run_id"],
                            claim["snapshot"]["case_version"], time.monotonic() + 60, 20, 48000)

    def test_durable_reply_and_fact_write_use_shared_service_and_replay(self):
        results = []
        def action(context, registry):
            results.append(registry.invoke("read_case", {}, context))
            results.append(registry.invoke("correct_fact", self.payload(), context))
            results.append(registry.invoke("correct_fact", self.payload(), context))
        provider = ScriptedProvider(action)
        runtime = AgentRuntime(self.service, provider=provider)
        command = self.message()
        result = runtime.handle(self.token, command)
        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["applied_case_version"], 2)
        self.assertEqual(result["case_snapshot"]["facts"]["mobility"]["state"], "user_reported")
        self.assertEqual(result["case_snapshot"]["conversation"]["turns"][-1]["state"], "complete")
        self.assertEqual(results[2]["status"], "already_applied")
        version = result["case_snapshot"]["case_version"]
        self.assertEqual(runtime.handle(self.token, command)["status"], "already_applied")
        self.assertEqual(provider.calls, 1)
        self.assertEqual(self.snapshot()["case_version"], version)
        restarted = CaseService(self.path, clock=lambda: NOW)
        self.assertEqual(AgentRuntime(restarted, provider=provider).handle(self.token, command)["status"], "already_applied")
        self.assertEqual(provider.calls, 1)
        with self.service._connection() as connection:
            rows = connection.execute("SELECT * FROM events WHERE command_json LIKE '%fact.correct%'").fetchall()
            self.assertEqual(len(rows), 1)
            self.assertIsNotNone(rows[0]["before_case_json"])
            self.assertEqual(rows[0]["applied_version"], 4)
        validate("CaseSnapshot", self.snapshot())

    def test_provider_failure_preserves_accepted_effect_and_sanitizes_error(self):
        def action(context, registry):
            registry.invoke("correct_fact", self.payload(), context)
            raise RuntimeError("secret_credential_or_private_prompt")
        provider = ScriptedProvider(action)
        runtime = AgentRuntime(self.service, provider=provider)
        command = self.message()
        result = runtime.handle(self.token, command)
        turn = result["case_snapshot"]["conversation"]["turns"][-1]
        self.assertEqual(turn["state"], "failed")
        self.assertEqual(turn["issue"]["code"], "agent_provider_unavailable")
        self.assertNotIn("secret_credential", str(result))
        self.assertEqual(self.snapshot()["facts"]["mobility"]["value"], "no_car")
        runtime.handle(self.token, command)
        self.assertEqual(provider.calls, 1)

    def test_missing_provider_settings_are_a_visible_failed_turn(self):
        result = AgentRuntime(self.service).handle(self.token, self.message())
        self.assertEqual(result["status"], "applied")  # The user message was durably accepted.
        turn = result["case_snapshot"]["conversation"]["turns"][-1]
        self.assertEqual(turn["state"], "failed")
        self.assertEqual(turn["issue"]["code"], "agent_not_configured")
        self.assertIn("AWS_REGION", turn["issue"]["message"])
        self.assertIn("STILLHERE_BEDROCK_MODEL_ID", turn["issue"]["message"])
        self.assertEqual(self.snapshot()["facts"], {})

    def test_unauthorized_context_and_model_selected_authority_are_rejected(self):
        context = self.claimed_context()
        registry = ToolRegistry()
        for key, value in (("case_id", "other_case"), ("token", "token"), ("channel", "system"), ("role", "operator")):
            result = registry.invoke("correct_fact", dict(self.payload(), **{key: value}), context)
            self.assertEqual(result["error"]["code"], "invalid_tool_input")
        stranger = self.service.create_session()["session_token"]
        context.token = stranger
        self.assertEqual(registry.invoke("read_case", {}, context)["error"]["code"], "case_unavailable")
        write = registry.invoke("correct_fact", self.payload(), context)
        self.assertEqual(write["status"], "rejected")
        self.assertIsNone(write["case_snapshot"])
        self.assertEqual(self.snapshot()["facts"], {})

    def test_conflict_cannot_be_automatically_rebased_by_an_agent_read(self):
        context = self.claimed_context()
        external = self.message("external", context.expected_version)
        external.update(type="fact.correct", channel="dashboard", payload={"fact_key": "mobility", "value": "car_available", "observed_at": NOW})
        self.service.execute(self.token, external)
        registry = ToolRegistry()
        self.assertEqual(registry.invoke("correct_fact", self.payload(), context)["status"], "conflict")
        registry.invoke("read_case", {}, context)
        with self.assertRaises(AgentFailure):
            registry.invoke("correct_fact", self.payload(), context)
        self.assertEqual(self.snapshot()["facts"]["mobility"]["value"], "car_available")

    def test_intake_adapter_is_opt_in_and_keeps_unknowns_and_consent(self):
        self.assertEqual([d.name for d in AgentRuntime(self.service).registry.definitions], ["read_case", "correct_fact"])
        context = self.claimed_context()
        registry = ToolRegistry(CASE_TOOLS + (INTAKE_TOOL,))
        result = registry.invoke("submit_intake", {"selections": {"needs": ["shelter"], "household_group": ["children_with_me"], "current_location": {"place": "Demo City"}}}, context)
        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["case_snapshot"]["needs"][0]["state"], "unknown")
        self.assertIsNone(result["case_snapshot"]["shared_location"])
        self.assertFalse(result["case_snapshot"]["check_in"]["enrolled"])
        bad = registry.invoke("submit_intake", {"selections": {"needs": ["shelter", "unsure"]}}, context)
        self.assertEqual(bad["error"]["code"], "invalid_tool_input")

    def test_case_scoped_claim_is_unique_across_service_instances(self):
        command = self.message()
        self.service.execute(self.token, command)
        other = CaseService(self.path, clock=lambda: NOW)
        with ThreadPoolExecutor(max_workers=2) as pool:
            claims = list(pool.map(lambda s: s.claim_agent_turn(self.token, self.case_id, "chat_1", 60), [self.service, other]))
        self.assertEqual(sum(c is not None for c in claims), 1)

    def test_queued_turn_can_resume_after_restart_and_failed_turn_does_not_rerun(self):
        command = self.message()
        self.service.execute(self.token, command)
        restarted = CaseService(self.path, clock=lambda: self.now)
        provider = ScriptedProvider()
        result = AgentRuntime(restarted, provider=provider).handle(self.token, command)
        self.assertEqual(result["status"], "already_applied")
        self.assertEqual(result["case_snapshot"]["conversation"]["turns"][-1]["state"], "complete")
        self.assertEqual(provider.calls, 1)

    def test_expired_run_is_failed_and_cannot_write_or_replace_the_reply(self):
        context = self.claimed_context()
        self.now = "2026-10-10T15:01:01Z"
        self.assertIsNone(self.service.claim_agent_turn(self.token, self.case_id, "chat_1", 60))
        self.assertEqual(self.snapshot()["conversation"]["turns"][-1]["issue"]["code"], "agent_interrupted")
        result = self.service.execute_agent_command(self.token, self.case_id, "chat_1", context.run_id, "fact.correct", self.payload(), context.expected_version)
        self.assertEqual(result["issues"][0]["code"], "agent_run_inactive")
        self.service.finish_agent_turn(self.token, self.case_id, "chat_1", context.run_id, "Late reply")
        self.assertEqual(self.snapshot()["conversation"]["turns"][-1]["text"], "")

    def test_owner_records_timeout_at_lease_expiry_without_allowing_late_writes(self):
        context = self.claimed_context()
        self.now = "2026-10-10T15:01:01Z"
        issue = {"code": "agent_timeout", "message": "The agent time limit was reached.", "retryable": False}
        with self.assertRaises(ServiceError) as wrong_run:
            self.service.finish_agent_turn(self.token, self.case_id, "chat_1", "wrong_run", issue=issue)
        self.assertEqual(wrong_run.exception.issue["code"], "agent_run_inactive")
        late_write = self.service.execute_agent_command(self.token, self.case_id, "chat_1", context.run_id,
                                                       "fact.correct", self.payload(), context.expected_version)
        self.assertEqual(late_write["issues"][0]["code"], "agent_run_inactive")
        saved = self.service.finish_agent_turn(self.token, self.case_id, "chat_1", context.run_id, issue=issue)
        self.assertEqual(saved["conversation"]["turns"][-1]["issue"]["code"], "agent_timeout")
        self.assertEqual(saved["facts"], {})
        self.service.finish_agent_turn(self.token, self.case_id, "chat_1", context.run_id, "Late success")
        self.assertEqual(self.snapshot(), saved)

    def test_diagnostics_keep_aws_code_and_omit_secret_messages_and_unknown_codes(self):
        path = Path(self.directory.name) / "synthetic-log.jsonl"
        diagnostics = SafeDiagnostics(path)
        ClientError = type("ClientError", (Exception,), {})
        error = ClientError("secret_fixture_exception")
        error.response = {"Error": {"Code": "AccessDeniedException", "Message": "secret_fixture_aws_message"},
                          "ResponseMetadata": {"RequestId": "secret_fixture_request"}}
        diagnostics.failure(error)
        error.response["Error"]["Code"] = "secret_fixture_unknown_code"
        diagnostics.failure(error)
        diagnostics.record("provider_failed", code="secret_fixture_code", error_type="secret_fixture_type")
        content = path.read_text()
        records = [json.loads(line) for line in content.splitlines()]
        self.assertEqual(records[0]["code"], "AccessDeniedException")
        self.assertEqual(records[0]["error_type"], "ClientError")
        self.assertEqual(records[1]["code"], "other_failure")
        self.assertEqual(records[2]["error_type"], "Exception")
        self.assertNotIn("secret_fixture", content)

    def test_diagnostic_storage_failure_does_not_fail_an_accepted_reply(self):
        diagnostics = SafeDiagnostics(Path(self.directory.name) / "synthetic-log.jsonl")
        runtime = AgentRuntime(self.service, provider=ScriptedProvider(), diagnostics=diagnostics)
        with patch.object(diagnostics, "record", side_effect=PermissionError("synthetic diagnostic storage failure")):
            result = runtime.handle(self.token, self.message())
        self.assertEqual(result["case_snapshot"]["conversation"]["turns"][-1]["state"], "complete")

    def test_aws_diagnostic_reasons_never_copy_message_values(self):
        path = Path(self.directory.name) / "synthetic-log.jsonl"
        diagnostics = SafeDiagnostics(path)
        ClientError = type("ClientError", (Exception,), {})
        fixtures = (
            ("ValidationException", "The provided model identifier is invalid.", "model_identifier_invalid"),
            ("ValidationException", "Invocation with on-demand throughput isn't supported. Use an inference profile.", "inference_profile_required"),
            ("ValidationException", "This model doesn't support the temperature field.", "temperature_unsupported"),
            ("ValidationException", "This model doesn't support the topP field.", "top_p_unsupported"),
            ("ValidationException", "This model doesn't support the stopSequences field.", "stop_sequences_unsupported"),
            ("ValidationException", "Operation not allowed", "operation_not_allowed"),
            ("AccessDeniedException", "Model is not available for this account.", "account_model_access_denied"),
            ("AccessDeniedException", "Missing aws-marketplace:Subscribe permission.", "marketplace_subscription_permission"),
            ("AccessDeniedException", "INVALID_PAYMENT_INSTRUMENT", "payment_method_required"),
            ("AccessDeniedException", "User is not authorized to perform bedrock:InvokeModel.", "iam_permission_denied"),
            ("ResourceNotFoundException", "Model use case details have not been submitted for this account.", "anthropic_use_case_required"),
            ("FTUFormNotFilled", "An unfamiliar rejection.", "anthropic_use_case_required"),
            ("ResourceNotFoundException", "An unfamiliar missing resource.", "unclassified"),
            ("ValidationException", "An unfamiliar rejection.", "unclassified"),
            ("ValidationException", {"Message": "Operation not allowed"}, "unclassified"),
            ("ValidationException", "Operation not allowed" * 1000, "unclassified"),
        )
        for code, message, reason in fixtures:
            with self.subTest(reason=reason):
                error = ClientError("secret_fixture_exception")
                error.response = {"Error": {"Code": code, "Message": message + " secret_fixture_value" if isinstance(message, str) else message}}
                diagnostics.failure(error)
                self.assertEqual(json.loads(path.read_text().splitlines()[-1])["reason"], reason)
                self.assertEqual(diagnostics.provider_failure["reason"], reason)
        diagnostics.record("provider_failed", reason="secret_fixture_reason")
        self.assertEqual(json.loads(path.read_text().splitlines()[-1])["reason"], "unclassified")
        content = path.read_text()
        self.assertNotIn("secret_fixture", content)
        self.assertNotIn("Operation not allowed", content)
        self.assertNotIn("secret_fixture", str(diagnostics.provider_failure))

    def test_diagnostics_unwrap_generated_aws_errors_without_rendering_exception_text(self):
        path = Path(self.directory.name) / "synthetic-log.jsonl"
        diagnostics = SafeDiagnostics(path)
        class ClientError(Exception):
            def __str__(self):
                raise AssertionError("Diagnostic code must never render exception text.")
        AccessDeniedException = type("AccessDeniedException", (ClientError,), {})
        root = AccessDeniedException()
        root.response = {"Error": {"Code": "AccessDeniedException", "Message": "secret_fixture_message"}}
        wrapper = RuntimeError("secret_fixture_wrapper")
        wrapper.__cause__ = root
        root.__context__ = wrapper  # Cycles must not cause an unbounded traversal.
        diagnostics.failure(wrapper)
        diagnostics.failure(root)
        records = [json.loads(line) for line in path.read_text().splitlines()]
        self.assertEqual([entry["code"] for entry in records], ["AccessDeniedException"] * 2)
        self.assertEqual([entry["error_type"] for entry in records], ["ClientError"] * 2)
        self.assertNotIn("secret_fixture", path.read_text())

    def test_tool_budget_and_invalid_output_fail_without_replaying(self):
        def action(context, registry):
            registry.invoke("read_case", {}, context)
            registry.invoke("read_case", {}, context)
        runtime = AgentRuntime(self.service, AgentConfig(max_tool_calls=1), ScriptedProvider(action))
        result = runtime.handle(self.token, self.message())
        self.assertEqual(result["case_snapshot"]["conversation"]["turns"][-1]["issue"]["code"], "agent_tool_limit")

    def test_message_reuse_changed_intent_whitespace_and_forbidden_channel(self):
        runtime = AgentRuntime(self.service, provider=ScriptedProvider())
        command = self.message()
        runtime.handle(self.token, command)
        changed = copy.deepcopy(command)
        changed["payload"]["text"] = "Changed"
        self.assertEqual(runtime.handle(self.token, changed)["issues"][0]["code"], "event_id_reused")
        for bad in (self.message("blank", text="   "), dict(self.message("operator"), channel="operator")):
            self.assertEqual(runtime.handle(self.token, bad)["status"], "rejected")
        reused = self.message("reuse")
        reused["payload"]["message_id"] = command["payload"]["message_id"]
        self.assertEqual(runtime.handle(self.token, reused)["issues"][0]["code"], "message_id_reused")

    def test_history_restores_recent_completed_turns_and_fresh_case_context(self):
        provider = ScriptedProvider()
        runtime = AgentRuntime(self.service, provider=provider)
        runtime.handle(self.token, self.message())
        runtime.handle(self.token, self.message("second"))
        self.assertEqual([t["role"] for t in provider.histories[1]], ["user", "assistant"])

    def test_failed_assistant_commit_rolls_back_state_and_preserves_domain_changes(self):
        context = self.claimed_context()
        ToolRegistry().invoke("correct_fact", self.payload(), context)
        before = self.snapshot()
        with patch.object(self.service, "_save_agent_state", side_effect=sqlite3.OperationalError("disk failure")):
            with self.assertRaises(ServiceError):
                self.service.finish_agent_turn(self.token, self.case_id, "chat_1", context.run_id, "Done")
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.snapshot()["facts"]["mobility"]["value"], "no_car")

    def test_registry_schema_has_no_unresolved_refs_or_authority(self):
        for definition in CASE_TOOLS + (INTAKE_TOOL,):
            schema = inline_schema(definition.arguments_schema)
            self.assertNotIn("$ref", str(schema))
            self.assertFalse({"token", "case_id", "role", "run_id", "channel"} & schema["properties"].keys())

    def test_timeout_releases_case_and_rejects_late_tools(self):
        release = threading.Event()
        finished = threading.Event()
        contexts = []
        def action(context, registry):
            contexts.append(context)
            release.wait(3)
            try:
                registry.invoke("correct_fact", self.payload(), context)
            finally:
                finished.set()
        runtime = AgentRuntime(self.service, AgentConfig(timeout_seconds=1), ScriptedProvider(action))
        result = runtime.handle(self.token, self.message())
        self.assertEqual(result["case_snapshot"]["conversation"]["turns"][-1]["issue"]["code"], "agent_timeout")
        release.set()
        self.assertTrue(finished.wait(2))
        self.assertEqual(self.snapshot()["facts"], {})

    def test_positive_config_and_explicit_environment(self):
        with self.assertRaises(ValueError):
            AgentConfig(max_tool_calls=0)
        with patch.dict("os.environ", {"AWS_REGION": "demo-region", "STILLHERE_BEDROCK_MODEL_ID": "demo-model", "STILLHERE_AGENT_ENABLE_INTAKE": "true"}, clear=True):
            config = AgentConfig.from_environment()
        self.assertEqual(config.region, "demo-region")
        self.assertTrue(config.enable_intake)

    def test_smoke_names_missing_settings_without_starting_service_or_echoing_values(self):
        cases = (
            (AgentConfig(), ("AWS_REGION", "STILLHERE_BEDROCK_MODEL_ID"), ""),
            (AgentConfig(model_id="private-fixture-profile-id"), ("AWS_REGION",), "private-fixture-profile-id"),
            (AgentConfig(region="fixture-region"), ("STILLHERE_BEDROCK_MODEL_ID",), "fixture-region"),
        )
        for config, missing, hidden in cases:
            with self.subTest(missing=missing):
                output = io.StringIO()
                with patch("sys.argv", ["smoke", "--log-file", str(Path(self.directory.name) / "synthetic-log.jsonl")]), \
                     patch("backend.stillhere.agent.smoke.AgentConfig.from_environment", return_value=config), \
                     patch("backend.stillhere.agent.smoke.CaseService") as service, redirect_stdout(output):
                    self.assertEqual(smoke_main(), 1)
                service.assert_not_called()
                self.assertIn("Missing required settings: " + ", ".join(missing), output.getvalue())
                if hidden:
                    self.assertNotIn(hidden, output.getvalue())

    def test_second_message_queued_during_a_run_continues_in_arrival_order(self):
        started = threading.Event()
        release = threading.Event()
        completed = threading.Event()
        def action(context, registry):
            if context.event_id == "chat_1":
                started.set()
                release.wait(3)
            else:
                completed.set()
        provider = ScriptedProvider(action)
        runtime = AgentRuntime(self.service, provider=provider)
        with ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(runtime.handle, self.token, self.message())
            self.assertTrue(started.wait(2))
            result = runtime.handle(self.token, self.message("second"))
            self.assertEqual(result["case_snapshot"]["conversation"]["turns"][-1]["state"], "queued")
            release.set()
            first.result(2)
        self.assertTrue(completed.wait(2))
        # Completion is asynchronous; wait for the database transition, not commentary.
        deadline = time.monotonic() + 2
        while self.snapshot()["conversation"]["turns"][-1]["state"] != "complete" and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(self.snapshot()["conversation"]["turns"][-1]["state"], "complete")
        self.assertEqual(provider.calls, 2)

    def test_backend_event_and_assistant_identities_cannot_be_claimed_by_clients(self):
        command = self.message("agent_tool_chosen_by_client")
        self.assertEqual(self.service.execute(self.token, command)["issues"][0]["code"], "reserved_event_id")
        command = self.message()
        command["payload"]["message_id"] = assistant_turn_id(self.case_id, command["event_id"])
        self.assertEqual(self.service.execute(self.token, command)["issues"][0]["code"], "message_id_reused")
        self.assertEqual(self.snapshot()["conversation"]["turns"], [])

    @unittest.skipUnless(importlib.util.find_spec("dotenv"), "Install python-dotenv for configuration-loader checks")
    def test_explicit_synthetic_environment_preserves_existing_values_and_skips_blanks(self):
        # A synthetic fixture outside credential filenames, never the user's .env.local.
        path = Path(self.directory.name) / "synthetic-settings.txt"
        path.write_text('AWS_REGION=fixture-region\nAWS_PROFILE=\nSTILLHERE_BEDROCK_MODEL_ID=fixture-model\n')
        with patch.dict("os.environ", {"AWS_REGION": "existing-region"}, clear=True):
            load_local_environment(path)
            import os
            self.assertEqual(os.environ["AWS_REGION"], "existing-region")
            self.assertNotIn("AWS_PROFILE", os.environ)
            self.assertEqual(os.environ["STILLHERE_BEDROCK_MODEL_ID"], "fixture-model")

    @unittest.skipUnless(importlib.util.find_spec("dotenv"), "Install python-dotenv for configuration-loader checks")
    def test_blank_shell_settings_do_not_mask_explicit_synthetic_file(self):
        path = Path(self.directory.name) / "synthetic-settings.txt"
        path.write_text('AWS_REGION=fixture-region\nSTILLHERE_BEDROCK_MODEL_ID=fixture-model\n')
        for blank in ("", "   "):
            with self.subTest(blank=repr(blank)), patch.dict("os.environ", {
                "AWS_REGION": blank, "STILLHERE_BEDROCK_MODEL_ID": blank,
            }, clear=True):
                load_local_environment(path)
                config = AgentConfig.from_environment()
                self.assertEqual(config.region, "fixture-region")
                self.assertEqual(config.model_id, "fixture-model")
                self.assertEqual(config.missing_provider_settings, ())
