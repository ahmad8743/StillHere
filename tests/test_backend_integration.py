"""Shared integration acceptance with temporary databases and scripted inputs."""

import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from backend.stillhere.contracts import InvalidInput, SCHEMA, _validate, validate
from backend.stillhere.service import CaseService, ServiceError
from tests.integration_fixtures import NOW, ZONE, command, create_family, family_ledger


class BackendIntegrationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "cases.sqlite3"
        self.now = NOW
        self.service = CaseService(self.path, clock=lambda: self.now)
        self.token, self.snapshot = create_family(self.service)

    def send(self, kind, payload, event_id, **kwargs):
        request = command(self.snapshot, kind, payload, event_id, **kwargs)
        result = self.service.execute(self.token, request)
        self.assertEqual(result["status"], "applied", result["issues"])
        self.snapshot = result["case_snapshot"]
        validate("CaseSnapshot", self.snapshot)
        return request, result

    def enroll(self):
        self.send("check_in.enroll", {"consent": True, "follow_up_consent": True,
                  "due_at": "2026-10-11T05:05:00Z", "time_zone": ZONE, "grace_minutes": 5,
                  "channel": "text_simulator", "permitted_need_ids": [self.snapshot["needs"][0]["id"]]}, "enroll")

    def test_check_in_restart_replay_operator_scope_and_late_reply(self):
        self.enroll()
        operator = self.service.provision_operator([self.snapshot["case_id"]], operator_id="demo_operator")
        self.now = "2026-10-11T05:11:00Z"
        restarted = CaseService(self.path, clock=lambda: self.now)
        self.assertEqual(restarted.process_due_check_ins()["processed_cases"], 1)
        self.assertEqual(restarted.process_due_check_ins()["processed_cases"], 0)
        self.snapshot = restarted.read_case(self.token, self.snapshot["case_id"])
        self.assertEqual(self.snapshot["check_in"]["status"], "overdue")
        self.assertEqual(len(self.snapshot["follow_ups"]), 1)
        self.assertEqual(len(self.snapshot["check_in"]["attempts"]), 1)
        queue = restarted.read_operator_queue(operator["session_token"])
        projection = queue["cases"][0]
        for forbidden in ("facts", "finance", "conversation", "evidence", "case_snapshot"):
            self.assertNotIn(forbidden, projection)
        request_id = projection["reviews"][0]["request_id"]
        ack = command(self.snapshot, "follow_up.acknowledge", {"request_id": request_id}, "ack", channel="operator", occurred_at=self.now)
        accepted = restarted.execute_operator(operator["session_token"], ack)
        self.assertEqual(accepted["status"], "applied", accepted["issues"])
        self.assertNotIn("case_snapshot", accepted)
        self.assertEqual(restarted.execute_operator(operator["session_token"], ack)["status"], "already_applied")
        self.snapshot = restarted.read_case(self.token, self.snapshot["case_id"])
        late, _ = self.send("check_in.reply", {"occurrence_id": self.snapshot["check_in"]["current_occurrence_id"], "reply": "okay_for_now"}, "late_reply", occurred_at="2026-10-11T05:06:00Z")
        self.assertTrue(self.snapshot["check_in"]["last_report"]["late"])
        self.assertEqual(self.snapshot["check_in"]["last_report"]["reported_at"], late["occurred_at"])
        self.assertEqual(self.snapshot["follow_ups"][0]["status"], "assigned_acknowledged")
        self.assertEqual(self.snapshot["follow_ups"][0]["report_updates"][0]["notify_operator_id"], "demo_operator")
        other, stranger = create_family(restarted)
        with self.assertRaises(ServiceError):
            restarted.read_operator_queue(operator["session_token"], stranger["case_id"])
        self.assertIsNone(restarted.execute_operator(other, ack)["operator_projection"])
        self.assertIsNone(restarted.execute(operator["session_token"], late)["case_snapshot"])

    def test_pause_and_location_clear_preserve_review_and_remove_operator_location(self):
        self.send("help.request", {"consent": True, "message": "Need food", "permitted_need_ids": [self.snapshot["needs"][0]["id"]]}, "help")
        self.assertTrue(any(notice["code"] == "simulated_help_requested" for notice in self.snapshot["notices"]))
        operator = self.service.provision_operator([self.snapshot["case_id"]])
        self.send("location.share", {"consent": True, "source": "user_entered", "place": "Synthetic shelter",
                  "observed_at": NOW, "purpose": "simulated_follow_up", "recipients": "case_handlers"}, "share")
        self.assertIsNotNone(self.service.read_operator_queue(operator["session_token"])["cases"][0]["reviews"][0]["shared_location"])
        self.send("location.clear", {}, "clear")
        self.send("check_in.pause", {"intent": "pause"}, "pause")
        self.assertEqual(len(self.snapshot["follow_ups"]), 1)
        self.assertIsNone(self.service.read_operator_queue(operator["session_token"])["cases"][0]["reviews"][0]["shared_location"])
        self.assertEqual(self.service.process_due_check_ins()["processed_cases"], 0)
        self.service.revoke_operator(operator["operator_id"])
        with self.assertRaises(ServiceError):
            self.service.read_operator_queue(operator["session_token"])

    def test_check_in_commit_rolls_back_state_effects_and_snapshot_together(self):
        with self.service._connection() as connection:
            connection.execute("CREATE TRIGGER fail_case BEFORE UPDATE ON cases BEGIN SELECT RAISE(ABORT,'synthetic'); END")
        request = command(self.snapshot, "help.request", {"consent": True, "message": "Synthetic"}, "fail")
        result = self.service.execute(self.token, request)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(self.service.read_case(self.token, self.snapshot["case_id"]), self.snapshot)
        with self.service._connection() as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM check_in_states").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT count(*) FROM simulated_effects").fetchone()[0], 0)

    def test_standalone_worker_processes_without_agent_or_private_configuration(self):
        self.send("check_in.enroll", {"consent": True, "follow_up_consent": True, "due_at": "2026-10-11T05:01:00Z",
                  "time_zone": ZONE, "grace_minutes": 0, "channel": "in_app"}, "enroll_process")
        import os, sys
        child_environment = {key: value for key, value in os.environ.items() if not key.startswith(("AWS_", "STILLHERE_"))}
        # Actual process clock is later than the fixed synthetic occurrence.
        child = subprocess.run([sys.executable, "-m", "backend.stillhere.worker", "--db", str(self.path), "--once"],
                               capture_output=True, text=True, timeout=20, env=child_environment)
        self.assertEqual(child.returncode, 0, child.stderr)
        self.assertEqual(json.loads(child.stdout)["processed_cases"], 1)
        self.assertEqual(self.service.read_case(self.token, self.snapshot["case_id"])["check_in"]["status"], "overdue")


