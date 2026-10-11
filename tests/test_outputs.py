"""Independent synthetic output contracts; no providers, configuration or writes."""

import copy
import json
import math
import unittest
from pathlib import Path

from backend.stillhere.contracts import empty_case, validate
from backend.stillhere.outputs import (
    KIND_DOMAINS, OutputValidationError, build_dashboard_descriptor, build_follow_up_question, prepare_dashboard_publication,
    prepare_structured_reply, validate_dashboard_publication, validate_shape,
    validate_structured_reply,
)


NOW = "2026-10-11T12:00:00Z"
LATER = "2026-10-11T12:01:00Z"


def descriptor(kind="task_list", records=None, identifier="component_1", order=0):
    return {"id": identifier, "kind": kind, "record_ids": records or [], "display_order": order}


def question(identifier="question_transport", kind="single_choice"):
    return {"id": identifier, "kind": kind, "prompt": "Do you have transport for this step?",
            "allow_skip": True, "choices": [] if kind == "text" else
            [{"id": "choice_yes", "label": "Yes"}, {"id": "choice_unknown", "label": "Unsure"}]}


def synthetic_snapshot():
    snapshot = empty_case("synthetic_outputs", "America/Chicago", NOW)
    snapshot["case_version"] = 7
    snapshot["needs"] = [{"id": "need_food", "state": "unknown"}]
    snapshot["evidence"] = [{"id": "evidence_id", "state": "missing", "observed_at": NOW}]
    snapshot["sources"] = [{"id": "source_demo", "freshness": "current", "retrieved_at": NOW,
                             "expires_at": "2026-10-11T12:02:00Z", "data_mode": "seeded"}]
    snapshot["resources"] = {"state": "available", "items": [{"id": "resource_food", "source_ids": ["source_demo"],
                               "availability": {"state": "unknown", "observed_at": None}}], "notices": [],
                             "search": {"freshness": "current", "input_case_version": 7, "retrieved_at": NOW}}
    snapshot["plan"] = {"state": "provisional", "version": 1, "input_case_version": 7, "computed_at": NOW,
                        "actions": [{"id": "action_id", "status": "waiting", "input_freshness": "current",
                                     "source_ids": ["source_demo"]}], "blockers": [{"id": "blocker_evidence"}],
                        "questions": [{"node_id": "rule_node", "fact_key": "transport"}]}
    snapshot["applications"] = [{"id": "application_aid", "state": "user_reported", "observed_at": NOW}]
    snapshot["finance"].update(state="complete", input_case_version=7, computed_at=NOW,
        baseline={"scenario_id": "baseline", "state": "incomplete", "input_case_version": 7,
                  "opening_accessible_cents": None, "first_gap": None},
        scenarios=[{"scenario_id": "scenario_delayed", "state": "complete", "input_case_version": 7,
                    "ending_projected_position_cents": 28000}])
    snapshot["finance"]["ledger"].update(
        money_sources=[{"id": "cash_demo", "balance_cents": 30000, "as_of": NOW}],
        aid=[{"id": "aid_demo", "state": "unreceived", "amount_cents": None}],
        support=[{"id": "support_demo", "state": "confirmed", "observed_at": NOW}],
        expense_commitments=[{"id": "expense_food", "observed_at": NOW, "amount_cents": None}])
    snapshot["check_in"].update(enrolled=True, status="overdue",
                               schedule={"id": "schedule_demo", "status": "overdue", "observed_at": NOW},
                               last_report={"id": "report_demo", "state": "user_reported", "observed_at": NOW},
                               attempts=[{"id": "attempt_demo", "simulation": True}])
    snapshot["follow_ups"] = [{"id": "review_demo", "status": "requested", "simulation": True}]
    return snapshot


class DashboardOutputTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = synthetic_snapshot()

    def prepare(self, components, now=NOW):
        return prepare_dashboard_publication(self.snapshot, {"components": components}, now=now)

    def test_all_allowlisted_kinds_have_compatible_synthetic_records(self):
        examples = {"urgent_resource": ["resource_food"], "next_step": ["action_id"],
                    "task_list": ["action_id"], "blocker_controls": ["blocker_evidence", "action_id"],
                    "evidence_checklist": ["evidence_id"], "aid_tracker": ["application_aid", "aid_demo"],
                    "finance_overview": ["cash_demo", "baseline", "expense_food", "support_demo"],
                    "scenario_comparison": ["scenario_delayed"], "check_in": ["schedule_demo", "report_demo", "review_demo"],
                    "source_details": ["source_demo"]}
        result = self.prepare([descriptor(kind, records, "component_" + kind, order)
                               for order, (kind, records) in enumerate(examples.items())])
        self.assertEqual(len(result["components"]), len(KIND_DOMAINS))
        validate_shape("DashboardPublication", result)
        # Descriptor shape is already in the shared contract.
        for component in result["components"]:
            validate("DashboardDescriptor", component)

    def test_descriptor_builder_validates_and_detaches_references(self):
        identifiers = ["action_id"]
        built = build_dashboard_descriptor(self.snapshot, component_id="component_a", kind="next_step",
                                          record_ids=identifiers, display_order=3, now=NOW)
        self.assertEqual(built, descriptor("next_step", identifiers, "component_a", 3))
        identifiers.clear()
        self.assertEqual(built["record_ids"], ["action_id"])
        with self.assertRaises(OutputValidationError):
            build_dashboard_descriptor(self.snapshot, component_id="component_a", kind="next_step",
                                       record_ids=["absent"], display_order=0, now=NOW)

    def test_malformed_or_unrecognized_domain_states_remain_unknown(self):
        for state in ({"role": "operator"}, ["confirmed"], "invented_status"):
            self.snapshot["plan"]["state"] = state
            self.snapshot["plan"]["actions"][0]["status"] = state
            result = self.prepare([descriptor("task_list", ["action_id"])])
            self.assertEqual(result["component_states"][0]["state"], "unknown")
            self.assertEqual(result["component_states"][0]["record_states"][0]["state"], "unknown")

    def test_prepare_is_pure_and_detaches_arguments(self):
        before = copy.deepcopy(self.snapshot)
        arguments = {"components": [descriptor("next_step", ["action_id"])]}
        old_arguments = copy.deepcopy(arguments)
        result = prepare_dashboard_publication(self.snapshot, arguments, now=NOW)
        self.assertEqual(self.snapshot, before)
        self.assertEqual(arguments, old_arguments)
        result["components"][0]["record_ids"].append("unrelated")
        result["component_states"][0]["record_states"].clear()
        self.assertEqual(arguments, old_arguments)
        self.assertEqual(self.snapshot, before)

    def test_empty_and_partial_snapshots_do_not_invent_records(self):
        for snapshot in (empty_case("empty", "America/Chicago", NOW),
                         {"contract_version": "0.1", "case_id": "partial", "case_version": 1}):
            with self.subTest(case_id=snapshot["case_id"]):
                kinds = set(KIND_DOMAINS) - {"urgent_resource", "next_step", "scenario_comparison"}
                components = [descriptor(kind, [], "component_" + kind, order) for order, kind in enumerate(sorted(kinds))]
                result = prepare_dashboard_publication(snapshot, {"components": components}, now=NOW)
                self.assertTrue(all(row["freshness"] == "unknown" for row in result["component_states"]))
                self.assertTrue(all(row["record_states"] == [] for row in result["component_states"]))
                validate_dashboard_publication(snapshot, result, now=LATER)

    def test_prepared_descriptors_fit_existing_snapshot_components(self):
        snapshot = empty_case("synthetic_empty", "America/Chicago", NOW)
        prepared = prepare_dashboard_publication(snapshot, {"components": [descriptor()]}, now=NOW)
        projection = copy.deepcopy(snapshot)
        projection["components"] = prepared["components"]
        validate("CaseSnapshot", projection)
        self.assertEqual(snapshot["components"], [])

    def test_empty_resource_lookups_preserve_not_requested_no_match_and_failure(self):
        for state in ("not_requested", "no_match", "unavailable"):
            self.snapshot["resources"] = {"state": state, "items": [], "notices": []}
            # Empty actionable cards are invalid: retain retrieval state in the
            # snapshot instead of manufacturing a result ID to render failure.
            with self.assertRaises(OutputValidationError):
                self.prepare([descriptor("urgent_resource")])
            self.assertEqual(self.prepare([])["components"], [])
            self.assertEqual(self.snapshot["resources"]["state"], state)

    def test_dangling_reference_is_rejected(self):
        with self.assertRaises(OutputValidationError) as caught:
            self.prepare([descriptor("task_list", ["other_household_action"])])
        self.assertEqual(caught.exception.code, "dangling_reference")

    def test_kind_mismatch_rejected(self):
        for kind, wrong in (("next_step", "resource_food"), ("urgent_resource", "application_aid"),
                            ("scenario_comparison", "baseline"), ("check_in", "cash_demo"),
                            ("source_details", "action_id")):
            with self.subTest(kind=kind), self.assertRaises(OutputValidationError) as caught:
                self.prepare([descriptor(kind, [wrong])])
            self.assertEqual(caught.exception.code, "reference_kind")

    def test_unsupported_kinds_and_executable_payloads_are_rejected(self):
        for kind in ("html", "script", "dispatch_help", "bank_transfer", "operator_queue", "print_summary"):
            with self.subTest(kind=kind), self.assertRaises(OutputValidationError):
                self.prepare([descriptor(kind)])
        for key in ("html", "javascript", "onClick", "url", "commands", "consent", "role", "amount_cents", "freshness"):
            payload = descriptor()
            payload[key] = "<script>grantAuthority()</script>"
            with self.subTest(key=key), self.assertRaises(OutputValidationError):
                self.prepare([payload])

    def test_model_arguments_cannot_choose_case_version_time_or_authority(self):
        for key in ("case_id", "input_case_version", "prepared_at", "session_token", "channel", "role", "consent"):
            with self.subTest(key=key), self.assertRaises(OutputValidationError):
                prepare_dashboard_publication(self.snapshot, {"components": [], key: "untrusted"}, now=NOW)

    def test_duplicate_component_reference_and_order_rejected(self):
        cases = ([descriptor(), descriptor(identifier="component_1", order=1)],
                 [descriptor(), descriptor(identifier="component_2", order=0)],
                 [descriptor(order=1), descriptor(identifier="component_2", order=0)],
                 [descriptor("task_list", ["action_id", "action_id"])])
        for components in cases:
            with self.subTest(components=components), self.assertRaises(OutputValidationError):
                self.prepare(components)

    def test_order_accepts_gaps_but_requires_integer_bounds(self):
        self.prepare([descriptor(order=2), descriptor(identifier="component_2", order=900)])
        for order in (-1, 1024, True, 0.0, "0"):
            with self.subTest(order=order), self.assertRaises(OutputValidationError):
                self.prepare([descriptor(order=order)])

    def test_component_and_record_limits(self):
        self.prepare([descriptor(identifier="component_" + str(i), order=i) for i in range(16)])
        with self.assertRaises(OutputValidationError):
            self.prepare([descriptor(identifier="component_" + str(i), order=i) for i in range(17)])
        self.snapshot["evidence"] = [{"id": "evidence_" + str(i)} for i in range(25)]
        self.prepare([descriptor("evidence_checklist", [item["id"] for item in self.snapshot["evidence"][:24]])])
        with self.assertRaises(OutputValidationError):
            self.prepare([descriptor("evidence_checklist", [item["id"] for item in self.snapshot["evidence"]])])

    def test_ids_and_malformed_snapshot_collections_are_bounded(self):
        for identifier in ("", "x" * 129, "<script>", "hidden\x00id"):
            with self.subTest(identifier=identifier), self.assertRaises(OutputValidationError):
                self.prepare([descriptor(identifier=identifier)])
        for collection in (None, {}, [None], [{"id": "x"}] * 4097):
            snapshot = copy.deepcopy(self.snapshot)
            snapshot["applications"] = collection
            with self.assertRaises(OutputValidationError):
                prepare_dashboard_publication(snapshot, {"components": []}, now=NOW)

    def test_ambiguous_snapshot_id_cannot_resolve_to_different_domain(self):
        self.snapshot["applications"].append({"id": "action_id"})
        with self.assertRaises(OutputValidationError) as caught:
            self.prepare([descriptor("next_step", ["action_id"])])
        self.assertEqual(caught.exception.code, "ambiguous_reference")

    def test_untyped_legacy_blockers_are_not_guessed_record_ids(self):
        self.snapshot["plan"]["blockers"] = [{"node_id": "rule_node", "code": "unmet"}]
        self.prepare([descriptor("blocker_controls", ["action_id"])])
        with self.assertRaises(OutputValidationError):
            self.prepare([descriptor("blocker_controls", ["rule_node"])])

    def test_dangling_source_reference_is_rejected(self):
        self.snapshot["plan"]["actions"][0]["source_ids"] = ["missing_source"]
        with self.assertRaises(OutputValidationError) as caught:
            self.prepare([descriptor("next_step", ["action_id"])])
        self.assertEqual(caught.exception.code, "dangling_reference")

    def test_capacity_source_references_are_validated_and_contribute_freshness(self):
        capacity = self.snapshot["resources"]["items"][0]["availability"]
        capacity.update(state="confirmed_available", observed_at=NOW, source_ids=["absent_source"])
        with self.assertRaises(OutputValidationError):
            self.prepare([descriptor("urgent_resource", ["resource_food"])])
        capacity["source_ids"] = ["source_demo"]
        self.snapshot["sources"][0]["freshness"] = "stale"
        result = self.prepare([descriptor("urgent_resource", ["resource_food"])])
        self.assertEqual(result["component_states"][0]["freshness"], "stale")

    def test_unknown_availability_stays_unknown_even_when_listing_is_current(self):
        result = self.prepare([descriptor("urgent_resource", ["resource_food"])])
        row = result["component_states"][0]["record_states"][0]
        self.assertEqual(row["availability"], "unknown")
        self.assertEqual(row["freshness"], "unknown")

    def test_current_listing_and_explicit_capacity_do_not_infer_new_authority(self):
        resource = self.snapshot["resources"]["items"][0]
        resource["availability"] = {"state": "confirmed_unavailable", "observed_at": NOW, "source_ids": ["source_demo"]}
        result = self.prepare([descriptor("urgent_resource", ["resource_food"])])
        row = result["component_states"][0]["record_states"][0]
        self.assertEqual(row["freshness"], "current")
        self.assertEqual(row["availability"], "confirmed_unavailable")
        self.assertNotIn("commands", result)

    def test_capacity_without_timed_evidence_remains_unknown(self):
        for capacity in ("confirmed_available", {"state": "confirmed_available"},
                         {"state": "confirmed_available", "observed_at": NOW, "source_ids": []},
                         {"state": "confirmed_available", "observed_at": "2026-10-12T00:00:00Z", "source_ids": ["source_demo"]}):
            self.snapshot["resources"]["items"][0]["availability"] = capacity
            result = self.prepare([descriptor("urgent_resource", ["resource_food"])])
            row = result["component_states"][0]["record_states"][0]
            self.assertEqual(row["availability"], "unknown")
            self.assertEqual(row["freshness"], "unknown")

    def test_failed_lookup_with_cached_record_preserves_failure_and_data_mode(self):
        self.snapshot["resources"]["state"] = "unavailable"
        self.snapshot["resources"]["items"][0]["data_mode"] = "cached"
        result = self.prepare([descriptor("urgent_resource", ["resource_food"])])
        state = result["component_states"][0]
        self.assertEqual(state["state"], "unavailable")
        self.assertEqual(state["record_states"][0]["data_mode"], "cached")
        self.assertEqual(state["freshness"], "unknown")

    def test_finance_baseline_uses_existing_scenario_id_and_preserves_unknowns(self):
        before = copy.deepcopy(self.snapshot["finance"])
        result = self.prepare([descriptor("finance_overview", ["baseline", "cash_demo", "aid_demo"])])
        self.assertEqual(result["component_states"][0]["record_states"][0]["state"], "incomplete")
        self.assertEqual(self.snapshot["finance"], before)
        self.assertNotIn("amount_cents", json.dumps(result))

    def test_scenario_definitions_with_id_are_compatible(self):
        self.snapshot["finance"]["scenarios"] = [{"id": "scenario_input", "label": "Synthetic receipt"}]
        self.prepare([descriptor("scenario_comparison", ["scenario_input"])])

    def test_pending_old_and_future_finance_inputs_do_not_become_current(self):
        for field, value, expected in (("input_case_version", 6, "stale"), ("input_case_version", 8, "unknown"),
                                       ("input_case_version", True, "unknown"), ("state", "pending", "stale"),
                                       ("computed_at", None, "unknown"),
                                       ("computed_at", "2026-10-12T12:00:00Z", "unknown")):
            with self.subTest(field=field, value=value):
                snapshot = copy.deepcopy(self.snapshot)
                snapshot["finance"][field] = value
                result = prepare_dashboard_publication(snapshot, {"components": [descriptor("finance_overview", ["cash_demo"])]}, now=NOW)
                self.assertEqual(result["component_states"][0]["freshness"], expected)

    def test_per_action_staleness_survives_current_plan(self):
        self.snapshot["plan"]["actions"][0]["input_freshness"] = "stale"
        result = self.prepare([descriptor("next_step", ["action_id"])])
        self.assertEqual(result["component_states"][0]["freshness"], "stale")

    def test_expired_unknown_and_malformed_sources_are_honest(self):
        for field, value, expected in (("expires_at", NOW, "stale"), ("freshness", "unknown", "unknown"),
                                       ("retrieved_at", "bad-date", "unknown"),
                                       ("retrieved_at", "2026-10-12T00:00:00Z", "unknown")):
            with self.subTest(field=field):
                self.snapshot["sources"][0][field] = value
                result = self.prepare([descriptor("source_details", ["source_demo"])])
                self.assertEqual(result["component_states"][0]["freshness"], expected)
                self.snapshot = synthetic_snapshot()

    def test_check_in_overdue_and_unacknowledged_review_remain_separate(self):
        result = self.prepare([descriptor("check_in", ["schedule_demo", "review_demo"])])
        state = result["component_states"][0]
        self.assertEqual(state["state"], "overdue")
        self.assertEqual([row["state"] for row in state["record_states"]], ["overdue", "requested"])
        self.assertEqual(self.snapshot["check_in"]["status"], "overdue")
        self.assertTrue(self.snapshot["follow_ups"][0]["simulation"])

    def test_shared_location_is_not_inferred_or_added_as_a_capability(self):
        self.snapshot["shared_location"] = {"id": "location_private", "place": "Synthetic place"}
        with self.assertRaises(OutputValidationError):
            self.prepare([descriptor("check_in", ["location_private"])])
        result = self.prepare([descriptor("check_in")])
        self.assertNotIn("Synthetic place", json.dumps(result))

    def test_publication_revalidation_is_pure_and_refreshes_source_expiry(self):
        prepared = self.prepare([descriptor("source_details", ["source_demo"])])
        before = copy.deepcopy(prepared)
        validated = validate_dashboard_publication(self.snapshot, prepared, now="2026-10-11T12:03:00Z")
        self.assertEqual(validated["component_states"][0]["freshness"], "stale")
        self.assertEqual(prepared, before)
        self.assertEqual(validated["status"], "prepared")

    def test_publication_rejects_changed_case_version_cross_case_and_time(self):
        prepared = self.prepare([descriptor()])
        other_case = dict(self.snapshot, case_id="synthetic_other")
        newer = dict(self.snapshot, case_version=8)
        for snapshot, now in ((other_case, LATER), (newer, LATER),
                              (self.snapshot, "2026-10-11T12:05:01Z"),
                              (self.snapshot, "2026-10-11T11:59:59Z")):
            with self.subTest(now=now), self.assertRaises(OutputValidationError) as caught:
                validate_dashboard_publication(snapshot, prepared, now=now)
            self.assertEqual(caught.exception.code, "stale_output")

    def test_publication_tampered_freshness_or_same_version_record_changes_rejected(self):
        prepared = self.prepare([descriptor("source_details", ["source_demo"])])
        altered = copy.deepcopy(prepared)
        altered["component_states"][0]["freshness"] = "unknown"
        with self.assertRaises(OutputValidationError):
            validate_dashboard_publication(self.snapshot, altered, now=LATER)
        self.snapshot["sources"][0]["freshness"] = "stale"
        with self.assertRaises(OutputValidationError):
            validate_dashboard_publication(self.snapshot, prepared, now=LATER)


class StructuredReplyTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = empty_case("synthetic_reply", "America/Chicago", NOW)

    def prepare(self, proposal):
        return prepare_structured_reply(self.snapshot, proposal, now=NOW)

    def test_legacy_string_and_text_only_object_are_equivalent(self):
        result = self.prepare("We can start with the information you have.")
        self.assertEqual(result, self.prepare({"text": result["text"]}))
        self.assertEqual(result["questions"], [])
        # Existing strict ConversationTurn does not accept questions yet; text
        # projection is compatible, and integration must add fields explicitly.
        validate("ConversationTurn", {"id": "assistant_demo", "role": "assistant", "text": result["text"],
                                      "created_at": NOW, "state": "complete"})

    def test_question_builder_is_bounded_display_only_and_detached(self):
        choices = [{"id": "choice_a", "label": "Yes"}, {"id": "choice_b", "label": "Unsure"}]
        built = build_follow_up_question(question_id="question_a", prompt="Is this possible?",
                                         kind="single_choice", choices=choices)
        self.assertTrue(built["allow_skip"])
        choices[0]["label"] = "Changed"
        self.assertEqual(built["choices"][0]["label"], "Yes")
        with self.assertRaises(OutputValidationError):
            build_follow_up_question(question_id="question_a", prompt="Is this possible?", kind="dispatch")

    def test_two_focused_questions_and_choices_are_pure_and_detached(self):
        arguments = {"text": "What would help with this step?", "questions":
                     [question(), question("question_other", "text")]}
        before = copy.deepcopy(arguments)
        snapshot_before = copy.deepcopy(self.snapshot)
        result = self.prepare(arguments)
        validate_structured_reply(self.snapshot, result, now=LATER)
        result["questions"][0]["choices"][0]["label"] = "Changed result only"
        self.assertEqual(arguments, before)
        self.assertEqual(self.snapshot, snapshot_before)

    def test_multiple_choice_is_display_only_and_allow_skip_is_required(self):
        result = self.prepare({"text": "Choose any that fit.", "questions": [question(kind="multiple_choice")]})
        self.assertTrue(result["questions"][0]["allow_skip"])
        self.assertNotIn("commands", json.dumps(result))
        for value in (False, "true", 1):
            item = question()
            item["allow_skip"] = value
            with self.assertRaises(OutputValidationError):
                self.prepare({"text": "Choose any that fit.", "questions": [item]})

    def test_question_and_choice_ids_must_be_unique_across_reply(self):
        for questions in ([question(), question()],
                          [question(), {**question("question_2"), "choices": [{"id": "choice_yes", "label": "Yes"},
                                                                                            {"id": "choice_2", "label": "Unsure"}]}],
                          [{**question(), "id": "choice_yes"}]):
            with self.assertRaises(OutputValidationError):
                self.prepare({"text": "Question", "questions": questions})

    def test_question_and_choice_bounds(self):
        items = [question(str(i), "text") for i in range(3)]
        with self.assertRaises(OutputValidationError):
            self.prepare({"text": "Question", "questions": items})
        for count in (0, 1, 7):
            item = question()
            item["choices"] = [{"id": "choice_" + str(i), "label": "Choice " + str(i)} for i in range(count)]
            with self.subTest(count=count), self.assertRaises(OutputValidationError):
                self.prepare({"text": "Question", "questions": [item]})
        item = question()
        item["choices"] = [{"id": "choice_" + str(i), "label": "Choice " + str(i)} for i in range(6)]
        self.prepare({"text": "Question", "questions": [item]})

    def test_text_questions_cannot_have_choices_and_kinds_are_allowlisted(self):
        for kind in ("text", "grant_consent", "submit_application", "dispatch", "operator"):
            with self.subTest(kind=kind), self.assertRaises(OutputValidationError):
                self.prepare({"text": "Question", "questions": [{**question(), "kind": kind}]})

    def test_choice_payloads_cannot_encode_actions_values_or_consent(self):
        for key in ("command", "payload", "value", "consent", "role", "selected", "url", "html"):
            item = question()
            item["choices"][0][key] = True
            with self.subTest(key=key), self.assertRaises(OutputValidationError):
                self.prepare({"text": "Question", "questions": [item]})

    def test_model_cannot_choose_reply_identity_role_state_or_finance_totals(self):
        for key in ("case_id", "case_version", "input_case_version", "role", "id", "state", "prepared_at", "amount_cents"):
            with self.subTest(key=key), self.assertRaises(OutputValidationError):
                self.prepare({"text": "Question", key: "untrusted"})

    def test_malicious_and_hidden_text_is_rejected_in_every_display_slot(self):
        for value in ("<img src=x onerror=alert(1)>", "<script>bad()</script>", "javascript:alert(1)",
                      "JaVaScRiPt :bad", "data:text/html,bad", "```javascript\nalert(1)```", "hidden\x00text",
                      "hidden\u202etext", "hidden\u2066text", "\x7fhidden"):
            for slot in ("text", "prompt", "label"):
                proposal = {"text": "Question", "questions": [question()]}
                if slot == "text":
                    proposal["text"] = value
                elif slot == "prompt":
                    proposal["questions"][0]["prompt"] = value
                else:
                    proposal["questions"][0]["choices"][0]["label"] = value
                with self.subTest(value=value, slot=slot), self.assertRaises(OutputValidationError):
                    self.prepare(proposal)

    def test_empty_whitespace_and_overlong_text_are_rejected_without_truncation(self):
        for text in ("", "   \n\t", "x" * 8001):
            with self.subTest(length=len(text)), self.assertRaises(OutputValidationError):
                self.prepare(text)
        self.assertEqual(len(self.prepare("x" * 8000)["text"]), 8000)
        for field, length in (("prompt", 501), ("label", 161)):
            item = question()
            if field == "prompt":
                item[field] = "x" * length
            else:
                item["choices"][0][field] = "x" * length
            with self.assertRaises(OutputValidationError):
                self.prepare({"text": "Question", "questions": [item]})

    def test_reply_rejects_stale_version_cross_case_and_expired_preparation(self):
        prepared = self.prepare("A synthetic reply")
        for snapshot, now in ((dict(self.snapshot, case_version=2), LATER),
                              (dict(self.snapshot, case_id="other_household"), LATER),
                              (self.snapshot, "2026-10-11T12:05:01Z")):
            with self.assertRaises(OutputValidationError) as caught:
                validate_structured_reply(snapshot, prepared, now=now)
            self.assertEqual(caught.exception.code, "stale_output")


