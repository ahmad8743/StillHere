"""Synthetic C04 rule lookup, scope, review, graph, SDK boundary and smoke checks."""

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
from backend.stillhere.agent.diagnostics import SafeDiagnostics
from backend.stillhere.agent.registry import CASE_TOOLS, RULE_TOOL, ToolRegistry
from backend.stillhere.agent.tools import AgentContext, AgentFailure
from backend.stillhere.contracts import InvalidInput, empty_case, validate
from backend.stillhere.knowledge import ProgramRuleStore, build_query
from backend.stillhere.knowledge.rules import validate_catalog, validate_result
from backend.stillhere.service import CaseService, ServiceError

NOW = "2026-10-11T03:00:00Z"
PROGRAM = "co_state_id_replacement"


def fact(value, state="user_reported"):
    return {"value":value, "state":state, "observed_at":NOW, "source_ids":[]}


class ProgramRuleStoreTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = empty_case("synthetic", "America/Denver", NOW)
        self.snapshot["facts"]["document_issuing_state"] = fact("CO")
        self.catalog = ProgramRuleStore._load()
        self.loads = 0
        def load():
            self.loads += 1
            return copy.deepcopy(self.catalog)
        self.store = ProgramRuleStore(load)

    def query(self, **arguments):
        return build_query(self.snapshot, {"program_id":PROGRAM, **arguments}, NOW)

    def lookup(self, **arguments):
        return self.store.lookup(self.query(**arguments))

    def test_source_scoped_and_or_paths_keep_unknown_prerequisites_fees_and_effective_dates(self):
        result = self.lookup()
        self.assertEqual(result["state"], "available")
        rule = result["rules"][0]
        self.assertEqual(rule["credential_kind"], "state_id")
        self.assertEqual({p["execution_mode"] for p in rule["paths"]}, {"online","in_person"})
        self.assertTrue(all(p["fee_cents"] is None and p["unresolved_requirements"] for p in rule["paths"]))
        operators = {node["operator"] for path in rule["paths"] for node in path["nodes"]}
        self.assertEqual(operators, {"all_of","any_of","requirement"})
        self.assertTrue(all(node["requirement"]["evidence_state"] == "unknown" for path in rule["paths"] for node in path["nodes"] if node["requirement"]))
        self.assertIsNone(rule["effective_from"])
        self.assertIsNone(rule["effective_to"])
        self.assertFalse(rule["coverage_complete"])
        self.assertEqual(result["household_eligibility"], "unknown")
        validate_result(result)

    def test_current_and_damaged_geography_never_establish_document_issuer(self):
        del self.snapshot["facts"]["document_issuing_state"]
        self.snapshot["facts"].update(current_location=fact({"state":"CO"}), damaged_location=fact({"state":"CO"}))
        result = self.lookup()
        self.assertEqual(result["state"], "unknown")
        self.assertEqual(result["rules"], [])
        self.assertEqual(self.loads, 0)
        self.assertIsNone(result["query"]["issuing_state"])

    def test_unknown_conflicting_stale_and_invalid_issuers_do_not_load_rules(self):
        for value,state,expected in ((None,"unknown","unknown"),("CO","conflicting","conflicting"),("CO","stale","stale"),
                                     ("Colorado","user_reported","invalid"),({"state":"CO"},"user_reported","invalid")):
            with self.subTest(value=value,state=state):
                self.snapshot["facts"]["document_issuing_state"] = fact(value,state)
                result = self.lookup()
                self.assertEqual(result["state"], "unknown")
                self.assertEqual(result["query"]["jurisdiction_state"], expected)
        self.assertEqual(self.loads, 0)

    def test_no_match_covers_only_the_requested_program_state_and_version(self):
        for arguments in ({"program_id":"another_program"},{"version":"absent_version"}):
            result = self.lookup(**arguments)
            self.assertEqual(result["state"], "no_match")
            self.assertEqual(result["rules"], [])
        self.snapshot["facts"]["document_issuing_state"] = fact("CA")
        self.assertEqual(self.lookup()["state"], "no_match")

    def test_multiple_versions_are_conflicting_until_an_exact_version_is_selected(self):
        additional = copy.deepcopy(self.catalog["rules"][0])
        additional["version"] = "synthetic.v2"
        self.catalog["rules"].append(additional)
        result = self.lookup()
        self.assertEqual(result["state"], "conflicting")
        self.assertEqual(len(result["rules"]), 2)
        self.assertEqual(self.lookup(version="synthetic.v2")["state"], "available")
        self.assertEqual(self.lookup(version="synthetic.v2")["rules"][0]["version"], "synthetic.v2")

    def test_source_or_rule_expiry_retains_labeled_stale_rules_without_refreshing_source_times(self):
        original = self.lookup()
        expiry = self.catalog["rules"][0]["review_expires_at"]
        query = self.query()
        query["as_of"] = expiry
        result = self.store.lookup(query)
        self.assertEqual(result["state"], "stale")
        self.assertEqual(result["sources"][0]["retrieved_at"], original["sources"][0]["retrieved_at"])
        self.assertTrue(all(source["freshness"] == "stale" for source in result["sources"]))
        self.catalog["rules"][0]["review_expires_at"] = "2026-10-11T02:30:00Z"
        self.assertEqual(self.lookup()["state"], "stale")

    def test_effective_intervals_do_not_relabel_historical_or_future_rules_as_current(self):
        self.catalog["rules"][0]["effective_to"] = NOW
        self.assertEqual(self.lookup()["state"], "stale")
        self.catalog["rules"][0].update(effective_to=None,effective_from="2026-10-12T00:00:00Z")
        self.assertEqual(self.lookup()["state"], "stale")
        self.catalog["rules"][0]["effective_to"] = NOW
        self.assertEqual(self.lookup()["state"], "unavailable")

    def test_failed_and_unreviewed_store_never_becomes_no_match_or_published_policy(self):
        def fail():
            raise OSError("synthetic failure")
        self.store.loader = fail
        self.assertEqual(self.lookup()["state"], "unavailable")
        self.store.loader = lambda: self.catalog
        self.catalog["rules"][0]["review_state"] = "pending_review"
        self.assertEqual(self.lookup()["state"], "unavailable")
        self.catalog["rules"][0].update(review_state="reviewed",publication_state="candidate")
        self.assertEqual(self.lookup()["state"], "unavailable")

    def test_rule_source_reference_issuer_scope_and_official_hosts_are_validated(self):
        mutations = [lambda c:c["rules"][0]["source_ids"].append("missing_source"),
                     lambda c:c["sources"][0].update(issuer="another issuer"),
                     lambda c:c["sources"][0]["jurisdiction"].update(state="CA"),
                     lambda c:c["sources"][0].update(url="https://dmv.nxt-demo.colorado.gov/documents"),
                     lambda c:c["rules"][0]["paths"][0].update(official_url="https://user:pass@mydmv.colorado.gov/"),
                     lambda c:c["rules"][0]["paths"][0]["nodes"][2]["source_ids"].append("source_resource_other")]
        for mutate in mutations:
            catalog = copy.deepcopy(self.catalog)
            mutate(catalog)
            with self.assertRaises(InvalidInput):
                validate_catalog(catalog)

    def test_graph_validation_rejects_cycles_dangling_children_and_unreachable_nodes(self):
        for mutate in (lambda p:p["nodes"][1]["children"].append(p["root_id"]),
                       lambda p:p["nodes"][0]["children"].append("missing"),
                       lambda p:p["nodes"].append({**copy.deepcopy(p["nodes"][2]),"id":"unreachable"}),
                       lambda p:p["nodes"][2]["children"].append("lost")):
            catalog = copy.deepcopy(self.catalog)
            mutate(catalog["rules"][0]["paths"][0])
            with self.assertRaises(InvalidInput):
                validate_catalog(catalog)

    def test_graph_depth_and_repeated_subgraphs_are_bounded(self):
        catalog = copy.deepcopy(self.catalog)
        path = catalog["rules"][0]["paths"][0]
        root = path["root_id"]
        for index in range(8):
            identifier = "layer_"+str(index)
            path["nodes"].append({"id":identifier,"operator":"all_of","children":[root],"requirement":None,"source_ids":["source_rule_co_replacement"]})
            root = identifier
        path["root_id"] = root
        with self.assertRaises(InvalidInput):
            validate_catalog(catalog)
        # Shared subgraphs are valid; validation memoizes them instead of expanding exponentially.
        path = self.catalog["rules"][0]["paths"][0]
        path["nodes"][0]["children"].append("lost")
        validate_catalog(self.catalog)

    def test_more_than_four_matching_versions_are_conflicting_and_visibly_bounded(self):
        for index in range(5):
            rule = copy.deepcopy(self.catalog["rules"][0]); rule["version"]="synthetic."+str(index)
            self.catalog["rules"].append(rule)
        result = self.lookup()
        self.assertEqual(result["state"], "conflicting")
        self.assertEqual(len(result["rules"]),4)
        self.assertIn("rule_results_truncated",[issue["code"] for issue in result["notices"]])

    def test_private_payloads_and_model_selected_scope_are_rejected(self):
        for extra in ({"case_id":"other"},{"issuing_state":"CO"},{"as_of":NOW},{"url":"https://dmv.colorado.gov/"},
                      {"publish":True},{"household_answers":{"credential_number":"synthetic_private"}}):
            with self.assertRaises(InvalidInput):
                self.query(**extra)
        self.catalog["rules"][0]["household_answers"] = {"private":"synthetic"}
        self.assertEqual(self.lookup()["state"], "unavailable")

    def test_result_scope_and_deadline_are_validated(self):
        result = self.lookup()
        result["query"]["issuing_state"] = "CA"
        with self.assertRaises(InvalidInput):
            validate_result(result)
        with self.assertRaises(TimeoutError):
            self.store.lookup(self.query(),time.monotonic()-1)


class ProgramRuleToolTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(); self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)/"synthetic.sqlite3"
        self.service = CaseService(self.path,clock=lambda:NOW)
        self.token = self.service.create_session()["session_token"]
        self.case = self.service.create_case(self.token,{"contract_version":"0.1","event_id":"create","time_zone":"America/Denver",
                    "intake":{"current_location":{"place":"Synthetic Denver","state":"CO"},"needs":["lost_documents"]}})["case_snapshot"]
        self.case_id = self.case["case_id"]
        self.correct_issuer("CO")
        self.loads = 0; self.callback = None
        def load():
            self.loads += 1
            if self.callback:
                callback,self.callback = self.callback,None
                callback()
            return ProgramRuleStore._load()
        self.store = ProgramRuleStore(load)
        self.registry = ToolRegistry(CASE_TOOLS+(RULE_TOOL,))

    def command(self,event="rule_chat",kind="conversation.message",payload=None):
        case = self.service.read_case(self.token,self.case_id)
        return {"contract_version":"0.1","case_id":self.case_id,"event_id":event,"expected_case_version":case["case_version"],
                "occurred_at":NOW,"channel":"chat","type":kind,
                "payload":payload or {"message_id":"user_"+event,"text":"My missing state ID was issued by Colorado; retrieve its replacement rules."}}

    def correct_issuer(self,value,event="issuer"):
        return self.service.execute(self.token,self.command(event,"fact.correct",{"fact_key":"document_issuing_state","value":value,"observed_at":NOW}))

    def claim(self):
        self.service.execute(self.token,self.command())
        claim = self.service.claim_agent_turn(self.token,self.case_id,"rule_chat",60)
        return AgentContext(self.service,self.token,self.case_id,"rule_chat",claim["run_id"],claim["snapshot"]["case_version"],
                            time.monotonic()+60,16,48000,rule_store=self.store)

    def lookup(self,context,**extra):
        return self.registry.invoke("retrieve_program_rules",{"program_id":PROGRAM,**extra},context)

    def test_rule_reads_have_no_durable_domain_or_audit_writes(self):
        context = self.claim(); before = self.service.read_case(self.token,self.case_id)
        with self.service._connection() as connection:
            count = connection.execute("SELECT count(*) FROM events").fetchone()[0]
        result = self.lookup(context)
        self.assertEqual(result["state"],"available")
        self.assertEqual(self.service.read_case(self.token,self.case_id),before)
        self.assertEqual(CaseService(self.path).read_case(self.token,self.case_id),before)
        with self.service._connection() as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM events").fetchone()[0],count)
        self.assertNotIn(self.token,json.dumps(result))
        self.assertNotIn(self.case_id,json.dumps(result))

    def test_household_authority_is_checked_before_shared_store_read(self):
        context = self.claim()
        context.token = self.service.create_session()["session_token"]
        self.assertEqual(self.lookup(context)["error"]["code"],"case_unavailable")
        self.assertEqual(self.loads,0)

    def test_model_selected_authority_source_and_publication_are_rejected_before_read(self):
        context = self.claim()
        for extra in ({"case_id":"other"},{"issuing_state":"CO"},{"role":"operator"},{"publish":True},{"url":"https://dmv.colorado.gov/"}):
            self.assertEqual(self.lookup(context,**extra)["error"]["code"],"invalid_tool_input")
        self.assertEqual(self.loads,0)

    def test_concurrent_correction_discards_rules_and_blocks_followup_mutation(self):
        context = self.claim()
        self.callback = lambda:self.correct_issuer("CA","concurrent")
        result = self.lookup(context)
        self.assertEqual(result["state"],"conflict")
        self.assertEqual(result["rules"],[])
        self.assertEqual(result["sources"],[])
        self.assertTrue(context.writes_conflicted)
        with self.assertRaises(AgentFailure):
            self.registry.invoke("correct_fact",{"fact_key":"mobility","value":"no_car","observed_at":NOW},context)

    def test_store_cannot_substitute_a_different_backend_query(self):
        context = self.claim()
        query = build_query(self.service.read_case(self.token,self.case_id),{"program_id":PROGRAM},NOW)
        result = self.store.lookup(query)
        for field,value in (("input_case_version",query["input_case_version"]+1),("as_of","2026-10-11T04:00:00Z")):
            with self.subTest(field=field):
                substituted = copy.deepcopy(result)
                substituted["query"][field] = value
                with patch.object(self.store,"lookup",return_value=substituted):
                    self.assertEqual(self.lookup(context)["error"]["code"],"invalid_tool_input")

    def test_deadline_during_input_revalidation_discards_the_result(self):
        context = self.claim()
        read = self.service.read_case
        calls = 0
        def delayed_read(*arguments):
            nonlocal calls
            calls += 1
            snapshot = read(*arguments)
            if calls == 2:
                context.deadline = 0
            return snapshot
        with patch.object(self.service,"read_case",side_effect=delayed_read),self.assertRaises(AgentFailure) as caught:
            self.lookup(context)
        self.assertEqual(caught.exception.issue["code"],"agent_timeout")

    def test_expired_lookup_never_returns_late_rules(self):
        context = self.claim()
        self.callback = lambda:setattr(context,"deadline",0)
        with self.assertRaises(AgentFailure) as caught:
            self.lookup(context)
        self.assertEqual(caught.exception.issue["code"],"agent_timeout")
        context.deadline = time.monotonic()+60
        with patch.object(self.store,"lookup",side_effect=TimeoutError),self.assertRaises(AgentFailure):
            self.lookup(context)

    def test_read_and_store_failure_do_not_change_the_case(self):
        context = self.claim(); before = self.service.read_case(self.token,self.case_id)
        with patch.object(self.store,"loader",side_effect=OSError):
            result = self.lookup(context)
        self.assertEqual(result["state"],"unavailable")
        self.assertEqual(self.service.read_case(self.token,self.case_id),before)
        with patch.object(self.service,"read_case",side_effect=ServiceError(503,"storage_unavailable","Synthetic read failure",True)):
            failed_read = self.lookup(context)
        self.assertEqual(failed_read["error"]["code"],"storage_unavailable")
        self.assertEqual(self.loads,0)

    def test_runtime_replay_saves_reply_and_does_not_repeat_rule_lookup(self):
        class Provider:
            def reply(inner,snapshot,history,text,context,registry):
                result = registry.invoke("retrieve_program_rules",{"program_id":PROGRAM},context)
                return "Synthetic rule retrieval state: "+result["state"]
        runtime = AgentRuntime(self.service,AgentConfig(enable_rules=True),provider=Provider(),rule_store=self.store)
        command = self.command()
        result = runtime.handle(self.token,command)
        after = result["case_snapshot"]
        self.assertEqual(after["conversation"]["turns"][-1]["text"],"Synthetic rule retrieval state: available")
        self.assertEqual(self.loads,1)
        replay = runtime.handle(self.token,command)
        self.assertEqual(replay["case_snapshot"]["case_version"],after["case_version"])
        self.assertEqual(self.loads,1)
        self.assertEqual(after["sources"],[])
        self.assertNotIn("retrieve_program_rules",AgentRuntime(self.service).registry.by_name)

    def test_independent_opt_in_flag_uses_only_synthetic_environment(self):
        with patch.dict(os.environ,{},clear=True):
            self.assertFalse(AgentConfig.from_environment().enable_rules)
            os.environ["STILLHERE_AGENT_ENABLE_RULES"]="true"
            config=AgentConfig.from_environment()
            self.assertTrue(config.enable_rules)
            self.assertFalse(config.enable_resources)
            os.environ["STILLHERE_AGENT_ENABLE_RULES"]="yes"
            with self.assertRaises(ValueError):
                AgentConfig.from_environment()

    def test_user_run_rules_smoke_checks_real_rule_result_reply_replay_and_safe_mode(self):
        from backend.stillhere.agent.smoke import main
        class Provider:
            def reply(inner,snapshot,history,text,context,registry):
                registry.invoke("retrieve_program_rules",{"program_id":PROGRAM},context)
                return "Synthetic online and office routes with source links; eligibility remains unknown."
        def runtime(service,config,diagnostics=None):
            return AgentRuntime(service,config,provider=Provider(),diagnostics=diagnostics)
        output=io.StringIO(); log=Path(self.directory.name)/"safe-smoke.jsonl"
        with patch("sys.argv",["smoke","--rules","--log-file",str(log)]), \
             patch("backend.stillhere.agent.smoke.AgentConfig.from_environment",return_value=AgentConfig(model_id="synthetic_model",region="synthetic_region")), \
             patch("backend.stillhere.agent.smoke.AgentRuntime",side_effect=runtime), \
             patch("backend.stillhere.agent.smoke.load_local_environment") as load_environment,redirect_stdout(output):
            self.assertEqual(main(),0)
        load_environment.assert_not_called()
        self.assertIn("read-only rule tool",output.getvalue())
        records=[json.loads(line) for line in log.read_text().splitlines()]
        self.assertEqual(records[0]["mode"],"rules")
        self.assertEqual(records[-1]["event"],"smoke_passed")
        self.assertEqual(records[-1]["mode"],"rules")
        self.assertNotIn("synthetic_model",log.read_text())
        self.assertNotIn(PROGRAM,log.read_text())

    def test_smoke_cannot_pass_without_a_rule_tool_result(self):
        from backend.stillhere.agent.smoke import main
        class Provider:
            def reply(inner,*args):
                return "Synthetic plain reply without the required rule lookup"
        def runtime(service,config,diagnostics=None):
            return AgentRuntime(service,config,provider=Provider(),diagnostics=diagnostics)
        log=Path(self.directory.name)/"safe-failure.jsonl"
        with patch("sys.argv",["smoke","--rules","--log-file",str(log)]), \
             patch("backend.stillhere.agent.smoke.AgentConfig.from_environment",return_value=AgentConfig(model_id="synthetic",region="synthetic")), \
             patch("backend.stillhere.agent.smoke.AgentRuntime",side_effect=runtime),redirect_stdout(io.StringIO()):
            self.assertEqual(main(),1)
        self.assertIn('"code": "rule_lookup_missing"',log.read_text())

    def test_smoke_rejects_an_unexpected_domain_mutation_after_a_valid_lookup(self):
        from backend.stillhere.agent.smoke import main
        class Provider:
            def reply(inner,snapshot,history,text,context,registry):
                registry.invoke("retrieve_program_rules",{"program_id":PROGRAM},context)
                registry.invoke("correct_fact",{"fact_key":"mobility","value":"no_car","observed_at":NOW},context)
                return "Synthetic valid rule result followed by an unintended case mutation"
        def runtime(service,config,diagnostics=None):
            return AgentRuntime(service,config,provider=Provider(),diagnostics=diagnostics)
        log=Path(self.directory.name)/"safe-side-effect.jsonl"
        with patch("sys.argv",["smoke","--rules","--log-file",str(log)]), \
             patch("backend.stillhere.agent.smoke.AgentConfig.from_environment",return_value=AgentConfig(model_id="synthetic",region="synthetic")), \
             patch("backend.stillhere.agent.smoke.AgentRuntime",side_effect=runtime),redirect_stdout(io.StringIO()):
            self.assertEqual(main(),1)
        self.assertIn('"code": "rule_side_effect_unexpected"',log.read_text())
        self.assertNotIn('"event": "smoke_passed"',log.read_text())

    def test_smoke_mode_and_codes_are_allowlisted_without_free_text(self):
        path=Path(self.directory.name)/"safe.jsonl"; diagnostics=SafeDiagnostics(path)
        diagnostics.record("smoke_started",mode="private-model-name")
        diagnostics.record("smoke_failed",mode="rules",code="rule_attribution_invalid")
        records=[json.loads(line) for line in path.read_text().splitlines()]
        self.assertEqual(records[0]["mode"],"unknown")
        self.assertEqual(records[1]["code"],"rule_attribution_invalid")
        self.assertNotIn("private-model-name",path.read_text())
