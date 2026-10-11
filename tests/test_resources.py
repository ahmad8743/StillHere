"""C04 synthetic catalog, scope, failure, atomic commit and replay checks. No network."""

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
from backend.stillhere.agent.registry import CASE_TOOLS, RESOURCE_TOOL, ToolRegistry
from backend.stillhere.agent.tools import AgentContext, AgentFailure
from backend.stillhere.contracts import InvalidInput, empty_case, validate
from backend.stillhere.resources import ResourceCatalog, build_query
from backend.stillhere.service import CaseService

NOW = "2026-10-11T02:00:00Z"
GEO = {"place": "Synthetic Denver", "state": "CO", "county_fips": "08031"}


def fact(value, state="user_reported"):
    return {"value": value, "state": state, "observed_at": NOW, "source_ids": []}


class ResourceCatalogTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = empty_case("synthetic", "America/Denver", NOW)
        self.asset = ResourceCatalog._load()
        self.catalog = ResourceCatalog(loader=lambda: copy.deepcopy(self.asset), clock=lambda: NOW)

    def collect(self, scope="current"):
        return self.catalog.collect(build_query(self.snapshot, {"location_scope": scope}), 1)

    def test_unknown_profile_has_nationwide_routes_without_inventing_needs_or_capacity(self):
        before = copy.deepcopy(self.snapshot)
        result = self.collect()
        self.assertEqual(result["state"], "available")
        self.assertEqual(len(result["items"]), 4)
        self.assertTrue(all(item["coverage"]["state"] is None for item in result["items"]))
        self.assertTrue(all(item["availability"]["state"] == "unknown" and item["requirements"]["state"] == "unknown"
                            and item["household_eligibility"] == "unknown" for item in result["items"]))
        self.assertEqual(self.snapshot, before)
        self.assertEqual(result["search"]["query"]["needs_state"], "unknown")
        validate("ResourceSearchResult", result)

    def test_reported_state_and_needs_select_local_referral_and_national_routes(self):
        self.snapshot["facts"].update(current_location=fact(GEO), requested_needs=fact(["shelter", "transport"]))
        result = self.collect()
        self.assertEqual(len(result["items"]), 2)
        colorado = next(item for item in result["items"] if item["coverage"]["state"] == "CO")
        self.assertEqual(colorado["contact"]["phone"], "2-1-1")
        self.assertTrue(all(source["data_mode"] == "seeded" for source in result["sources"]))
        self.assertEqual(result["search"]["query"]["need_kinds"], ["shelter", "transport"])

    def test_current_and_damaged_scope_never_substitute_for_each_other_or_document_issuer(self):
        self.snapshot["facts"].update(current_location=fact({"state": "CA"}), damaged_location=fact(GEO))
        current, damaged = self.collect(), self.collect("damaged")
        self.assertEqual(len(current["items"]), 4)
        self.assertEqual(len(damaged["items"]), 5)
        self.assertTrue({source["id"] for source in current["sources"]}.isdisjoint({source["id"] for source in damaged["sources"]}))
        self.assertIn("resource_issuing_jurisdiction_unknown", [n["code"] for n in damaged["notices"]])

    def test_missing_conflicting_stale_or_invalid_geography_does_not_select_local_referral(self):
        for value, state in ((GEO,"stale"), (GEO,"conflicting"), ({"place":"Denver","postal_code":"80202"},"user_reported"),
                             ({"state":"CO","county_fips":"06037"},"user_reported"), ({"latitude":91,"longitude":0},"user_reported")):
            with self.subTest(value=value, state=state):
                self.snapshot["facts"]["current_location"] = fact(value, state)
                result = self.collect()
                self.assertEqual(len(result["items"]), 4)
                self.assertTrue(all(item["coverage"]["state"] is None for item in result["items"]))

    def test_corrected_requested_needs_override_retained_need_records(self):
        self.snapshot["needs"] = [{"kind":"shelter"}]
        self.snapshot["facts"]["requested_needs"] = fact(["lost_documents"])
        result = self.collect()
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["need_kinds"], ["lost_documents"])
        for value in (None, ["unsure"], "shelter", ["model_invented_need"]):
            self.snapshot["facts"]["requested_needs"] = fact(value)
            self.assertEqual(build_query(self.snapshot, {"location_scope":"current"})["need_kinds"], [])

    def test_review_expiry_and_original_source_times_do_not_become_live_retrieval(self):
        result = self.collect()
        source = result["sources"][0]
        self.assertEqual(source["retrieved_at"], self.asset["sources"][0]["retrieved_at"])
        self.assertNotEqual(source["retrieved_at"], result["search"]["retrieved_at"])
        self.catalog.clock = lambda: source["expires_at"]
        stale = self.collect()
        self.assertEqual(stale["state"], "available")
        self.assertEqual(stale["search"]["freshness"], "stale")
        self.assertTrue(all(s["freshness"] == "stale" for s in stale["sources"]))
        self.assertIn("resource_review_stale", [n["code"] for n in stale["notices"]])

    def test_failed_or_malformed_catalog_is_unavailable_even_for_out_of_scope_records(self):
        def failed():
            raise OSError("synthetic failure")
        self.catalog.loader = failed
        self.assertEqual(self.collect()["state"], "unavailable")
        self.asset["items"][-1]["source_ids"] = ["missing_source"]
        self.catalog.loader = lambda: self.asset
        self.assertEqual(self.collect()["state"], "unavailable")
        for url in ("http://www.usa.gov/", "https://www.usa.gov.evil.example/", "https://user:pass@www.usa.gov/", "https://www.usa.gov:invalid/"):
            asset = ResourceCatalog._load()
            asset["sources"][0]["url"] = url
            asset["items"][0]["contact"]["url"] = url
            self.catalog.loader = lambda: asset
            self.assertEqual(self.collect()["state"], "unavailable")

    def test_no_match_describes_only_completed_catalog_scope(self):
        self.snapshot["facts"]["requested_needs"] = fact(["transport"])
        result = self.collect()
        self.assertEqual(result["state"], "no_match")
        self.assertEqual(result["items"], [])
        self.assertEqual(result["sources"], [])
        self.assertIn("resource_bounded_catalog", [n["code"] for n in result["notices"]])

    def test_truncation_is_bounded_and_attribution_matches_retained_records(self):
        self.snapshot["facts"]["current_location"] = fact(GEO)
        extra = copy.deepcopy(self.asset["items"][0])
        extra["id"] = "synthetic_extra_referral"
        self.asset["items"].append(extra)
        result = self.collect()
        self.assertEqual(len(result["items"]), 5)
        self.assertTrue(result["search"]["truncated"])
        self.assertEqual({s["id"] for s in result["sources"]}, {i for item in result["items"] for i in item["source_ids"]})

    def test_deadline_and_model_selected_arguments_are_rejected(self):
        with self.assertRaises(TimeoutError):
            self.catalog.collect(build_query(self.snapshot, {"location_scope":"current"}), 1, time.monotonic()-1)
        for extra in ({"url":"https://www.usa.gov/"}, {"case_id":"other"}, {"need_kinds":["shelter"]}, {"role":"operator"}):
            with self.assertRaises(InvalidInput):
                build_query(self.snapshot, {"location_scope":"current", **extra})


class ResourceServiceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "synthetic.sqlite3"
        self.now = NOW
        self.service = CaseService(self.path, clock=lambda: self.now)
        self.token = self.service.create_session()["session_token"]
        self.case = self.service.create_case(self.token, {"contract_version":"0.1", "event_id":"create", "time_zone":"America/Denver",
                    "intake":{"current_location":GEO, "needs":["shelter","transport"]}})["case_snapshot"]
        self.case_id = self.case["case_id"]
        self.loads = 0
        self.callback = None
        self.asset = ResourceCatalog._load()
        def load():
            self.loads += 1
            if self.callback:
                callback, self.callback = self.callback, None
                callback()
            return copy.deepcopy(self.asset)
        self.catalog = ResourceCatalog(load, clock=lambda: self.now)
        self.registry = ToolRegistry(CASE_TOOLS + (RESOURCE_TOOL,))

    def message(self, event="resource_chat", version=1):
        return {"contract_version":"0.1", "case_id":self.case_id, "event_id":event, "expected_case_version":version,
                "occurred_at":NOW, "channel":"chat", "type":"conversation.message",
                "payload":{"message_id":"user_"+event, "text":"Find resource referrals for my reported location and needs."}}

    def claim(self, event="resource_chat"):
        version = self.service.read_case(self.token, self.case_id)["case_version"]
        self.service.execute(self.token, self.message(event, version))
        claim = self.service.claim_agent_turn(self.token, self.case_id, event, 60)
        return AgentContext(self.service, self.token, self.case_id, event, claim["run_id"], claim["snapshot"]["case_version"],
                            time.monotonic()+60, 20, 48000, resource_catalog=self.catalog)

    def fetch(self, context, scope="current"):
        return self.registry.invoke("find_resources", {"location_scope":scope}, context)

    def correct(self, key, value):
        command = self.message("correction_"+key, self.service.read_case(self.token, self.case_id)["case_version"])
        command.update(type="fact.correct", payload={"fact_key":key,"value":value,"observed_at":NOW})
        return self.service.execute(self.token, command)

    def test_audited_commit_replay_and_restart_preserve_private_and_finance_state(self):
        context = self.claim()
        before = self.service.read_case(self.token, self.case_id)
        result = self.fetch(context)
        self.assertEqual(result["status"], "applied")
        after = result["case_snapshot"]
        replay = self.fetch(context)
        self.assertEqual(replay["status"], "already_applied")
        self.assertEqual(replay["case_snapshot"]["case_version"], after["case_version"])
        self.assertEqual(self.loads, 1)
        self.assertEqual(CaseService(self.path).read_case(self.token,self.case_id), after)
        for key in ("facts","needs","check_in","shared_location","applications"):
            self.assertEqual(after[key], before[key])
        self.assertEqual(after["finance"]["ledger"], before["finance"]["ledger"])
        with self.service._connection() as connection:
            audit = json.loads(connection.execute("SELECT before_case_json FROM events WHERE command_json LIKE '%resource.search%'").fetchone()[0])
        self.assertEqual(audit["resources"]["state"], "not_requested")

    def test_authority_is_backend_only_and_scoped_before_catalog_read(self):
        context = self.claim()
        for extra in ({"url":"https://untrusted.example"},{"case_id":"other"},{"state":"CA"},{"role":"operator"}):
            result = self.registry.invoke("find_resources", {"location_scope":"current", **extra}, context)
            self.assertEqual(result["error"]["code"], "invalid_tool_input")
        context.token = self.service.create_session()["session_token"]
        self.assertEqual(self.fetch(context)["error"]["code"], "case_unavailable")
        self.assertEqual(self.loads, 0)

    def test_concurrent_change_conflicts_and_blocks_further_writes(self):
        context = self.claim()
        self.callback = lambda: self.correct("current_location", {"state":"CA"})
        self.assertEqual(self.fetch(context)["status"], "conflict")
        with self.assertRaises(AgentFailure):
            self.fetch(context)
        self.assertEqual(self.service.read_case(self.token,self.case_id)["resources"]["state"], "not_requested")

    def test_expired_run_or_deadline_cannot_commit(self):
        context = self.claim()
        self.callback = lambda: setattr(self, "now", "2026-10-11T02:01:01Z")
        rejected = self.fetch(context)
        self.assertEqual(rejected["issues"][0]["code"], "agent_run_inactive")
        self.assertEqual(self.service.read_case(self.token,self.case_id)["sources"], [])
        self.now = NOW
        self.callback = lambda: setattr(context,"deadline",0)
        context.resource_results.clear()
        with self.assertRaises(AgentFailure) as caught:
            self.fetch(context)
        self.assertEqual(caught.exception.issue["code"], "agent_timeout")
        context.deadline = time.monotonic()+60
        context.resource_results.clear()
        with patch.object(self.catalog,"collect",side_effect=TimeoutError), self.assertRaises(AgentFailure) as caught:
            self.fetch(context)
        self.assertEqual(caught.exception.issue["code"], "agent_timeout")
        self.assertEqual(context.terminal_issue["code"], "agent_timeout")

    def test_storage_rollback_reuses_catalog_and_commits_once(self):
        context = self.claim()
        with self.service._connection() as connection:
            connection.execute("CREATE TRIGGER reject_resources BEFORE INSERT ON events WHEN NEW.command_json LIKE '%resource.search%' BEGIN SELECT RAISE(ABORT, 'synthetic storage failure'); END")
        self.assertEqual(self.fetch(context)["status"], "unavailable")
        unchanged = self.service.read_case(self.token,self.case_id)
        self.assertEqual(unchanged["resources"]["state"], "not_requested")
        self.assertEqual(unchanged["sources"], [])
        with self.service._connection() as connection:
            connection.execute("DROP TRIGGER reject_resources")
        self.assertEqual(self.fetch(context)["status"], "applied")
        self.assertEqual(self.fetch(context)["status"], "already_applied")
        self.assertEqual(self.loads, 1)

    def test_malformed_backend_result_cannot_write_attribution_or_scope(self):
        context = self.claim()
        result = self.catalog.collect(build_query(self.service.read_case(self.token,self.case_id),{"location_scope":"current"}), context.expected_version)
        for mutate in (lambda r: r["items"][0]["source_ids"].append("wrong_source"),
                       lambda r: r["sources"][0].update(id="source_incident_forged"),
                       lambda r: r["items"][0]["coverage"].update(state="CA"),
                       lambda r: r["items"][0]["availability"].update(state="confirmed_available")):
            malformed = copy.deepcopy(result)
            mutate(malformed)
            rejected = self.service.commit_agent_resources(self.token,self.case_id,context.event_id,context.run_id,malformed,context.expected_version)
            self.assertEqual(rejected["status"], "rejected")
        changed_query = copy.deepcopy(result)
        changed_query["search"]["query"]["geography"]["place"] = "Other synthetic place"
        self.assertEqual(self.service.commit_agent_resources(self.token,self.case_id,context.event_id,context.run_id,changed_query,context.expected_version)["status"], "conflict")
        self.assertEqual(self.service.read_case(self.token,self.case_id)["sources"], [])

    def test_catalog_failure_retains_prior_referrals_under_original_query(self):
        context = self.claim()
        saved = self.fetch(context)["case_snapshot"]["resources"]
        self.service.finish_agent_turn(self.token,self.case_id,context.event_id,context.run_id,"Synthetic reply")
        next_context = self.claim("next_turn")
        self.asset["items"][-1]["source_ids"] = ["missing_source"]
        version = next_context.expected_version
        failed = self.fetch(next_context)
        self.assertEqual(failed["status"], "unavailable")
        self.assertEqual(failed["issues"][0]["code"], "resource_catalog_unavailable")
        self.assertEqual(failed["case_snapshot"]["resources"], saved)
        self.assertEqual(failed["case_snapshot"]["case_version"], version)

    def test_relevant_corrections_stale_saved_results_and_other_scope_does_not(self):
        context = self.claim()
        self.fetch(context)
        unrelated = self.correct("damaged_location", {"state":"CA"})
        self.assertEqual(unrelated["case_snapshot"]["resources"]["search"]["freshness"], "current")
        corrected = self.correct("requested_needs", ["lost_documents"])["case_snapshot"]
        self.assertEqual(corrected["resources"]["search"]["freshness"], "stale")
        self.assertEqual(corrected["resources"]["search"]["query"]["need_kinds"], ["shelter","transport"])
        self.assertTrue(all(source["freshness"] == "stale" for source in corrected["sources"]))
        self.service.finish_agent_turn(self.token,self.case_id,context.event_id,context.run_id,"Synthetic reply")
        fresh = self.fetch(self.claim("corrected_turn"))["case_snapshot"]
        self.assertEqual(fresh["resources"]["search"]["freshness"], "current")
        self.assertEqual(len(fresh["resources"]["items"]),1)
        self.assertEqual(len(fresh["sources"]),1)

    def test_intake_needs_and_location_changes_invalidate_referrals(self):
        context = self.claim()
        self.fetch(context)
        command = self.message("new_intake",context.expected_version)
        command.update(type="intake.submit",payload={"needs":["lost_documents"],"current_location":{"place":"Synthetic California","state":"CA"}})
        result = self.service.execute(self.token,command)
        self.assertEqual(result["case_snapshot"]["resources"]["search"]["freshness"],"stale")

    def test_resource_replacement_preserves_incident_attribution(self):
        from backend.stillhere.agent.registry import INCIDENT_TOOL
        from backend.stillhere.incidents import IncidentFacade
        from tests.test_incidents import FixtureTransport
        context = self.claim()
        context.incident_facade = IncidentFacade(FixtureTransport(),clock=lambda: self.now)
        registry = ToolRegistry(CASE_TOOLS + (RESOURCE_TOOL,INCIDENT_TOOL))
        incident = registry.invoke("get_incident_context",{"location_scope":"current"},context)
        incident_sources = incident["case_snapshot"]["sources"]
        first = self.fetch(context)["case_snapshot"]
        self.assertEqual(len(first["sources"]),5)
        self.service.finish_agent_turn(self.token,self.case_id,context.event_id,context.run_id,"Synthetic reply")
        second = self.fetch(self.claim("replacement_turn"))["case_snapshot"]
        self.assertEqual(len(second["sources"]),5)
        self.assertEqual([s for s in second["sources"] if s["id"].startswith("source_incident_")],incident_sources)

    def test_successful_no_match_is_saved_with_its_bounded_query(self):
        self.correct("current_location",{"state":"CA"})
        self.correct("requested_needs",["transport"])
        context = self.claim()
        saved = self.fetch(context)["case_snapshot"]
        self.assertEqual(saved["resources"]["state"],"no_match")
        self.assertEqual(saved["resources"]["search"]["query"]["need_kinds"],["transport"])
        self.assertEqual(saved["resources"]["items"],[])
        self.assertEqual(saved["sources"],[])

    def test_runtime_registration_provider_failure_and_replay_keep_accepted_referrals(self):
        class Provider:
            def reply(inner,snapshot,history,text,context,registry):
                registry.invoke("find_resources",{"location_scope":"current"},context)
                raise RuntimeError("synthetic provider failure after durable resources")
        runtime = AgentRuntime(self.service,AgentConfig(enable_resources=True),provider=Provider(),resource_catalog=self.catalog)
        self.assertIn("find_resources",runtime.registry.by_name)
        self.assertNotIn("find_resources",AgentRuntime(self.service).registry.by_name)
        result = runtime.handle(self.token,self.message())
        self.assertEqual(result["case_snapshot"]["resources"]["state"], "available")
        self.assertEqual(result["case_snapshot"]["conversation"]["turns"][-1]["state"], "failed")
        version = result["case_snapshot"]["case_version"]
        replay = runtime.handle(self.token,self.message())
        self.assertEqual(replay["case_snapshot"]["case_version"],version)
        self.assertEqual(self.loads,1)

    def test_resource_flag_is_opt_in_with_synthetic_environment(self):
        with patch.dict(os.environ,{},clear=True):
            self.assertFalse(AgentConfig.from_environment().enable_resources)
            os.environ["STILLHERE_AGENT_ENABLE_RESOURCES"] = "true"
            self.assertTrue(AgentConfig.from_environment().enable_resources)
            os.environ["STILLHERE_AGENT_ENABLE_RESOURCES"] = "yes"
            with self.assertRaises(ValueError):
                AgentConfig.from_environment()

    def test_user_run_resource_smoke_checks_saved_seeded_sources_reply_and_replay(self):
        from backend.stillhere.agent.smoke import main
        class Provider:
            def reply(inner,snapshot,history,text,context,registry):
                registry.invoke("find_resources",{"location_scope":"current"},context)
                return "Synthetic reviewed referrals are saved; availability remains unknown."
        def runtime(service,config,diagnostics=None):
            return AgentRuntime(service,config,provider=Provider(),diagnostics=diagnostics)
        log = Path(self.directory.name)/"synthetic-smoke.jsonl"
        output = io.StringIO()
        with patch("sys.argv",["smoke","--resources","--log-file",str(log)]), \
             patch("backend.stillhere.agent.smoke.AgentConfig.from_environment",return_value=AgentConfig(model_id="synthetic_model",region="synthetic_region")), \
             patch("backend.stillhere.agent.smoke.AgentRuntime",side_effect=runtime), \
             patch("backend.stillhere.agent.smoke.load_local_environment") as load_environment, redirect_stdout(output):
            self.assertEqual(main(),0)
        load_environment.assert_not_called()
        self.assertIn("durable seeded referrals/attribution/reply",output.getvalue())
        self.assertIn('"event": "smoke_passed"',log.read_text())
        self.assertNotIn("synthetic_model",log.read_text())
        self.assertNotIn("Synthetic Denver",log.read_text())