class OutputBoundaryTests(unittest.TestCase):
    def test_inert_ids_reject_active_schemes_and_hidden_control_characters(self):
        for identifier in ("javascript:alert(1)", "data:text/html,bad", "hidden\u202eid", "id\n", "two ids"):
            with self.subTest(identifier=identifier), self.assertRaises(OutputValidationError):
                validate_shape("Id", identifier)

    def test_non_json_nonfinite_nested_and_cyclic_payloads_are_bounded(self):
        cycle = []
        cycle.append(cycle)
        deep = []
        for _ in range(10):
            deep = [deep]
        for value in (object(), math.nan, math.inf, cycle, deep, {1: "bad"}, {"x": [None] * 2049},
                      {"x": "a" * 65537}):
            with self.subTest(type=type(value).__name__), self.assertRaises(OutputValidationError):
                validate_shape("PublishDashboardArguments", value)

    def test_encoded_byte_budget_is_enforced_before_shape_checks(self):
        with self.assertRaises(OutputValidationError) as caught:
            validate_shape("StructuredReplyArguments", {"text": "\U0001f600" * 6000})
        self.assertEqual(caught.exception.code, "output_limit")

    def test_invalid_snapshot_identity_and_clock_are_rejected(self):
        base = {"contract_version": "0.1", "case_id": "synthetic", "case_version": 1}
        for snapshot in (None, {}, dict(base, contract_version="0.2"), dict(base, case_version=True), dict(base, case_version=0)):
            with self.assertRaises(OutputValidationError):
                prepare_structured_reply(snapshot, "Hello", now=NOW)
        for now in ("2026-10-11", "2026-10-11T12:00:00-05:00", "2026-13-11T12:00:00Z", None):
            with self.assertRaises(OutputValidationError):
                prepare_dashboard_publication(base, {"components": []}, now=now)

    def test_diagnostics_do_not_echo_untrusted_payloads(self):
        marker = "PRIVATE_SYNTHETIC_MARKER"
        with self.assertRaises(OutputValidationError) as caught:
            validate_shape("PublishDashboardArguments", {marker: marker})
        self.assertNotIn(marker, json.dumps(caught.exception.issue))
        self.assertFalse(caught.exception.issue["retryable"])

    def test_schema_kind_vocabulary_matches_existing_contract(self):
        root = Path(__file__).resolve().parents[1]
        original = json.loads((root / "contracts/case-service.schema.json").read_text())
        proposed = json.loads((root / "contracts/parallel/outputs.schema.json").read_text())
        self.assertEqual(original["$defs"]["DashboardDescriptor"]["properties"]["kind"]["enum"],
                         proposed["$defs"]["DashboardDescriptor"]["properties"]["kind"]["enum"])
        self.assertEqual(set(KIND_DOMAINS), set(proposed["$defs"]["DashboardDescriptor"]["properties"]["kind"]["enum"]))


if __name__ == "__main__":
    unittest.main()