class ExecutableContractTests(unittest.TestCase):
    def test_all_references_resolve_and_schema_keywords_are_enforced(self):
        allowed = {"$ref", "type", "required", "properties", "additionalProperties", "enum", "const", "anyOf", "allOf", "oneOf", "not", "if", "then", "else",
                   "minimum", "maximum", "minItems", "maxItems", "uniqueItems", "items", "minLength", "maxLength", "pattern", "format", "minProperties", "maxProperties", "propertyNames", "description", "title", "default"}
        def walk(schema):
            self.assertFalse(set(schema) - allowed, set(schema)-allowed)
            if "$ref" in schema:
                self.assertIn(schema["$ref"].removeprefix("#/$defs/"), SCHEMA["$defs"])
            for child in schema.get("properties", {}).values(): walk(child)
            for keyword in ("items", "additionalProperties", "not", "propertyNames", "if", "then", "else"):
                if isinstance(schema.get(keyword), dict): walk(schema[keyword])
            for keyword in ("anyOf", "oneOf", "allOf"):
                for child in schema.get(keyword, []): walk(child)
        for schema in SCHEMA["$defs"].values(): walk(schema)
        for schema, value in [({"const": True}, False), ({"const": True}, 1),
                              ({"type": "array", "minItems": 1}, []),
                              ({"type": "object", "maxProperties": 0}, {"x": 1}),
                              ({"format": "date"}, "2026-02-30")]:
            with self.assertRaises(InvalidInput): _validate(schema, value, "$")


if __name__ == "__main__":
    unittest.main()
