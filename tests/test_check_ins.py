"""Synthetic C07/C12 tests. Import no provider/configuration or live service."""

import copy
import json
import unittest
from dataclasses import replace
from pathlib import Path

from backend.stillhere.check_ins import (
    AUTHORIZATION_REQUIREMENTS, Authority, CheckInError, CheckInProcessor,
    apply_command, empty_state, operator_projection, process_due, validate,
)
from backend.stillhere.check_ins.demo import run_demo


NOW = "2026-10-11T10:00:00Z"
DUE = "2026-10-11T11:00:00Z"
GRACE = "2026-10-11T11:30:00Z"
LATE = "2026-10-11T12:00:00Z"
NEXT = "2026-10-11T13:00:00Z"


class CheckInsTests(unittest.TestCase):
    def setUp(self):
        self.state = empty_state("case_synthetic")
        self.user = Authority("case_synthetic", "household", "household_synthetic",
                              frozenset({"check_in.write", "help.write", "location.write"}), True)
        self.worker = Authority("case_synthetic", "worker", "worker_synthetic", frozenset({"check_in.process"}))
        self.operator = Authority("case_synthetic", "operator", "operator_one",
                                  frozenset({"follow_up.read", "follow_up.write", "location.read", "needs.read"}))
        self.event_counter = 0

    def command(self, kind, payload, reported_at=NOW, received_at=None, caller=None, event_id=None):
        self.event_counter += 1
        before = copy.deepcopy(self.state)
        result = apply_command(self.state, kind, payload, event_id=event_id or f"event_{self.event_counter}",
                               reported_at=reported_at, received_at=received_at or reported_at, caller=caller or self.user)
        self.assertEqual(self.state, before, "Pure commands must not mutate caller state")
        self.state = result["state"]
        self.assertTrue(all(effect["simulation"] is True for effect in result["effects"]))
        return result

    def enroll(self, **changes):
        payload = {"consent": True, "follow_up_consent": True, "due_at": DUE, "time_zone": "America/Chicago",
                   "grace_minutes": 30, "channel": "text_simulator", "permitted_need_ids": ["need_shelter"]}
        payload.update(changes)
        return self.command("check_in.enroll", payload)

    def tick(self, now):
        before = copy.deepcopy(self.state)
        result = process_due(self.state, now=now, caller=self.worker)
        self.assertEqual(self.state, before)
        self.state = result["state"]
        return result

    def occurrence(self):
        return next(item for item in self.state["check_in"]["occurrences"]
                    if item["id"] == self.state["check_in"]["current_occurrence_id"])

    def request(self):
        return self.state["follow_ups"][0]

    def assign(self, when=GRACE):
        return self.command("follow_up.acknowledge", {"request_id": self.request()["id"]}, when, caller=self.operator)

    def record(self, kind="attempt", when=LATE, **changes):
        payload = {"request_id": self.request()["id"], "kind": kind, "simulation": True,
                   "unresolved_need_ids": ["need_shelter"], "next_action": "Review the explicit report."}
        if kind == "attempt":
            payload.update(channel="phone_simulator", result="no_reply")
        else:
            payload.update(outcome="needs_follow_up")
        payload.update(changes)
        return self.command("follow_up.record", payload, when, caller=self.operator)

    def share(self, when=NOW, **changes):
        payload = {"consent": True, "source": "user_entered", "place": "Synthetic community center",
                   "observed_at": NOW, "purpose": "simulated_follow_up", "recipients": "assigned_handler"}
        payload.update(changes)
        return self.command("location.share", payload, when)

    def view(self, caller=None, when=LATE, needs=()):
        before = copy.deepcopy(self.state)
        result = operator_projection(self.state, caller=caller or self.operator, now=when, relevant_needs=needs)
        self.assertEqual(before, self.state)
        return result

    def assert_error(self, code, operation):
        before = copy.deepcopy(self.state)
        with self.assertRaises(CheckInError) as caught:
            operation()
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(before, self.state, "Rejections must not mutate caller state")

    def test_full_synthetic_demonstration(self):
        frames = {frame["label"]: frame for frame in run_demo()}
        self.assertEqual(frames["reminder"]["state"]["check_in"]["status"], "reminder_attempted")
        self.assertEqual(frames["overdue"]["state"]["follow_ups"][0]["condition"], "unknown")
        self.assertFalse(frames["duplicate_tick"]["changed"])
        pending = frames["offline_pending"]
        self.assertEqual(pending["state"]["check_in"]["status"], "overdue")
        self.assertIsNone(pending["state"]["check_in"]["last_report"])
        reply = frames["offline_reply"]
        self.assertNotEqual(reply["state"]["check_in"]["last_report"]["reported_at"], reply["state"]["check_in"]["last_report"]["received_at"])
        self.assertEqual(reply["state"]["follow_ups"][0]["status"], "contact_attempted")
        self.assertEqual([effect["operator_id"] for effect in reply["effects"] if effect["kind"] == "reviewer_update"], ["operator_synthetic"])
        self.assertEqual(frames["reschedule"]["state"]["check_in"]["status"], "scheduled")
        self.assertFalse(frames["paused_tick"]["changed"])
        projection = frames["operator_view"]["projection"]
        self.assertIsNone(projection["reviews"][0]["shared_location"])
        self.assertEqual(projection["reviews"][0]["status"], "outcome_recorded")
        self.assertEqual(projection["reviews"][0]["unresolved_need_ids"], ["need_shelter"])
        for frame in frames.values():
            for effect in frame.get("effects", []):
                self.assertIs(effect["simulation"], True)

    def test_declined_or_missing_consent_and_model_authority_are_rejected(self):
        for changes in ({"consent": False}, {"consent": "true"}, {"follow_up_consent": False}):
            self.assert_error("invalid_input", lambda: self.enroll(**changes))
        self.assert_error("consent_required", lambda: self.command("check_in.enroll", {
            "consent": True, "follow_up_consent": True, "due_at": DUE, "time_zone": "UTC", "grace_minutes": 30,
            "channel": "in_app"}, caller=replace(self.user, explicit_user_action=False)))
        self.assert_error("consent_required", lambda: self.command("location.share", {
            "consent": True, "source": "user_entered", "place": "Synthetic", "observed_at": NOW,
            "purpose": "simulated_follow_up", "recipients": "case_handlers"}, caller=replace(self.user, explicit_user_action=False)))

    def test_no_enrollment_or_login_based_processing(self):
        self.assertFalse(self.tick(NEXT)["changed"])
        self.assertEqual(self.state["follow_ups"], [])
        self.assert_error("unsupported_command", lambda: self.command("login", {}))

    def test_exact_due_and_grace_boundaries_and_duplicate_ticks(self):
        self.enroll()
        self.assertFalse(self.tick("2026-10-11T10:59:59Z")["changed"])
        due = self.tick(DUE)
        self.assertEqual([effect["kind"] for effect in due["effects"]], ["reminder_simulated"])
        self.assertEqual(self.occurrence()["condition"], "unknown")
        self.assertFalse(self.tick(DUE)["changed"])
        self.assertFalse(self.tick("2026-10-11T11:29:59Z")["changed"])
        grace = self.tick(GRACE)
        self.assertEqual([effect["kind"] for effect in grace["effects"]], ["review_requested"])
        for now in (GRACE, LATE, NEXT):
            self.assertEqual(self.tick(now)["effects"], [])
        self.assertEqual(len(self.occurrence()["attempts"]), 1)
        self.assertEqual(len(self.state["follow_ups"]), 1)

    def test_delayed_and_zero_grace_ticks_catch_up_once(self):
        for grace in (0, 30):
            self.state = empty_state("case_synthetic")
            self.enroll(grace_minutes=grace)
            result = self.tick(LATE)
            self.assertEqual({effect["kind"] for effect in result["effects"]}, {"reminder_simulated", "review_requested"})
            self.assertEqual(self.request()["received_at"], LATE)
            self.assertEqual(self.occurrence()["attempts"][0]["scheduled_at"], DUE)
            self.assertFalse(self.tick(LATE)["changed"])

    def test_injected_clock_sampled_once_and_backward_tick_never_regresses(self):
        self.enroll()
        calls = []
        def clock():
            calls.append(1)
            return LATE
        result = CheckInProcessor(clock).process(self.state, caller=self.worker)
        self.state = result["state"]
        self.assertEqual(len(calls), 1)
        self.assertFalse(self.tick(DUE)["changed"])
        self.assertEqual(self.occurrence()["status"], "overdue")

    def test_round_trip_restart_and_same_snapshot_have_stable_effect_ids(self):
        self.enroll()
        first = process_due(self.state, now=LATE, caller=self.worker)
        retry = process_due(json.loads(json.dumps(self.state)), now=NEXT, caller=self.worker)
        self.assertEqual([effect["id"] for effect in first["effects"]], [effect["id"] for effect in retry["effects"]])
        self.assertEqual(first["state"]["follow_ups"][0]["id"], retry["state"]["follow_ups"][0]["id"])
        self.state = json.loads(json.dumps(first["state"]))
        self.assertFalse(self.tick(NEXT)["changed"])

    def test_duplicate_command_and_changed_intent_or_actor(self):
        payload = {"consent": True, "message": "Synthetic help", "permitted_need_ids": ["need_shelter"]}
        result = self.command("help.request", payload, event_id="stable_help")
        again = self.command("help.request", payload, received_at=LATE, event_id="stable_help")
        self.assertTrue(again["duplicate"])
        self.assertFalse(again["changed"])
        self.assertEqual(again["effects"], [])
        self.assertEqual(result["state"], again["state"])
        self.assert_error("event_reused", lambda: self.command("help.request", {**payload, "message": "Changed"}, event_id="stable_help"))
        self.assert_error("event_reused", lambda: self.command("help.request", payload, caller=replace(self.user, subject_id="other_user"), event_id="stable_help"))

    def test_authorize_before_duplicate_lookup_and_all_case_boundaries(self):
        self.enroll()
        for caller in (replace(self.user, case_id="other_case"), self.operator, replace(self.user, permissions=frozenset())):
            self.assert_error("forbidden", lambda: self.command("check_in.pause", {"intent": "pause"}, caller=caller))
        self.assert_error("forbidden", lambda: process_due(self.state, now=LATE, caller=self.user))
        self.assert_error("forbidden", lambda: self.view(caller=self.user))
        self.assert_error("forbidden", lambda: process_due(self.state, now=LATE, caller=replace(self.worker, case_id="other_case")))
        self.assert_error("forbidden", lambda: apply_command(self.state, "check_in.enroll", {}, event_id="event_1", reported_at=NOW, received_at=LATE, caller=replace(self.user, case_id="other_case")))

    def test_immediate_help_without_enrollment_requires_explicit_request(self):
        result = self.command("help.request", {"consent": True, "message": "Synthetic shelter request"})
        self.assertEqual({effect["kind"] for effect in result["effects"]}, {"review_requested", "urgent_help_required"})
        self.assertFalse(self.state["check_in"]["enrolled"])
        self.assertEqual(self.request()["status"], "requested")
        self.assertEqual(self.request()["condition"], "unknown")
        self.assert_error("invalid_input", lambda: self.command("help.request", {"message": "No permission"}))

    def test_need_help_reply_creates_immediate_review_and_no_due_outreach(self):
        self.enroll()
        result = self.command("check_in.reply", {"occurrence_id": self.occurrence()["id"], "reply": "need_help"})
        self.assertIn("urgent_help_required", [effect["kind"] for effect in result["effects"]])
        self.assertEqual(self.occurrence()["status"], "answered")
        self.assertEqual(self.occurrence()["condition"], "need_help")
        self.assertFalse(self.tick(NEXT)["changed"])

    def test_okay_reply_is_report_not_verification_and_does_not_recur(self):
        self.enroll()
        self.command("check_in.reply", {"occurrence_id": self.occurrence()["id"], "reply": "okay_for_now"})
        self.assertEqual(self.state["check_in"]["status"], "answered")
        self.assertEqual(len(self.state["check_in"]["occurrences"]), 1)
        self.assertFalse(self.tick(NEXT)["changed"])
        self.assertEqual(self.state["follow_ups"], [])

    def test_check_later_requires_selected_future_time_and_preserves_review(self):
        self.enroll()
        self.tick(GRACE)
        self.assign()
        old = self.occurrence()["id"]
        self.assert_error("invalid_schedule", lambda: self.command("check_in.reply", {"occurrence_id": old, "reply": "check_later"}, LATE))
        self.assert_error("invalid_schedule", lambda: self.command("check_in.reply", {"occurrence_id": old, "reply": "check_later", "next_due_at": LATE}, LATE))
        self.command("check_in.reply", {"occurrence_id": old, "reply": "check_later", "next_due_at": NEXT}, LATE)
        self.assertNotEqual(self.occurrence()["id"], old)
        self.assertEqual(self.request()["status"], "assigned_acknowledged")
        self.assertEqual(self.state["check_in"]["occurrences"][0]["status"], "answered")
        self.assertEqual(self.state["check_in"]["status"], "scheduled")

    def test_rescheduling_cancels_previous_pending_occurrence(self):
        self.enroll()
        old = self.occurrence()["id"]
        self.enroll(due_at=NEXT)
        self.tick(LATE)
        self.assertEqual(self.state["check_in"]["occurrences"][0]["status"], "canceled")
        self.assertEqual(self.state["follow_ups"], [])
        self.assertNotEqual(self.occurrence()["id"], old)
        self.tick("2026-10-11T13:30:00Z")
        self.assertEqual(len(self.state["follow_ups"]), 1)

    def test_late_reply_preserves_owner_outcome_and_unresolved_need(self):
        self.enroll()
        self.tick(GRACE)
        self.assign()
        self.record(kind="outcome")
        result = self.command("check_in.reply", {"occurrence_id": self.occurrence()["id"], "reply": "okay_for_now"},
                              reported_at="2026-10-11T11:10:00Z", received_at=NEXT)
        report = self.state["check_in"]["last_report"]
        self.assertTrue(report["late"])
        self.assertEqual(report["reported_at"], "2026-10-11T11:10:00Z")
        self.assertEqual(report["received_at"], NEXT)
        self.assertEqual(self.request()["status"], "outcome_recorded")
        self.assertEqual(self.request()["unresolved_need_ids"], ["need_shelter"])
        notification = next(effect for effect in result["effects"] if effect["kind"] == "reviewer_update")
        self.assertEqual(notification["operator_id"], self.operator.subject_id)
        replay = self.command("check_in.reply", {"occurrence_id": self.occurrence()["id"], "reply": "okay_for_now"},
                              reported_at=report["reported_at"], received_at=NEXT, event_id=report["event_id"])
        self.assertEqual(replay["effects"], [])
        self.assertEqual(len(self.request()["report_updates"]), 1)

    def test_old_reply_does_not_replace_new_schedule_or_latest_report(self):
        self.enroll()
        first = self.occurrence()["id"]
        self.enroll(due_at=NEXT)
        second = self.occurrence()["id"]
        self.command("check_in.reply", {"occurrence_id": second, "reply": "okay_for_now"}, LATE)
        self.command("check_in.reply", {"occurrence_id": first, "reply": "need_help"}, reported_at=DUE, received_at=NEXT)
        self.assertEqual(self.state["check_in"]["current_occurrence_id"], second)
        self.assertEqual(self.state["check_in"]["last_report"]["occurrence_id"], second)
        self.assertEqual(self.state["check_in"]["status"], "answered")
        self.assert_error("schedule_conflict", lambda: self.command("check_in.reply", {"occurrence_id": first, "reply": "check_later", "next_due_at": "2026-10-11T14:00:00Z"}, NEXT))

    def test_older_report_preserved_without_regressing_occurrence_condition(self):
        self.enroll()
        occurrence_id = self.occurrence()["id"]
        self.command("check_in.reply", {"occurrence_id": occurrence_id, "reply": "need_help"}, LATE)
        self.command("check_in.reply", {"occurrence_id": occurrence_id, "reply": "okay_for_now"}, reported_at=DUE, received_at=NEXT)
        self.assertEqual(self.occurrence()["condition"], "need_help")
        self.assertEqual(len(self.occurrence()["reports"]), 2)
        self.assertEqual(len(self.request()["report_updates"]), 2)

    def test_older_check_later_cannot_replace_newer_explicit_reply(self):
        self.enroll()
        occurrence_id = self.occurrence()["id"]
        self.command("check_in.reply", {"occurrence_id": occurrence_id, "reply": "okay_for_now"}, LATE)
        self.assert_error("stale_control", lambda: self.command("check_in.reply", {
            "occurrence_id": occurrence_id, "reply": "check_later", "next_due_at": "2026-10-11T14:00:00Z"},
            reported_at=DUE, received_at=NEXT))

    def test_bounded_receipts_reject_atomically_instead_of_dropping_replay(self):
        self.state["processed_events"] = {f"reserved_{index}": {"fingerprint": "0" * 64, "received_at": NOW} for index in range(4096)}
        self.assert_error("invalid_input", lambda: self.command("location.clear", {}, LATE))
        self.assertEqual(len(self.state["processed_events"]), 4096)

    def test_help_for_overdue_occurrence_reuses_review_and_owner(self):
        self.enroll()
        self.tick(GRACE)
        self.assign()
        request_id = self.request()["id"]
        self.command("help.request", {"consent": True, "message": "New explicit help", "occurrence_id": self.occurrence()["id"]}, LATE)
        self.assertEqual(len(self.state["follow_ups"]), 1)
        self.assertEqual(self.request()["id"], request_id)
        self.assertEqual(self.request()["assignment"]["operator_id"], self.operator.subject_id)
        self.assertEqual(self.request()["message"], "New explicit help")

    def test_explicit_help_after_outcome_creates_new_unassigned_review(self):
        for kind in ("help.request", "check_in.reply"):
            self.state = empty_state("case_synthetic")
            self.enroll()
            self.tick(GRACE)
            self.assign()
            self.record(kind="outcome", when=LATE)
            previous = copy.deepcopy(self.request())
            occurrence_id = self.occurrence()["id"]
            payload = {"occurrence_id": occurrence_id}
            if kind == "help.request":
                payload.update(consent=True, message="New explicit help after review")
            else:
                payload.update(reply="need_help")
            result = self.command(kind, payload, NEXT)
            self.assertEqual(len(self.state["follow_ups"]), 2)
            self.assertEqual(self.request()["assignment"], previous["assignment"])
            self.assertEqual(self.request()["outcomes"], previous["outcomes"])
            self.assertEqual(self.request()["status"], "outcome_recorded")
            new = self.state["follow_ups"][1]
            self.assertEqual(new["status"], "requested")
            self.assertIsNone(new["assignment"])
            self.assertNotEqual(new["id"], previous["id"])
            self.assertIn("review_requested", [effect["kind"] for effect in result["effects"]])
            self.assertEqual(len({effect["id"] for effect in result["effects"]}), len(result["effects"]))
            if kind == "check_in.reply":
                self.assertTrue(any(effect.get("operator_id") == self.operator.subject_id for effect in result["effects"]))
            self.assertEqual(self.tick("2026-10-11T14:00:00Z")["effects"], [])

    def test_need_context_generator_is_available_to_each_review(self):
        for index in range(2):
            self.command("help.request", {"consent": True, "message": f"Synthetic help {index}", "permitted_need_ids": ["need_shelter"]})
        needs = (need for need in [{"id": "need_shelter", "kind": "shelter", "state": "uncovered", "reported_urgency": "essentials_today"}])
        projection = self.view(needs=needs)
        self.assertEqual([len(review["relevant_needs"]) for review in projection["reviews"]], [1, 1])

    def test_timestamp_subset_and_grace_overflow_fail_cleanly(self):
        for due in ("2026-W41-7T11:00:00Z", "2026-10-11T110000Z", "2026-10-11T11:00:00.123456789Z"):
            self.assert_error("invalid_input", lambda: self.enroll(due_at=due))
        self.assert_error("invalid_schedule", lambda: self.enroll(due_at="9999-12-31T23:59:00Z"))

    def test_pause_stop_prevent_scheduled_attempts_preserve_open_review(self):
        for intent in ("pause", "stop"):
            self.state = empty_state("case_synthetic")
            self.enroll()
            self.tick(GRACE)
            self.command("check_in.pause", {"intent": intent}, LATE)
            self.assertFalse(self.tick(NEXT)["changed"])
            self.assertFalse(self.state["check_in"]["consent"]["active"])
            self.assertEqual(self.request()["status"], "requested")
            self.assign(LATE)
            self.assertEqual(len(self.view()["reviews"]), 1)

    def test_pause_before_due_and_reply_after_pause_do_not_restart(self):
        self.enroll()
        occurrence_id = self.occurrence()["id"]
        self.command("check_in.pause", {"intent": "pause"}, DUE)
        self.assertFalse(self.tick(NEXT)["changed"])
        self.command("check_in.reply", {"occurrence_id": occurrence_id, "reply": "okay_for_now"}, LATE)
        self.assertEqual(self.state["check_in"]["status"], "paused")
        self.assertFalse(self.state["check_in"]["enrolled"])
        self.assert_error("schedule_conflict", lambda: self.command("check_in.reply", {"occurrence_id": occurrence_id, "reply": "check_later", "next_due_at": NEXT}, LATE))

    def test_older_offline_enrollment_cannot_revoke_newer_pause(self):
        self.enroll()
        self.command("check_in.pause", {"intent": "pause"}, LATE)
        self.assert_error("stale_control", lambda: self.enroll(due_at=NEXT))

    def test_operator_assignment_requires_scoped_identity_and_cannot_be_stolen(self):
        self.enroll()
        self.tick(GRACE)
        self.assert_error("assignment_required", self.record)
        self.assert_error("forbidden", lambda: self.command("follow_up.acknowledge", {"request_id": self.request()["id"]}, GRACE))
        self.assign()
        same_owner = self.assign(LATE)
        self.assertEqual(same_owner["effects"], [])
        self.assertEqual(self.request()["assignment"]["acknowledged_at"], GRACE)
        self.assert_error("already_assigned", lambda: self.command("follow_up.acknowledge", {"request_id": self.request()["id"]}, LATE, caller=replace(self.operator, subject_id="operator_two")))
        self.assert_error("invalid_input", lambda: self.command("follow_up.acknowledge", {"request_id": self.request()["id"], "operator_id": "spoofed"}, LATE, caller=self.operator))
        self.record()
        self.assertEqual(self.request()["attempts"][0]["operator_id"], self.operator.subject_id)

    def test_operator_attempt_and_outcome_are_idempotent_simulated_and_scoped(self):
        self.enroll()
        self.tick(GRACE)
        self.assign()
        self.assert_error("invalid_input", lambda: self.record(simulation=False))
        self.assert_error("invalid_input", lambda: self.record(channel="live_sms"))
        self.assert_error("consent_required", lambda: self.record(unresolved_need_ids=["private_money_need"]))
        attempt = self.record()
        event_id = next(reversed(self.state["processed_events"]))
        replay = self.command("follow_up.record", {"request_id": self.request()["id"], "kind": "attempt", "simulation": True,
                 "unresolved_need_ids": ["need_shelter"], "next_action": "Review the explicit report.", "channel": "phone_simulator", "result": "no_reply"}, LATE, caller=self.operator, event_id=event_id)
        self.assertTrue(replay["duplicate"])
        self.assertEqual(len(self.request()["attempts"]), 1)
        self.assertEqual(attempt["effects"][0]["kind"], "contact_simulated")
        self.record(kind="outcome", when=NEXT)
        self.assertEqual(self.request()["status"], "outcome_recorded")
        self.assert_error("review_complete", lambda: self.record(when=NEXT))
        self.assert_error("stale_operator_record", lambda: self.record(kind="outcome", when=LATE))

    def test_location_projection_requires_separate_permission_and_assigned_recipient(self):
        self.enroll()
        self.share()
        self.tick(GRACE)
        self.assertIsNone(self.view()["reviews"][0]["shared_location"])
        self.assign()
        location = self.view()["reviews"][0]["shared_location"]
        self.assertEqual(location["age_seconds"], 7200)
        self.assertIs(location["verified_current_destination"], False)
        self.assertIsNone(self.view(caller=replace(self.operator, subject_id="operator_two"))["reviews"][0]["shared_location"])
        self.assertIsNone(self.view(caller=replace(self.operator, permissions=frozenset({"follow_up.read"})))["reviews"][0]["shared_location"])

    def test_case_handler_recipient_and_expiry_are_explicit(self):
        self.command("help.request", {"consent": True, "message": "Synthetic help"})
        self.share(recipients="case_handlers", expires_at=LATE)
        self.assertIsNotNone(self.view(when=GRACE)["reviews"][0]["shared_location"])
        self.assertIsNone(self.view(when=LATE)["reviews"][0]["shared_location"])

    def test_clear_removes_all_active_location_access_and_old_replay_never_restores_it(self):
        self.enroll()
        shared = self.share()
        share_event = next(reversed(self.state["processed_events"]))
        self.tick(GRACE)
        self.assign()
        self.command("location.clear", {}, LATE)
        self.assertIsNone(self.view()["reviews"][0]["shared_location"])
        self.assertNotIn("Synthetic community center", json.dumps(self.state))
        payload = {key: value for key, value in shared["state"]["shared_location"].items() if key not in {"id", "reported_at", "received_at"}}
        replay = self.command("location.share", payload, received_at=NEXT, event_id=share_event)
        self.assertTrue(replay["duplicate"])
        self.assertIsNone(self.state["shared_location"])
        self.assert_error("stale_control", lambda: self.command("location.share", payload, reported_at=DUE, received_at=NEXT))
        self.assertEqual(self.request()["status"], "assigned_acknowledged")

    def test_location_input_validation_and_observation_receipt_times(self):
        self.share(when=LATE, source="device_fix", latitude=40.1, longitude=-105.1, accuracy_meters=30)
        self.assertEqual(self.state["shared_location"]["observed_at"], NOW)
        self.assertEqual(self.state["shared_location"]["received_at"], LATE)
        for changes, code in (({"latitude": 100}, "invalid_input"), ({"latitude": 40}, "invalid_location"),
                              ({"observed_at": NEXT}, "invalid_time"), ({"expires_at": NOW}, "invalid_schedule"),
                              ({"accuracy_meters": 1}, "invalid_location"), ({"consent": False}, "invalid_input"),
                              ({"source": "background_tracker"}, "invalid_input")):
            self.state = empty_state("case_synthetic")
            self.assert_error(code, lambda: self.share(**changes))

    def test_limited_projection_discards_ledger_identity_chat_and_unconsented_needs(self):
        self.enroll()
        self.tick(GRACE)
        permitted = {"id": "need_shelter", "kind": "shelter", "state": "uncovered", "reported_urgency": "essentials_today",
                     "financial_ledger": "PRIVATE_LEDGER", "identity": "PRIVATE_IDENTITY", "notes": "PRIVATE_CHAT"}
        other = {"id": "need_money", "kind": "managing_money", "private_value": "PRIVATE_MONEY"}
        projection = self.view(needs=[permitted, other])
        serialized = json.dumps(projection)
        for token in ("PRIVATE_LEDGER", "PRIVATE_IDENTITY", "PRIVATE_CHAT", "PRIVATE_MONEY"):
            self.assertNotIn(token, serialized)
        self.assertEqual(projection["reviews"][0]["relevant_needs"], [{key: permitted[key] for key in ("id", "kind", "state", "reported_urgency")}])
        self.assertEqual(self.view(caller=replace(self.operator, permissions=frozenset({"follow_up.read"})), needs=[permitted])["reviews"][0]["relevant_needs"], [])
        self.assertNotIn("processed_events", projection)

    def test_invalid_time_zone_schedule_and_untrusted_fields_are_rejected(self):
        for changes in ({"due_at": NOW}, {"grace_minutes": -1}, {"grace_minutes": True},
                        {"time_zone": "Invented/Zone"}, {"channel": "sms"}, {"due_at": "2026-10-11T11:00:00-05:00"}):
            with self.assertRaises(CheckInError):
                self.enroll(**changes)
        self.assert_error("invalid_time", lambda: self.command("check_in.pause", {"intent": "pause"}, reported_at=LATE, received_at=NOW))
        self.assert_error("invalid_input", lambda: self.command("location.clear", {"operator_id": "spoofed"}))

    def test_unknown_occurrence_and_request_ids_are_not_cross_case_handles(self):
        self.assert_error("not_found", lambda: self.command("check_in.reply", {"occurrence_id": "other_case_occurrence", "reply": "okay_for_now"}))
        self.assert_error("not_found", lambda: self.command("follow_up.acknowledge", {"request_id": "other_case_review"}, caller=self.operator))

    def test_schema_proposal_and_transition_requirements_are_separate_from_public_contract(self):
        schema_path = Path(__file__).resolve().parents[1] / "contracts/parallel/check-ins.schema.json"
        schema = json.loads(schema_path.read_text())
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(AUTHORIZATION_REQUIREMENTS["follow_up.record"]["role"], "operator")
        self.assertEqual(AUTHORIZATION_REQUIREMENTS["process_due"]["role"], "worker")
        validate("State", self.state)
        invalid = copy.deepcopy(self.state)
        invalid["financial_ledger"] = []
        self.assert_error("invalid_input", lambda: validate("State", invalid))


if __name__ == "__main__":
    unittest.main()
