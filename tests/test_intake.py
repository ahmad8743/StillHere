import copy
import json
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

from backend.stillhere.commands import with_intake
from backend.stillhere.contracts import validate
from backend.stillhere.service import CaseService

NOW = "2026-10-10T15:00:00Z"
REPORTED = "2026-10-09T18:30:00Z"


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "cases.sqlite3"
        self.service = CaseService(self.path, clock=lambda: NOW)
        self.token = self.service.create_session()["session_token"]
        self.create = {"contract_version": "0.1", "event_id": "create", "time_zone": "America/Chicago"}
        self.snapshot = self.service.create_case(self.token, self.create)["case_snapshot"]

    def command(self, selections, event_id="intake", version=1, channel="dashboard"):
        return {
            "contract_version": "0.1", "case_id": self.snapshot["case_id"], "event_id": event_id,
            "expected_case_version": version, "occurred_at": REPORTED, "channel": channel,
            "type": "intake.submit", "payload": selections,
        }

    def read(self):
        return self.service.read_case(self.token, self.snapshot["case_id"])

    def test_create_with_intake_and_replay_preserves_scope_and_observation(self):
        request = dict(self.create, event_id="create_intake", occurred_at=REPORTED, intake={
            "help_urgency": "essentials_today", "crisis_type": "flood",
            "household_group": ["children_with_me"], "needs": ["shelter", "food_water"],
            "current_location": {"place": "Demo City, IL", "postal_code": "60601"},
        })
        result = self.service.create_case(self.token, request)
        self.assertEqual(result["status"], "applied")
        snapshot = result["case_snapshot"]
        validate("CaseSnapshot", snapshot)
        self.assertEqual(snapshot["case_version"], 1)
        self.assertEqual(snapshot["facts"]["crisis_type"], {
            "value": "flood", "state": "user_reported", "observed_at": REPORTED, "source_ids": [],
        })
        self.assertNotIn("damaged_residence", snapshot["facts"])
        self.assertNotIn("issuing_jurisdiction", snapshot["facts"])
        self.assertNotIn("children_count", snapshot["facts"])
        self.assertIsNone(snapshot["shared_location"])
        self.assertFalse(snapshot["check_in"]["enrolled"])
        self.assertEqual(snapshot["resources"]["state"], "not_requested")
        self.assertEqual(snapshot["finance"]["ledger"]["money_sources"], [])
        for need in snapshot["needs"]:
            validate("IntakeNeed", need)
            self.assertEqual(need["state"], "unknown")
        replay = self.service.create_case(self.token, request)
        self.assertEqual(replay["status"], "already_applied")
        self.assertEqual(replay["case_snapshot"], snapshot)
        changed = copy.deepcopy(request)
        changed["intake"]["crisis_type"] = "wildfire"
        self.assertEqual(self.service.create_case(self.token, changed)["issues"][0]["code"], "event_id_reused")

    def test_creation_defaults_observation_to_receipt_and_supports_empty_intake(self):
        request = dict(self.create, event_id="create_default_time", intake={"crisis_type": "earthquake"})
        snapshot = self.service.create_case(self.token, request)["case_snapshot"]
        self.assertEqual(snapshot["facts"]["crisis_type"]["observed_at"], NOW)
        empty = self.service.create_case(self.token, dict(self.create, event_id="create_empty", intake={}))
        self.assertEqual(empty["case_snapshot"]["facts"], {})
        self.assertEqual(empty["case_snapshot"]["case_version"], 1)

    def test_skips_and_uncertainty_never_invent_negative_facts(self):
        empty = self.service.execute(self.token, self.command({}))
        self.assertEqual(empty["status"], "applied")
        self.assertEqual(empty["case_snapshot"]["facts"], {})
        skipped = self.service.execute(self.token, self.command({
            "help_urgency": "unsure", "crisis_type": None, "household_group": [],
            "needs": ["unsure"], "current_location": None,
        }, "skip", 2))["case_snapshot"]
        for fact in skipped["facts"].values():
            self.assertIsNone(fact["value"])
            self.assertEqual(fact["state"], "unknown")
        self.assertEqual(skipped["needs"], [])
        self.assertEqual(skipped["resources"]["state"], "not_requested")

    def test_partial_updates_preserve_prior_facts_needs_and_completed_work(self):
        first = self.service.execute(self.token, self.command({
            "help_urgency": "essentials_today", "crisis_type": "flood", "needs": ["shelter"],
        }))["case_snapshot"]
        shelter_id = first["needs"][0]["id"]
        first["needs"][0]["state"] = "covered"
        first["plan"].update(state="ready", version=1, actions=[{"id": "done", "status": "completed"}])
        first["finance"].update(state="calculated", input_case_version=2, baseline={"input_case_version": 2}, computed_at=NOW)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE cases SET snapshot_json=? WHERE case_id=?", (json.dumps(first), self.snapshot["case_id"]))
        updated = self.service.execute(self.token, self.command({"needs": ["food_water"]}, "more", 2))["case_snapshot"]
        self.assertEqual(updated["facts"]["crisis_type"], first["facts"]["crisis_type"])
        self.assertEqual(updated["needs"][0]["id"], shelter_id)
        self.assertEqual(updated["needs"][0]["state"], "covered")
        self.assertEqual([need["kind"] for need in updated["needs"]], ["shelter", "food_water"])
        self.assertEqual(updated["plan"]["actions"], first["plan"]["actions"])
        self.assertEqual(updated["finance"]["input_case_version"], 2)
        for section in ("plan", "finance"):
            self.assertEqual(updated[section]["state"], "pending")
            self.assertEqual(updated[section]["pending_input_case_version"], 3)
        again = self.service.execute(self.token, self.command({"needs": ["shelter"]}, "again", 3))["case_snapshot"]
        self.assertEqual(again["needs"][0]["id"], shelter_id)
        self.assertEqual(again["needs"][0]["state"], "covered")
        self.assertEqual(len(again["needs"]), 2)

    def test_replay_conflict_and_changed_intent_do_not_duplicate_needs(self):
        command = self.command({"needs": ["transport"]})
        original = self.service.execute(self.token, command)
        replay = self.service.execute(self.token, dict(command, expected_case_version=99))
        self.assertEqual(replay["status"], "already_applied")
        self.assertEqual(replay["case_snapshot"], original["case_snapshot"])
        changed = copy.deepcopy(command)
        changed["payload"]["needs"] = ["shelter"]
        self.assertEqual(self.service.execute(self.token, changed)["issues"][0]["code"], "event_id_reused")
        stale = self.command({"needs": ["transport", "food_water"]}, "more", 1)
        self.assertEqual(self.service.execute(self.token, stale)["status"], "conflict")
        updated = self.service.execute(self.token, dict(stale, expected_case_version=2))
        self.assertEqual(updated["status"], "applied")
        self.assertEqual(len(updated["case_snapshot"]["needs"]), 2)
        self.assertEqual(updated["case_snapshot"]["needs"][0]["id"], original["case_snapshot"]["needs"][0]["id"])

    def test_audit_retains_whole_previous_case_and_distinct_times(self):
        command = self.command({"crisis_type": "flood", "needs": ["food_water"]})
        self.service.execute(self.token, command)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            row = connection.execute("SELECT before_case_json, command_json, first_received_at, applied_received_at FROM events WHERE event_id='intake'").fetchone()
        self.assertEqual(json.loads(row[0]), self.snapshot)
        self.assertEqual(json.loads(row[1])["occurred_at"], REPORTED)
        self.assertEqual(row[2:], (NOW, NOW))

    def test_bad_selections_fail_atomically_with_field_issues(self):
        invalid = [
            {"crisis_type": "model_invented_crisis"}, {"needs": ["shelter", "shelter"]},
            {"needs": ["shelter", "unsure"]}, {"household_group": ["just_me", "children_with_me"]},
            {"current_location": {}}, {"current_location": {"place": "   "}},
            {"current_location": {"postal_code": "bad_zip"}},
            {"current_location": {"place": "Demo City", "sharing_consent": True}},
            {"enrolled": True}, {"cash_cents": 30000},
        ]
        for index, bad in enumerate(invalid):
            payload = dict(bad, help_urgency="essentials_today")
            with self.subTest(payload=payload):
                rejected = self.service.execute(self.token, self.command(payload, f"bad_{index}"))
                self.assertEqual(rejected["status"], "rejected")
                self.assertIn("field", rejected["issues"][0])
                self.assertIsNone(rejected["case_snapshot"])
        self.assertEqual(self.read(), self.snapshot)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM events").fetchone()[0], 0)
            count_before = connection.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
        rejected = self.service.create_case(self.token, dict(self.create, event_id="invalid_create", intake={"needs": ["unsure", "shelter"]}))
        self.assertEqual(rejected["status"], "rejected")
        with closing(sqlite3.connect(self.path)) as connection, connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM cases").fetchone()[0], count_before)

    def test_household_authorization_and_channels_apply_to_intake(self):
        other = self.service.create_session()["session_token"]
        command = self.command({"needs": ["shelter"]})
        for token, channel in ((other, "dashboard"), (self.token, "system"), (self.token, "operator")):
            rejected = self.service.execute(token, dict(command, channel=channel))
            self.assertEqual(rejected["status"], "rejected")
            self.assertIsNone(rejected["case_snapshot"])
        self.assertEqual(self.read(), self.snapshot)

    def test_handlers_are_deterministic_and_leave_input_snapshot_untouched(self):
        saved = copy.deepcopy(self.snapshot)
        payload = {"needs": ["lost_documents"], "household_group": ["children_with_me", "other_adults_with_me"]}
        first = with_intake(self.snapshot, payload, REPORTED)
        second = with_intake(self.snapshot, payload, REPORTED)
        self.assertEqual(first, second)
        self.assertEqual(self.snapshot, saved)

    def test_storage_failure_rolls_back_all_intake_fields_and_audit(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("CREATE TRIGGER fail_intake BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END")
        command = self.command({"crisis_type": "flood", "needs": ["shelter", "food_water"]})
        self.assertEqual(self.service.execute(self.token, command)["status"], "unavailable")
        self.assertEqual(self.read(), self.snapshot)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM events").fetchone()[0], 0)
            connection.execute("DROP TRIGGER fail_intake")
        applied = self.service.execute(self.token, command)
        self.assertEqual(applied["status"], "applied")
        self.assertEqual(len(applied["case_snapshot"]["needs"]), 2)

    def test_legacy_database_upgrade_preserves_session_case_and_replay(self):
        original = self.command({}, "legacy_fact")
        original.update(type="fact.correct", payload={"fact_key": "mobility", "value": "no_car", "observed_at": REPORTED})
        self.service.execute(self.token, original)
        # Rebuild only the event table with the exact columns from the first slice.
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.executescript("""
                ALTER TABLE events RENAME TO current_events;
                CREATE TABLE events (
                    case_id TEXT NOT NULL REFERENCES cases(case_id), event_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL, command_json TEXT NOT NULL,
                    first_received_at TEXT NOT NULL, applied_received_at TEXT,
                    applied_version INTEGER, before_fact_json TEXT,
                    PRIMARY KEY (case_id, event_id)
                );
                INSERT INTO events SELECT case_id, event_id, fingerprint, command_json,
                    first_received_at, applied_received_at, applied_version, before_fact_json FROM current_events;
                DROP TABLE current_events;
            """)
        restarted = CaseService(self.path, clock=lambda: NOW)
        replay = restarted.execute(self.token, original)
        self.assertEqual(replay["status"], "already_applied")
        self.assertEqual(replay["applied_case_version"], 2)
        self.assertEqual(replay["case_snapshot"]["facts"]["mobility"]["value"], "no_car")
        self.assertEqual(restarted.create_case(self.token, self.create)["case_snapshot"]["case_version"], 2)
        updated = restarted.execute(self.token, self.command({"needs": ["food_water"]}, "after_upgrade", 2))
        self.assertEqual(updated["status"], "applied")
        with closing(sqlite3.connect(self.path)) as connection, connection:
            self.assertIsNone(connection.execute("SELECT before_case_json FROM events WHERE event_id='legacy_fact'").fetchone()[0])
            self.assertEqual(json.loads(connection.execute("SELECT before_case_json FROM events WHERE event_id='after_upgrade'").fetchone()[0])["case_version"], 2)
        CaseService(self.path, clock=lambda: NOW)  # Repeated startup does not repeat the migration.

    def test_concurrent_intakes_reconcile_without_losing_either_need(self):
        commands = [self.command({"needs": ["shelter"]}, "a"), self.command({"needs": ["food_water"]}, "b")]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda command: self.service.execute(self.token, command), commands))
        self.assertCountEqual([result["status"] for result in results], ["applied", "conflict"])
        for command, result in zip(commands, results):
            if result["status"] == "conflict":
                self.assertEqual(self.service.execute(self.token, dict(command, expected_case_version=2))["status"], "applied")
        self.assertCountEqual([need["kind"] for need in self.read()["needs"]], ["shelter", "food_water"])
        self.assertEqual(self.read()["case_version"], 3)


if __name__ == "__main__":
    unittest.main()
