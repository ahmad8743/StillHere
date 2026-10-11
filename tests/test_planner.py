"""C05 deterministic evaluation and scoped read-only tooling, with synthetic inputs."""

import copy
import io
import json
import os
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from backend.stillhere.agent import AgentConfig, AgentRuntime
from backend.stillhere.agent.registry import CASE_TOOLS, PLANNER_TOOL, ToolRegistry
from backend.stillhere.agent.tools import AgentContext, AgentFailure
from backend.stillhere.contracts import InvalidInput, empty_case, validate
from backend.stillhere.knowledge.rules import ProgramRuleStore, build_query
from backend.stillhere.planner import evaluate_options
from backend.stillhere.service import CaseService, ServiceError

NOW = "2026-10-11T06:00:00Z"
PROGRAM = "co_state_id_replacement"
SOURCE = "source_rule_co_replacement"


def fact(value, state="user_reported", observed=NOW, sources=None):
    return {"value": value, "state": state, "observed_at": observed, "source_ids": sources or []}


def leaf(key, kind="fact", expected=True):
    return {"id": key, "operator": "requirement", "children": [], "source_ids": [SOURCE],
            "requirement": {"key": key, "kind": kind, "label": "Synthetic requirement " + key,
                            "expected": expected, "timing": "before_start", "evidence_state": "unknown"}}


def group(identifier, operator, children):
    return {"id": identifier, "operator": operator, "children": children, "requirement": None, "source_ids": [SOURCE]}


class PlannerEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = empty_case("synthetic", "America/Chicago", NOW)
        self.snapshot["facts"] = {"document_issuing_state": fact("CO"), "internet_access": fact(True)}
        self.catalog = ProgramRuleStore._load()
        self.store = ProgramRuleStore(lambda: copy.deepcopy(self.catalog))

    def rules(self, arguments=None, now=NOW):
        return self.store.lookup(build_query(self.snapshot, arguments or {"program_id": PROGRAM}, now))

    def evaluate(self, arguments=None, now=NOW):
        return evaluate_options(self.snapshot, self.rules(arguments, now))

    def graph(self, nodes, root="root"):
        path = self.catalog["rules"][0]["paths"][0]
        path.update(nodes=nodes, root_id=root, unresolved_requirements=[])
        self.catalog["rules"][0]["paths"] = [path]

    def option(self):
        return self.evaluate()["options"][0]

    def test_and_truth_table_distinguishes_unmet_and_unknown_without_coercion(self):
        self.graph([group("root", "all_of", ["a", "b"]), leaf("a"), leaf("b")])
        for a, b, expected in ((True, True, "satisfied"), (True, None, "unknown"),
                               (False, None, "unmet"), (False, True, "unmet")):
            with self.subTest(a=a, b=b):
                self.snapshot["facts"].update(a=fact(a), b=fact(b))
                option = self.option()
                self.assertEqual(option["requirement_state"], expected)
                self.assertEqual(option["status"], "blocked" if expected == "unmet" else "provisional")
                self.assertEqual([item["fact_key"] for item in option["blockers"]], ["a"] if a is False else [])
        self.assertEqual({item["fact_key"] for item in self.option()["questions"]}, {None})

    def test_or_truth_table_and_optional_failures_do_not_block_satisfied_branch(self):
        self.graph([group("root", "any_of", ["a", "b"]), leaf("a"), leaf("b")])
        for a, b, expected in ((True, False, "satisfied"), (True, None, "satisfied"),
                               (False, None, "unknown"), (False, False, "unmet")):
            self.snapshot["facts"].update(a=fact(a), b=fact(b))
            option = self.option()
            self.assertEqual(option["requirement_state"], expected)
            self.assertEqual([item["fact_key"] for item in option["blockers"]], ["a", "b"] if expected == "unmet" else [])
            requested = {item["fact_key"] for item in option["questions"] if item["fact_key"]}
            self.assertEqual(requested, {"b"} if expected == "unknown" else set())
            self.assertEqual(len(option["alternatives"][0]["branches"]), 2)
            if b is False:
                self.assertEqual(option["alternatives"][0]["branches"][1]["blocker_node_ids"], ["b"])

    def test_nested_and_or_alternatives_retain_only_necessary_questions(self):
        self.graph([group("root", "all_of", ["identity", "email_access"]),
                    group("identity", "any_of", ["passport", "pair"]),
                    group("pair", "all_of", ["birth_certificate", "other_proof"]),
                    leaf("passport", "evidence"), leaf("birth_certificate", "evidence"),
                    leaf("other_proof", "evidence"), leaf("email_access")])
        self.snapshot["facts"].update(passport=fact(False), birth_certificate=fact(True), email_access=fact(True))
        option = self.option()
        self.assertEqual(option["requirement_state"], "unknown")
        self.assertEqual(option["blockers"], [])
        self.assertEqual({q["fact_key"] for q in option["questions"] if q["fact_key"]}, {"other_proof"})
        self.snapshot["facts"]["other_proof"] = fact(True)
        self.assertEqual(self.option()["requirement_state"], "satisfied")

    def test_unknown_missing_conflicting_stale_invalid_and_future_answers_stay_unknown(self):
        self.graph([leaf("a")], "a")
        cases = ((None, "missing", "fact_missing"), (fact(None, "unknown"), "unknown", "fact_unknown"),
                 (fact(True, "conflicting"), "conflicting", "fact_conflicting"), (fact(True, "stale"), "stale", "fact_stale"),
                 (fact("true"), "user_reported", "fact_invalid"), (fact(1), "user_reported", "fact_invalid"),
                 (fact({"available": True}), "user_reported", "fact_invalid"),
                 (fact(True, observed=None), "user_reported", "observation_unusable"),
                 (fact(True, observed="2026-10-12T00:00:00Z"), "user_reported", "observation_unusable"))
        for answer, expected_state, reason in cases:
            self.snapshot["facts"].pop("a", None)
            if answer:
                self.snapshot["facts"]["a"] = answer
            option = self.option()
            self.assertEqual(option["requirement_state"], "unknown")
            self.assertEqual(option["requirements"][0]["fact_state"], expected_state)
            self.assertEqual(option["requirements"][0]["reason"], reason)

    def test_false_expected_predicate_uses_exact_booleans(self):
        self.graph([leaf("a", expected=False)], "a")
        self.snapshot["facts"]["a"] = fact(False)
        self.assertEqual(self.option()["requirement_state"], "satisfied")
        self.snapshot["facts"]["a"] = fact(True)
        self.assertEqual(self.option()["requirement_state"], "unmet")

    def test_authority_confirmation_cannot_be_invented_from_household_report_or_wrong_source(self):
        self.graph([leaf("confirmed", "authority_confirmation")], "confirmed")
        for answer in (fact(True), fact(True, "source_supported"), fact(True, "source_supported", sources=["unrelated_source"])):
            self.snapshot["facts"]["confirmed"] = answer
            option = self.option()
            self.assertEqual(option["requirement_state"], "unknown")
            self.assertEqual(option["requirements"][0]["reason"], "authority_unverified")
        self.snapshot["facts"]["confirmed"] = fact(True, "source_supported", sources=[SOURCE])
        option = self.option()
        self.assertEqual(option["requirement_state"], "satisfied")
        self.assertEqual(option["status"], "provisional")
        self.assertEqual(self.evaluate()["household_eligibility"], "unknown")

    def test_no_car_does_not_prove_all_transport_unavailable_or_block_online(self):
        self.snapshot["facts"].update(mobility=fact("no_car"), credential_lost=fact(True))
        result = self.evaluate()
        paths = {o["execution_mode"]: o for o in result["options"]}
        office, online = paths["in_person"], paths["online"]
        self.assertEqual(office["status"], "provisional")
        self.assertTrue(any(q["code"] == "no_car_transport_unknown" for q in office["questions"]))
        self.assertFalse(any(q["fact_key"] == "office_transport_available" for q in online["questions"]))
        self.assertIn(online["id"], office["alternative_option_ids"])
        self.snapshot["facts"]["office_transport_available"] = fact(False)
        paths = {o["execution_mode"]: o for o in self.evaluate()["options"]}
        self.assertEqual(paths["in_person"]["status"], "blocked")
        self.assertEqual(paths["online"]["status"], "provisional")
        self.assertEqual({b["fact_key"] for b in paths["in_person"]["blockers"]}, {"office_transport_available"})
        self.snapshot["facts"]["office_transport_available"] = fact(True)
        self.assertEqual(self.evaluate()["options"][1]["constraints"][0]["state"], "satisfied")

    def test_no_car_stale_report_and_known_car_do_not_establish_access(self):
        for mobility in (fact("no_car", "stale"), fact("car_available"), fact("no_car", observed="2026-10-12T00:00:00Z")):
            self.snapshot["facts"]["mobility"] = mobility
            office = self.evaluate()["options"][1]
            self.assertEqual(office["constraints"][0]["state"], "unknown")
            self.assertNotEqual(office["constraints"][0]["reason"], "no_car_transport_unknown")

    def test_online_access_is_explicit_and_no_referral_implies_a_ride(self):
        self.snapshot["facts"]["internet_access"] = fact(False)
        self.snapshot["resources"]["items"] = [{"id": "synthetic_transport_directory", "availability": "unknown"}]
        result = self.evaluate()
        self.assertEqual(result["options"][0]["status"], "blocked")
        self.assertEqual(result["options"][1]["constraints"][0]["state"], "unknown")

    def test_proof_reference_keeps_applicability_gate_and_sourced_or_document_alternatives(self):
        self.snapshot["facts"].update(valid_us_passport=fact(True), applicable_checklist_confirmed=fact(True))
        result = self.evaluate({"program_id": "co_state_id_proof_options"})
        standard = result["options"][0]
        self.assertEqual(standard["status"], "provisional")
        self.assertTrue(any(q["fact_key"] == "applicable_checklist_confirmed" for q in standard["questions"]))
        self.assertTrue(any(a["group_node_id"] == "identity_options" for a in standard["alternatives"]))
        self.assertFalse(any(q["fact_key"] == "certified_us_birth_certificate" for q in standard["questions"]))
        self.assertEqual({s["id"] for s in result["sources"]}, {"source_rule_co_documents", "source_rule_co_exceptions"})

    def test_untyped_evidence_and_completed_tasks_never_supply_guessed_requirement_answers(self):
        self.graph([leaf("a", "action")], "a")
        self.snapshot["evidence"] = [{"kind": "a", "state": "available"}]
        self.snapshot["plan"]["actions"] = [{"id": "a", "status": "completed", "title": "a"}]
        before = copy.deepcopy(self.snapshot)
        self.assertEqual(self.option()["requirement_state"], "unknown")
        self.assertEqual(self.snapshot, before)
        self.snapshot["facts"]["a"] = fact(True)
        self.assertEqual(self.option()["requirement_state"], "satisfied")

    def test_pure_deterministic_evaluation_preserves_rules_case_completed_work_and_private_values(self):
        self.snapshot["facts"]["unrelated"] = fact("synthetic_private_value")
        self.snapshot["plan"]["actions"] = [{"id": "done", "status": "completed"}]
        rules = self.rules()
        before = copy.deepcopy((self.snapshot, rules))
        result = evaluate_options(self.snapshot, rules)
        self.assertEqual(result, evaluate_options(self.snapshot, rules))
        self.assertEqual((self.snapshot, rules), before)
        self.assertNotIn("synthetic_private_value", json.dumps(result))
        self.assertEqual(result["sources"], rules["sources"])
        self.assertTrue(all(o["costs"][k] is None for o in result["options"] for k in ("fee_cents", "transport_cents", "cost_date")))

    def test_cycles_missing_nodes_missing_requirements_and_unreachable_nodes_are_rejected_before_evaluation(self):
        rules = self.rules()
        mutations = (lambda p: p["nodes"][1]["children"].append(p["root_id"]),
                     lambda p: p["nodes"][0]["children"].append("missing"),
                     lambda p: p["nodes"][2].update(requirement=None),
                     lambda p: p["nodes"].append(leaf("unreachable")),
                     lambda p: p["nodes"][0].update(children=[]))
        for mutate in mutations:
            malformed = copy.deepcopy(rules)
            mutate(malformed["rules"][0]["paths"][0])
            with self.assertRaises(InvalidInput):
                evaluate_options(self.snapshot, malformed)
        self.catalog["rules"][0]["paths"][0]["nodes"][1]["children"].append("online_root")
        unavailable = self.evaluate()
        self.assertEqual(unavailable["state"], "unavailable")
        self.assertEqual(unavailable["options"], [])
        self.assertEqual(unavailable["blockers"][0]["code"], "rules_unavailable")

    def test_shared_subgraphs_do_not_expand_combinations_or_duplicate_blockers(self):
        self.graph([group("root", "all_of", ["left", "right"]), group("left", "any_of", ["a", "b"]),
                    group("right", "all_of", ["a", "b"]), leaf("a"), leaf("b")])
        self.snapshot["facts"].update(a=fact(False), b=fact(False))
        option = self.option()
        self.assertEqual(len(option["requirements"]), 5)
        self.assertEqual([b["fact_key"] for b in option["blockers"]], ["a", "b"])

    def test_access_constraint_identifier_cannot_shadow_a_published_node(self):
        key = "constraint_internet_access"
        self.graph([leaf(key)], key)
        self.snapshot["facts"][key] = fact(False)
        option = self.option()
        self.assertEqual(option["requirements"][0]["state"], "unmet")
        self.assertEqual(option["constraints"][0]["state"], "satisfied")
        self.assertNotEqual(option["requirements"][0]["node_id"], option["constraints"][0]["node_id"])

    def test_issuer_unknown_no_match_failed_stale_and_conflicting_rules_never_become_feasible(self):
        self.snapshot["facts"].pop("document_issuing_state")
        result = self.evaluate()
        self.assertEqual((result["state"], result["options"]), ("unknown", []))
        self.assertEqual(result["questions"][0]["fact_key"], "document_issuing_state")
        self.snapshot["facts"]["document_issuing_state"] = fact("CO")
        self.assertEqual(self.evaluate({"program_id": "absent"})["state"], "no_match")
        with patch.object(self.store, "loader", side_effect=OSError):
            self.assertEqual(self.evaluate()["state"], "unavailable")
        stale = self.evaluate(now="2026-12-01T00:00:00Z")
        self.assertEqual(stale["state"], "stale")
        self.assertTrue(all(o["status"] != "feasible" for o in stale["options"]))
        other = copy.deepcopy(self.catalog["rules"][0]); other["version"] = "synthetic.v2"
        self.catalog["rules"].append(other)
        result = self.evaluate()
        self.assertEqual(result["state"], "conflicting")
        self.assertEqual(len(result["options"]), 4)
        self.assertTrue(all(o["status"] != "feasible" for o in result["options"]))
        self.assertTrue(all(len(o["alternative_option_ids"]) == 1 for o in result["options"]))
        self.assertEqual(self.evaluate({"program_id": PROGRAM, "version": "synthetic.v2"})["state"], "available")

    def test_mismatched_case_version_or_scope_cannot_be_evaluated(self):
        rules = self.rules()
        self.snapshot["case_version"] += 1
        with self.assertRaises(InvalidInput):
            evaluate_options(self.snapshot, rules)
        self.snapshot["case_version"] -= 1
        self.snapshot["facts"]["document_issuing_state"] = fact("CA")
        with self.assertRaises(InvalidInput):
            evaluate_options(self.snapshot, rules)


class PlannerToolTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(); self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "synthetic.sqlite3"
        self.service = CaseService(self.path, clock=lambda: NOW)
        self.token = self.service.create_session()["session_token"]
        self.case_id = self.service.create_case(self.token, {"contract_version": "0.1", "event_id": "create", "time_zone": "America/Chicago"})["case_snapshot"]["case_id"]
        self.correct("document_issuing_state", "CO")
        self.loads, self.callback = 0, None
        def loader():
            self.loads += 1
            if self.callback:
                callback, self.callback = self.callback, None
                callback()
            return ProgramRuleStore._load()
        self.store = ProgramRuleStore(loader)
        self.registry = ToolRegistry(CASE_TOOLS + (PLANNER_TOOL,))

    def command(self, event="chat", kind="conversation.message", payload=None):
        return {"contract_version": "0.1", "case_id": self.case_id, "event_id": event,
                "expected_case_version": self.service.read_case(self.token, self.case_id)["case_version"],
                "occurred_at": NOW, "channel": "chat", "type": kind,
                "payload": payload or {"message_id": "user_" + event, "text": "Evaluate my recovery options."}}

    def correct(self, key, value, event=None):
        return self.service.execute(self.token, self.command(event or key, "fact.correct", {"fact_key": key, "value": value, "observed_at": NOW}))

    def context(self):
        self.service.execute(self.token, self.command())
        claim = self.service.claim_agent_turn(self.token, self.case_id, "chat", 60)
        return AgentContext(self.service, self.token, self.case_id, "chat", claim["run_id"], claim["snapshot"]["case_version"],
                            time.monotonic() + 60, 16, 48000, rule_store=self.store)

    def invoke(self, context, **extra):
        return self.registry.invoke("evaluate_recovery_options", {"program_id": PROGRAM, **extra}, context)

    def test_evaluation_writes_no_case_domain_version_audit_or_policy_and_survives_restart(self):
        context = self.context()
        before = self.service.read_case(self.token, self.case_id)
        catalog = self.service.read_program_catalog()
        with self.service._connection() as connection:
            events = connection.execute("SELECT count(*) FROM events").fetchone()[0]
        result = self.invoke(context)
        validate("RecoveryOptionResult", result)
        self.assertEqual(self.service.read_case(self.token, self.case_id), before)
        self.assertEqual(CaseService(self.path).read_case(self.token, self.case_id), before)
        self.assertEqual(self.service.read_program_catalog(), catalog)
        with self.service._connection() as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM events").fetchone()[0], events)
        self.assertNotIn(self.token, json.dumps(result))
        self.assertNotIn(self.case_id, json.dumps(result))

    def test_authority_checked_before_catalog_and_model_authority_facts_graphs_costs_rejected(self):
        context = self.context()
        for extra in ({"case_id": "other"}, {"issuing_state": "CO"}, {"role": "operator"}, {"facts": {"a": True}},
                      {"rules": []}, {"cost_cents": 0}, {"publish": True}, {"as_of": NOW}):
            self.assertEqual(self.invoke(context, **extra)["error"]["code"], "invalid_tool_input")
        context.token = self.service.create_session()["session_token"]
        self.assertEqual(self.invoke(context)["error"]["code"], "case_unavailable")
        self.assertEqual(self.loads, 0)

    def test_missing_issuer_never_loads_catalog(self):
        self.correct("document_issuing_state", None, "unknown_issuer")
        result = self.invoke(self.context())
        self.assertEqual(result["state"], "unknown")
        self.assertEqual(result["options"], [])
        self.assertEqual(self.loads, 0)

    def test_concurrent_mobility_correction_discards_options_sources_and_blocks_later_tools(self):
        context = self.context()
        self.callback = lambda: self.correct("mobility", "no_car", "concurrent")
        result = self.invoke(context)
        self.assertEqual(result["state"], "conflict")
        self.assertEqual(result["options"], [])
        self.assertEqual(result["sources"], [])
        self.assertTrue(context.writes_conflicted)
        with self.assertRaises(AgentFailure):
            self.invoke(context)
        with self.assertRaises(AgentFailure):
            self.registry.invoke("correct_fact", {"fact_key": "email_access", "value": True, "observed_at": NOW}, context)

    def test_substituted_time_or_version_and_invalid_graph_fail_without_case_writes(self):
        context = self.context()
        rules = self.store.lookup(build_query(self.service.read_case(self.token, self.case_id), {"program_id": PROGRAM}, NOW))
        before = self.service.read_case(self.token, self.case_id)
        for field, value in (("as_of", "2026-10-11T07:00:00Z"), ("input_case_version", rules["query"]["input_case_version"] + 1)):
            substituted = copy.deepcopy(rules); substituted["query"][field] = value
            with patch.object(self.store, "lookup", return_value=substituted):
                self.assertEqual(self.invoke(context)["error"]["code"], "invalid_tool_input")
        malformed = copy.deepcopy(rules)
        malformed["rules"][0]["paths"][0]["nodes"][0]["children"].append("online_root")
        with patch.object(self.store, "lookup", return_value=malformed):
            self.assertEqual(self.invoke(context)["error"]["code"], "invalid_tool_input")
        self.assertEqual(self.service.read_case(self.token, self.case_id), before)

    def test_deadlines_during_lookup_and_final_recheck_discard_options(self):
        context = self.context()
        self.callback = lambda: setattr(context, "deadline", 0)
        with self.assertRaises(AgentFailure) as caught:
            self.invoke(context)
        self.assertEqual(caught.exception.issue["code"], "agent_timeout")
        context.deadline = time.monotonic() + 60
        with patch.object(self.store, "lookup", side_effect=TimeoutError), self.assertRaises(AgentFailure):
            self.invoke(context)
        context.deadline = time.monotonic() + 60
        read, calls = self.service.read_case, 0
        def final_read(*args):
            nonlocal calls
            calls += 1
            result = read(*args)
            if calls == 2:
                context.deadline = 0
            return result
        with patch.object(self.service, "read_case", side_effect=final_read), self.assertRaises(AgentFailure):
            self.invoke(context)

    def test_storage_failure_is_distinct_and_cannot_create_options(self):
        context = self.context()
        with patch.object(self.service, "read_case", side_effect=ServiceError(503, "storage_unavailable", "Synthetic", True)):
            self.assertEqual(self.invoke(context)["error"]["code"], "storage_unavailable")
        self.assertEqual(self.loads, 0)

    def test_runtime_reply_and_replay_never_repeat_evaluation_or_mutate_saved_plan(self):
        class Provider:
            def reply(inner, snapshot, history, text, context, registry):
                result = registry.invoke("evaluate_recovery_options", {"program_id": PROGRAM}, context)
                return "Synthetic options: " + result["state"]
        runtime = AgentRuntime(self.service, AgentConfig(enable_planner=True), Provider(), rule_store=self.store)
        command = self.command()
        result = runtime.handle(self.token, command)
        self.assertEqual(result["case_snapshot"]["conversation"]["turns"][-1]["text"], "Synthetic options: available")
        self.assertEqual(result["case_snapshot"]["plan"]["state"], "not_requested")
        replay = runtime.handle(self.token, command)
        self.assertEqual(replay["case_snapshot"], result["case_snapshot"])
        self.assertEqual(self.loads, 1)

    def test_independent_opt_in_and_synthetic_environment_leave_other_groups_disabled(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(AgentConfig.from_environment().enable_planner)
            os.environ["STILLHERE_AGENT_ENABLE_PLANNER"] = "true"
            config = AgentConfig.from_environment()
            self.assertTrue(config.enable_planner)
            self.assertFalse(config.enable_rules)
            names = set(AgentRuntime(self.service, config).registry.by_name)
            self.assertEqual(names, {"read_case", "correct_fact", "evaluate_recovery_options"})
            os.environ["STILLHERE_AGENT_ENABLE_PLANNER"] = "yes"
            with self.assertRaises(ValueError):
                AgentConfig.from_environment()
        self.assertNotIn("evaluate_recovery_options", AgentRuntime(self.service).registry.by_name)


class PlannerSmokeTests(unittest.TestCase):
    def run_smoke(self, behavior="valid"):
        from backend.stillhere.agent.smoke import main
        class Provider:
            def reply(inner, snapshot, history, text, context, registry):
                if behavior == "missing":
                    return "Synthetic plain reply"
                result = registry.invoke("evaluate_recovery_options", {"program_id": PROGRAM}, context)
                if behavior == "mutation":
                    registry.invoke("correct_fact", {"fact_key": "email_access", "value": True, "observed_at": NOW}, context)
                if behavior == "bad_reply":
                    return "Synthetic reply without evidence"
                return "Online provisional alternative; office blocked. Costs and eligibility unknown. " + result["options"][0]["official_url"]
        def runtime(service, config, diagnostics=None):
            return AgentRuntime(service, config, Provider(), diagnostics=diagnostics)
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "safe.jsonl"
            output = io.StringIO()
            with patch("sys.argv", ["smoke", "--planner", "--log-file", str(log)]), \
                 patch("backend.stillhere.agent.smoke.AgentConfig.from_environment", return_value=AgentConfig(model_id="synthetic", region="synthetic")), \
                 patch("backend.stillhere.agent.smoke.AgentRuntime", side_effect=runtime), \
                 patch("backend.stillhere.agent.smoke.load_local_environment") as environment, redirect_stdout(output):
                status = main()
            environment.assert_not_called()
            return status, output.getvalue(), log.read_text()

    def test_synthetic_live_proof_checks_no_car_unknowns_source_saved_reply_and_replay(self):
        status, output, log = self.run_smoke()
        self.assertEqual(status, 0)
        self.assertIn("read-only planner", output)
        records = [json.loads(line) for line in log.splitlines()]
        self.assertEqual((records[-1]["event"], records[-1]["mode"]), ("smoke_passed", "planner"))
        self.assertNotIn(PROGRAM, log)
        self.assertNotIn("synthetic", log)

    def test_proof_rejects_missing_tool_uncited_reply_or_domain_mutation(self):
        for behavior, code in (("missing", "planner_result_missing"), ("bad_reply", "planner_reply_missing"),
                               ("mutation", "planner_side_effect_unexpected")):
            status, output, log = self.run_smoke(behavior)
            self.assertEqual(status, 1)
            self.assertIn(code, log)
            self.assertNotIn('"event": "smoke_passed"', log)
