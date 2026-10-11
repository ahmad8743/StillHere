"""Read-only access checks use fake SDK clients; never load real local configuration."""

import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.stillhere.agent.access import access_ready, check_access
from backend.stillhere.agent.config import AgentConfig
from backend.stillhere.agent.diagnostics import SafeDiagnostics
from backend.stillhere.agent.smoke import main as smoke_main


class ClientError(Exception):
    def __init__(self, code, message):
        self.response = {"Error": {"Code": code, "Message": message}}

    def __str__(self):
        raise AssertionError("Access diagnostics must never render exception text.")


class FakeBedrock:
    def __init__(self, model="anthropic.synthetic-model-v1:0"):
        self.model = model
        self.profile = {"status": "ACTIVE", "inferenceProfileArn": "secret_fixture_profile",
                        "models": [{"modelArn": f"arn:aws:bedrock:synthetic-region::foundation-model/{model}"}]}
        self.form = {"formData": b"secret_fixture_form_data"}
        self.availability = {"agreementAvailability": {"status": "AVAILABLE", "errorMessage": "secret_fixture_message"},
                             "authorizationStatus": "AUTHORIZED", "entitlementAvailability": "AVAILABLE",
                             "regionAvailability": "AVAILABLE", "modelId": "secret_fixture_model"}
        self.profile_requests, self.availability_requests, self.form_requests = [], [], 0

    def get_inference_profile(self, **kwargs):
        self.profile_requests.append(kwargs)
        return copy.deepcopy(self.profile)

    def get_use_case_for_model_access(self):
        self.form_requests += 1
        if isinstance(self.form, Exception):
            raise self.form
        return self.form

    def get_foundation_model_availability(self, **kwargs):
        self.availability_requests.append(kwargs)
        return copy.deepcopy(self.availability)


class FakeSession:
    def __init__(self, bedrock):
        self.bedrock = bedrock
        self.calls = []

    def client(self, name, **kwargs):
        self.calls.append((name, kwargs))
        if name == "sts":
            return SimpleNamespace(get_caller_identity=lambda: {"Account": "111111111111", "Arn": "secret_fixture_identity"})
        if name == "bedrock":
            return self.bedrock
        raise AssertionError("Only read-only identity/Bedrock control-plane clients are permitted.")


class AccessTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "synthetic-log.jsonl"
        self.diagnostics = SafeDiagnostics(self.path)
        self.bedrock = FakeBedrock()
        self.session = FakeSession(self.bedrock)
        self.config = AgentConfig(model_id="us." + self.bedrock.model, region="synthetic-region")

    def check(self, **kwargs):
        return check_access(self.config, self.diagnostics, session=self.session, **kwargs)

    def test_profile_resolves_foundation_model_and_account_matches_without_retaining_data(self):
        status = self.check(expected_account_id="111111111111")
        self.assertTrue(access_ready(status))
        self.assertEqual(status["account_match"], "MATCH")
        self.assertEqual(status["use_case"], "SUBMITTED")
        self.assertEqual(self.bedrock.availability_requests, [{"modelId": self.bedrock.model}])
        self.assertTrue(all(options["region_name"] == "synthetic-region" for _, options in self.session.calls))
        content = self.path.read_text() + json.dumps(status)
        self.assertNotIn("secret_fixture", content)
        self.assertNotIn("111111111111", content)
        self.assertNotIn(self.bedrock.model, content)

    def test_pending_agreement_and_account_mismatch_are_distinct(self):
        self.bedrock.availability["agreementAvailability"]["status"] = "PENDING"
        status = self.check(expected_account_id="222222222222")
        self.assertEqual(status["agreement"], "PENDING")
        self.assertEqual(status["account_match"], "MISMATCH")
        self.assertFalse(access_ready(status))
        self.assertNotIn("222222222222", self.path.read_text())

    def test_missing_form_retains_only_safe_status_and_error(self):
        self.bedrock.form = ClientError("ResourceNotFoundException", "Model use case details have not been submitted. secret_fixture_message")
        status = self.check()
        self.assertEqual(status["use_case"], "NOT_VISIBLE")
        self.assertFalse(access_ready(status))
        self.assertEqual(self.diagnostics.provider_failure["reason"], "anthropic_use_case_required")
        self.assertNotIn("secret_fixture", self.path.read_text())

    def test_openai_does_not_query_anthropic_form_and_reports_model_authorization(self):
        self.bedrock = FakeBedrock("openai.synthetic-model")
        self.session = FakeSession(self.bedrock)
        self.config = AgentConfig(model_id="us." + self.bedrock.model, region="synthetic-region")
        self.bedrock.availability["authorizationStatus"] = "NOT_AUTHORIZED"
        status = self.check()
        self.assertEqual(self.bedrock.form_requests, 0)
        self.assertEqual(status["use_case"], "NOT_APPLICABLE")
        self.assertEqual(status["authorization"], "NOT_AUTHORIZED")
        self.assertFalse(access_ready(status))

    def test_unrecognized_aws_values_and_malformed_routing_do_not_leak_or_pass(self):
        self.bedrock.availability["agreementAvailability"]["status"] = "secret_fixture_status"
        self.bedrock.availability["authorizationStatus"] = {"secret_fixture": "value"}
        status = self.check()
        self.assertEqual(status["agreement"], "UNKNOWN")
        self.assertEqual(status["authorization"], "UNKNOWN")
        self.assertFalse(access_ready(status))
        self.bedrock.profile["models"] = None
        self.bedrock.availability_requests.clear()
        self.assertEqual(self.check()["agreement"], "UNKNOWN")
        self.assertEqual(self.bedrock.availability_requests, [])
        self.assertNotIn("secret_fixture", self.path.read_text())

    def test_control_plane_permission_failure_keeps_form_unknown(self):
        self.bedrock.form = ClientError("AccessDeniedException", "User is not authorized to perform bedrock:GetUseCaseForModelAccess. secret_fixture_message")
        status = self.check()
        self.assertEqual(status["use_case"], "UNKNOWN")
        self.assertEqual(status["agreement"], "AVAILABLE")
        self.assertFalse(access_ready(status))
        self.assertEqual(self.diagnostics.provider_failure["reason"], "iam_permission_denied")
        self.assertNotIn("secret_fixture", self.path.read_text())

    def test_cli_access_mode_does_not_start_case_service_or_model_inference(self):
        self.bedrock.availability["agreementAvailability"]["status"] = "PENDING"
        output = io.StringIO()
        def fake_check(config, diagnostics, **kwargs):
            return check_access(config, diagnostics, session=self.session, **kwargs)
        with patch("sys.argv", ["smoke", "--check-access", "--expected-account-id", "111111111111", "--log-file", str(self.path)]), \
             patch("backend.stillhere.agent.smoke.AgentConfig.from_environment", return_value=self.config), \
             patch("backend.stillhere.agent.access.check_access", side_effect=fake_check), \
             patch("backend.stillhere.agent.smoke.CaseService") as case_service, \
             patch("backend.stillhere.agent.smoke.AgentRuntime") as runtime, redirect_stdout(output):
            self.assertEqual(smoke_main(), 1)
        case_service.assert_not_called()
        runtime.assert_not_called()
        self.assertIn("agreement: PENDING", output.getvalue())
        self.assertIn("account_match: MATCH", output.getvalue())
        self.assertNotIn("secret_fixture", output.getvalue())
        self.assertNotIn("111111111111", output.getvalue())
