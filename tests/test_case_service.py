import copy
import json
import re
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from backend.stillhere.contracts import InvalidInput, empty_case, validate
from backend.stillhere.service import CaseService, ServiceError

NOW = "2026-10-10T15:00:00Z"
REPORTED = "2026-10-09T18:30:00Z"


class CaseServiceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "cases.sqlite3"
        self.service = CaseService(self.path, clock=lambda: NOW)
        self.token = self.service.create_session()["session_token"]
        self.request = {"contract_version": "0.1", "event_id": "create_1", "time_zone": "America/Chicago"}
        self.snapshot = self.service.create_case(self.token, self.request)["case_snapshot"]
        self.case_id = self.snapshot["case_id"]

    def command(self, event_id="edit_1", version=1, value="no_car", fact_key="mobility"):
        return {
            "contract_version": "0.1", "case_id": self.case_id, "event_id": event_id,
            "expected_case_version": version, "occurred_at": REPORTED, "channel": "dashboard",
            "type": "fact.correct", "payload": {"fact_key": fact_key, "value": value, "observed_at": REPORTED},
        }

    def test_empty_snapshot_matches_documented_example(self):
        document = (Path(__file__).resolve().parents[1] / "docs/contracts-and-progress.md").read_text()
        section = document.split("### Minimal empty-case example", 1)[1]
        example = json.loads(re.search(r"```json\n(.*?)\n```", section, re.S).group(1))
        self.assertEqual(empty_case(example["case_id"], example["time_zone"], example["updated_at"]), example)
        validate("CaseSnapshot", self.snapshot)
        self.assertEqual(self.snapshot["facts"], {})
        self.assertEqual(self.snapshot["resources"]["state"], "not_requested")
        self.assertIsNone(self.snapshot["shared_location"])

    def test_create_retry_and_restart_resume_latest_case(self):
        self.service.execute(self.token, self.command())
        restarted = CaseService(self.path, clock=lambda: NOW)
        result = restarted.create_case(self.token, self.request)
        self.assertEqual(result["status"], "already_applied")
        self.assertEqual(result["applied_case_version"], 1)
        self.assertEqual(result["case_snapshot"]["case_version"], 2)
        self.assertEqual(result["case_snapshot"], restarted.read_case(self.token, self.case_id))
        changed = dict(self.request, time_zone="America/New_York")
        self.assertEqual(restarted.create_case(self.token, changed)["issues"][0]["code"], "event_id_reused")

    def test_authorize_before_read_write_and_event_replay(self):
        self.service.execute(self.token, self.command())
        stranger = self.service.create_session()["session_token"]
        with self.assertRaises(ServiceError) as denied:
            self.service.read_case(stranger, self.case_id)
        self.assertEqual(denied.exception.status, 404)
        for command in (self.command(), dict(self.command(), event_id="new_event")):
            result = self.service.execute(stranger, command)
            self.assertEqual(result["status"], "rejected")
            self.assertIsNone(result["case_snapshot"])
            self.assertIsNone(result["applied_case_version"])
        other = self.service.create_case(stranger, self.request)["case_snapshot"]
        self.assertNotEqual(other["case_id"], self.case_id)
        self.assertEqual(self.service.read_case(self.token, self.case_id)["case_version"], 2)

    def test_replay_precedes_version_check_and_returns_original_version(self):
        original = self.command()
        self.assertEqual(self.service.execute(self.token, original)["status"], "applied")
        self.service.execute(self.token, self.command("edit_2", 2, "limited"))
        replay = self.service.execute(self.token, dict(original, expected_case_version=99))
        self.assertEqual(replay["status"], "already_applied")
        self.assertEqual(replay["applied_case_version"], 2)
        self.assertEqual(replay["case_snapshot"]["case_version"], 3)
        changed = copy.deepcopy(original)
        changed["payload"]["value"] = "has_car"
        rejected = self.service.execute(self.token, changed)
        self.assertEqual(rejected["issues"][0]["code"], "event_id_reused")
        self.assertEqual(self.service.read_case(self.token, self.case_id)["facts"]["mobility"]["value"], "limited")

    def test_conflict_retry_can_change_precondition_but_not_intent(self):
        self.service.execute(self.token, self.command())
        stale = self.command("edit_2", 1, "limited")
        conflict = self.service.execute(self.token, stale)
        self.assertEqual(conflict["status"], "conflict")
        self.assertEqual(conflict["case_snapshot"]["case_version"], 2)
        changed = copy.deepcopy(stale)
        changed["payload"]["value"] = "has_car"
        self.assertEqual(self.service.execute(self.token, changed)["issues"][0]["code"], "event_id_reused")
        result = self.service.execute(self.token, dict(stale, expected_case_version=2))
        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["applied_case_version"], 3)

    def test_concurrent_writers_do_not_overwrite_and_same_event_applies_once(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda command: self.service.execute(self.token, command), [self.command("a"), self.command("b", value="limited")]))
        self.assertCountEqual([result["status"] for result in results], ["applied", "conflict"])
        self.assertEqual(self.service.read_case(self.token, self.case_id)["case_version"], 2)
        same = self.command("c", 2, "has_car")
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.service.execute(self.token, same), range(2)))
        self.assertCountEqual([result["status"] for result in results], ["applied", "already_applied"])
        self.assertEqual(self.service.read_case(self.token, self.case_id)["case_version"], 3)

    def test_audit_preserves_previous_fact_observation_occurrence_and_receipt_times(self):
        self.service.execute(self.token, self.command())
        self.service.execute(self.token, self.command("reset", 2, None))
        current = self.service.read_case(self.token, self.case_id)["facts"]["mobility"]
        self.assertEqual(current, {"value": None, "state": "unknown", "observed_at": REPORTED, "source_ids": []})
        with closing(sqlite3.connect(self.path)) as connection, connection:
            row = connection.execute("SELECT command_json, first_received_at, applied_received_at, before_fact_json FROM events WHERE event_id='reset'").fetchone()
            stored_tokens = connection.execute("SELECT token_digest FROM sessions").fetchall()
        self.assertEqual(json.loads(row[0])["occurred_at"], REPORTED)
        self.assertEqual(row[1:3], (NOW, NOW))
        self.assertEqual(json.loads(row[3])["value"], "no_car")
        self.assertNotIn(self.token, str(stored_tokens))

    def test_validation_and_channel_authority_never_mutate_case(self):
        commands = []
        for field, value in [("contract_version", "9"), ("expected_case_version", True), ("occurred_at", "2026-10-10T15:00:00-05:00"), ("channel", "system"), ("channel", "operator"), ("type", "finance.update"), ("role", "operator")]:
            commands.append(dict(self.command(), **{field: value}))
        for field, value in [("observed_at", "2026-02-30T15:00:00Z"), ("source_ids", ["invented_source"]), ("state", "source_supported")]:
            command = self.command()
            command["payload"][field] = value
            commands.append(command)
        command = self.command()
        command["payload"]["value"] = float("nan")
        commands.append(command)
        for command in commands:
            with self.subTest(command=command):
                result = self.service.execute(self.token, command)
                self.assertEqual(result["status"], "rejected")
                self.assertIsNone(result["case_snapshot"])
        self.assertEqual(self.service.read_case(self.token, self.case_id), self.snapshot)
        invalid_zone = dict(self.request, event_id="bad_zone", time_zone="Missing/Zone")
        self.assertEqual(self.service.create_case(self.token, invalid_zone)["status"], "rejected")
        with self.assertRaises(InvalidInput):
            validate("DashboardDescriptor", {"id": "component", "kind": "executable_code", "record_ids": [], "display_order": 0})

    def test_correction_retains_completed_work_and_marks_old_results_pending(self):
        snapshot = copy.deepcopy(self.snapshot)
        snapshot["plan"].update(state="ready", version=1, actions=[{"id": "done", "status": "completed"}])
        snapshot["finance"].update(state="calculated", baseline={"input_case_version": 1}, computed_at=NOW)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE cases SET snapshot_json=? WHERE case_id=?", (json.dumps(snapshot), self.case_id))
        updated = self.service.execute(self.token, self.command())["case_snapshot"]
        self.assertEqual(updated["plan"]["actions"], snapshot["plan"]["actions"])
        for section in ("plan", "finance"):
            self.assertEqual(updated[section]["state"], "pending")
            self.assertEqual(updated[section]["pending_input_case_version"], 2)
        self.assertEqual(updated["finance"]["input_case_version"], 1)
        self.assertEqual(updated["finance"]["baseline"], snapshot["finance"]["baseline"])

    def test_transaction_failure_rolls_back_snapshot_and_event_then_retry_succeeds(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("CREATE TRIGGER fail_apply BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT, 'synthetic storage failure'); END")
        result = self.service.execute(self.token, self.command())
        self.assertEqual(result["status"], "unavailable")
        self.assertTrue(result["issues"][0]["retryable"])
        self.assertIsNone(result["case_snapshot"])
        self.assertEqual(self.service.read_case(self.token, self.case_id), self.snapshot)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM events").fetchone()[0], 0)
            connection.execute("DROP TRIGGER fail_apply")
        self.assertEqual(self.service.execute(self.token, self.command())["status"], "applied")

    def test_unavailable_storage_does_not_claim_empty_case(self):
        with patch("backend.stillhere.service.sqlite3.connect", side_effect=sqlite3.OperationalError("synthetic outage")):
            result = self.service.execute(self.token, self.command())
            self.assertEqual(result["status"], "unavailable")
            with self.assertRaises(ServiceError) as error:
                self.service.read_case(self.token, self.case_id)
            self.assertEqual(error.exception.status, 503)


if __name__ == "__main__":
    unittest.main()
