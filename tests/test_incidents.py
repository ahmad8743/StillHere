"""Synthetic C03 source, authority, persistence, replay and failure checks. No network."""

import copy
import io
import json
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from backend.stillhere.agent import AgentConfig, AgentRuntime
from backend.stillhere.agent.registry import CASE_TOOLS, INCIDENT_TOOL, ToolRegistry
from backend.stillhere.agent.tools import AgentContext, AgentFailure
from backend.stillhere.contracts import InvalidInput, empty_case, validate
from backend.stillhere.incidents import IncidentFacade, build_query
from backend.stillhere.incidents.adapters import request_url
from backend.stillhere.incidents.geography import validate_geography
from backend.stillhere.incidents.transport import MAX_BYTES, OfficialRedirect, PublicJSONTransport, SourceFailure
from backend.stillhere.service import CaseService

NOW = "2026-10-10T15:00:00Z"
GEO = {"place": "Synthetic Denver", "latitude": 39.7392, "longitude": -104.9903, "state": "CO", "county_fips": "08031"}


def epoch(value):
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def alert(identifier="synthetic_alert", **changes):
    properties = {"id": identifier, "status": "Actual", "messageType": "Alert", "event": "Flood Warning",
                  "headline": "Synthetic flood warning", "areaDesc": "Demonstration area",
                  "description": "Synthetic official context", "instruction": "Synthetic instruction",
                  "sent": "2026-10-10T14:00:00-00:00", "effective": "2026-10-10T14:00:00Z",
                  "expires": "2026-10-10T16:00:00Z", "ends": None,
                  "severity": "Severe", "certainty": "Observed", "urgency": "Immediate"}
    properties.update(changes)
    return {"type": "Feature", "id": "https://api.weather.gov/alerts/" + identifier, "properties": properties}


def quake(identifier="synthetic_quake", **changes):
    properties = {"type": "earthquake", "title": "Synthetic M 3.0 earthquake", "place": "Demonstration area",
                  "time": epoch("2026-10-09T15:00:00Z"), "updated": epoch("2026-10-10T14:00:00Z"),
                  "mag": 3.0, "status": "reviewed", "url": "https://earthquake.usgs.gov/earthquakes/eventpage/" + identifier}
    properties.update(changes)
    return {"type": "Feature", "id": identifier, "properties": properties,
            "geometry": {"type": "Point", "coordinates": [-104.9903, 39.7392, 5.5]}}


def declaration(identifier="synthetic_decl", **changes):
    result = {"id": identifier, "state": "CO", "fipsStateCode": "08", "fipsCountyCode": "031",
              "declarationDate": "2026-10-01T00:00:00Z", "incidentBeginDate": "2026-09-25T00:00:00Z",
              "incidentEndDate": "2026-09-30T00:00:00Z", "declarationTitle": "SYNTHETIC FLOOD",
              "incidentType": "Flood", "declarationType": "DR", "disasterNumber": 9999,
              "designatedArea": "Denver (County)", "lastRefresh": "2026-10-09T00:00:00Z",
              "ihProgramDeclared": True, "iaProgramDeclared": True, "paProgramDeclared": False,
              "hmProgramDeclared": None}
    result.update(changes)
    return result


class FixtureTransport:
    def __init__(self):
        self.payloads = {"nws": {"type": "FeatureCollection", "features": [alert()]},
                         "usgs": {"type": "FeatureCollection", "features": [quake()]},
                         "openfema": {"DisasterDeclarationsSummaries": [declaration()]}}
        self.calls = []
        self.callback = None

    def get_json(self, url, deadline):
        provider = next(name for name in self.payloads if {"nws": "api.weather.gov", "usgs": "earthquake.usgs.gov", "openfema": "www.fema.gov"}[name] == urlsplit(url).hostname)
        self.calls.append((provider, url))
        if self.callback:
            callback, self.callback = self.callback, None
            callback()
        value = self.payloads[provider]
        if isinstance(value, Exception):
            raise value
        return copy.deepcopy(value)


class IncidentSourceTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = empty_case("synthetic", "America/Denver", NOW)
        self.snapshot["facts"]["current_location"] = {"value": copy.deepcopy(GEO), "state": "user_reported", "observed_at": NOW, "source_ids": []}
        self.snapshot["facts"]["damaged_location"] = {"value": {"place": "Synthetic California", "state": "CA", "county_fips": "06037"}, "state": "user_reported", "observed_at": NOW, "source_ids": []}
        self.transport = FixtureTransport()
        self.facade = IncidentFacade(self.transport, clock=lambda: NOW)

    def collect(self, scope="current"):
        query = build_query(self.snapshot, {"location_scope": scope}, NOW)
        return self.facade.collect(query, self.snapshot["case_version"])

    def test_all_sources_normalize_timestamps_geography_and_program_unknowns(self):
        result = self.collect()
        self.assertEqual(result["state"], "available")
        validate("IncidentContext", result)
        nws = result["providers"]["nws"]
        self.assertEqual(nws["records"][0]["source_updated_at"], "2026-10-10T14:00:00.000Z")
        self.assertEqual(nws["source"]["fresh_until"], "2026-10-10T15:05:00.000Z")
        usgs = result["providers"]["usgs"]["records"][0]
        self.assertEqual(usgs["details"]["magnitude"], 3.0)
        self.assertEqual(usgs["geographic_scope"]["match"], "within_radius")
        fema = result["providers"]["openfema"]["records"][0]
        self.assertEqual(fema["geographic_scope"]["county_fips"], "08031")
        self.assertIsNone(fema["details"]["designated_programs"]["hazard_mitigation"])
        self.assertEqual(fema["details"]["household_eligibility"], "unknown")
        self.assertIsNone(fema["expires_at"])

    def test_current_and_damaged_locations_do_not_cross_or_geocode_by_guess(self):
        query = build_query(self.snapshot, {"location_scope": "damaged", "lookback_days": 7}, NOW)
        self.assertEqual(query["geography"]["state"], "CA")
        self.assertNotIn("latitude", query["geography"])
        self.assertIsNone(request_url("usgs", query))
        fema_params = parse_qs(urlsplit(request_url("openfema", query)).query)
        self.assertIn("state eq 'CA'", fema_params["$filter"][0])
        self.assertIn("fipsCountyCode eq '037'", fema_params["$filter"][0])
        self.assertNotIn("08031", str(query))
        self.assertNotIn("limit", parse_qs(urlsplit(request_url("nws", query)).query))

    def test_absent_place_only_and_stale_geography_return_unknown_without_network(self):
        for value, state in ((None, "unknown"), ({"place": "Synthetic city"}, "user_reported"), (GEO, "stale")):
            self.snapshot["facts"]["current_location"].update(value=value, state=state)
            self.transport.calls.clear()
            result = self.collect()
            self.assertEqual(result["state"], "unknown")
            self.assertEqual(self.transport.calls, [])
            self.assertTrue(all(p["issue"]["code"] == "incident_geography_unknown" for p in result["providers"].values()))

    def test_invalid_coordinates_and_county_state_mismatch_are_not_sent(self):
        for value in (dict(GEO, latitude=91), dict(GEO, longitude=-181), dict(GEO, latitude=True),
                      dict(GEO, latitude=float("nan")), dict(GEO, county_fips="06037"), {"latitude": 39.0}):
            with self.assertRaises(InvalidInput):
                validate_geography(value)
            self.snapshot["facts"]["current_location"]["value"] = value
            self.transport.calls.clear()
            self.assertEqual(self.collect()["query"]["geography_state"], "invalid")
            self.assertEqual(self.transport.calls, [])
        for days in (0, 366, True):
            with self.assertRaises(InvalidInput):
                build_query(self.snapshot, {"location_scope": "current", "lookback_days": days}, NOW)

    def test_expired_cancelled_and_test_alerts_are_not_current_context(self):
        self.transport.payloads["nws"]["features"] = [alert(expires=NOW), alert(messageType="Cancel"), alert(status="Test"), alert(ends="2026-10-10T14:59:00Z")]
        provider = self.collect()["providers"]["nws"]
        self.assertEqual(provider["state"], "no_match")
        self.assertEqual(provider["records"], [])

    def test_alert_expiry_shortens_freshness_and_instruction_excerpt_is_bounded(self):
        self.transport.payloads["nws"]["features"] = [alert(expires="2026-10-10T15:01:00Z", instruction="x" * 1000)]
        provider = self.collect()["providers"]["nws"]
        self.assertEqual(provider["source"]["fresh_until"], "2026-10-10T15:01:00.000Z")
        self.assertEqual(len(provider["records"][0]["instructions"]), 512)
        self.assertTrue(provider["records"][0]["text_truncated"])

    def test_out_of_radius_old_nonquake_and_small_events_do_not_match(self):
        distant = quake("distant")
        distant["geometry"]["coordinates"] = [0, 0, 1]
        self.transport.payloads["usgs"]["features"] = [distant, quake("old", time=epoch("2020-01-01T00:00:00Z")), quake("explosion", type="explosion"), quake("small", mag=1.0)]
        self.assertEqual(self.collect()["providers"]["usgs"]["state"], "no_match")

    def test_wrong_county_state_and_old_declarations_do_not_match(self):
        self.transport.payloads["openfema"]["DisasterDeclarationsSummaries"] = [
            declaration("county", fipsCountyCode="001"), declaration("state", state="CA", fipsStateCode="06", fipsCountyCode="037"),
            declaration("old", declarationDate="2020-01-01T00:00:00Z")]
        self.assertEqual(self.collect()["providers"]["openfema"]["state"], "no_match")

    def test_statewide_declaration_and_state_only_lookup_do_not_claim_county_match(self):
        self.transport.payloads["openfema"]["DisasterDeclarationsSummaries"] = [declaration(fipsCountyCode="000", designatedArea="Statewide")]
        record = self.collect()["providers"]["openfema"]["records"][0]
        self.assertEqual(record["geographic_scope"]["match"], "state_query")
        self.assertIsNone(record["geographic_scope"]["county_fips"])
        self.assertEqual(record["details"]["household_eligibility"], "unknown")

    def test_empty_success_differs_from_timeout_and_malformed_data(self):
        self.transport.payloads = {"nws": {"type": "FeatureCollection", "features": []},
                                   "usgs": SourceFailure("source_timeout_or_network"), "openfema": {"wrong_schema": []}}
        result = self.collect()
        self.assertEqual(result["state"], "partial")
        self.assertEqual(result["providers"]["nws"]["state"], "no_match")
        self.assertEqual(result["providers"]["usgs"]["state"], "unavailable")
        self.assertEqual(result["providers"]["openfema"]["issue"]["code"], "source_invalid_response")
        self.assertTrue(result["providers"]["openfema"]["source"]["referral_url"].startswith("https://www.fema.gov/"))

    def test_provider_text_cannot_select_urls_or_turn_string_flags_into_booleans(self):
        self.transport.payloads["nws"]["features"][0]["id"] = "https://untrusted.example/secret_fixture"
        self.transport.payloads["openfema"]["DisasterDeclarationsSummaries"][0]["iaProgramDeclared"] = "false"
        result = self.collect()
        self.assertEqual(result["providers"]["nws"]["state"], "unavailable")
        self.assertEqual(result["providers"]["openfema"]["state"], "unavailable")
        self.assertNotIn("secret_fixture", str(result))

    def test_limits_and_duplicate_identity_are_explicit(self):
        self.transport.payloads["nws"]["features"] = [alert("synthetic_" + str(n)) for n in range(7)]
        provider = self.collect()["providers"]["nws"]
        self.assertEqual(len(provider["records"]), 5)
        self.assertTrue(provider["truncated"])
        self.transport.payloads["nws"]["features"] = [alert(), alert()]
        self.assertEqual(len(self.collect()["providers"]["nws"]["records"]), 1)

    def test_facade_deadline_discards_late_response_and_does_not_dispatch_more_requests(self):
        monotonic = [100.0]
        self.transport.callback = lambda: monotonic.__setitem__(0, 101.0)
        query = build_query(self.snapshot, {"location_scope": "current"}, NOW)
        with patch("backend.stillhere.incidents.facade.time.monotonic", side_effect=lambda: monotonic[0]):
            result = self.facade.collect(query, 1, deadline=100.5)
        self.assertEqual(result["state"], "unavailable")
        self.assertEqual(len(self.transport.calls), 1)
        self.assertTrue(all(provider["issue"]["code"] == "source_timeout" and not provider["records"] for provider in result["providers"].values()))


class IncidentPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "synthetic.sqlite3"
        self.now = NOW
        self.service = CaseService(self.path, clock=lambda: self.now)
        self.token = self.service.create_session()["session_token"]
        self.case = self.service.create_case(self.token, {"contract_version": "0.1", "event_id": "create", "time_zone": "America/Denver",
                    "intake": {"current_location": GEO}})["case_snapshot"]
        self.case_id = self.case["case_id"]
        self.transport = FixtureTransport()
        self.facade = IncidentFacade(self.transport, clock=lambda: self.now)
        self.registry = ToolRegistry(CASE_TOOLS + (INCIDENT_TOOL,))

    def message(self, event="incident_chat", version=1):
        return {"contract_version": "0.1", "case_id": self.case_id, "event_id": event, "expected_case_version": version,
                "occurred_at": NOW, "channel": "chat", "type": "conversation.message",
                "payload": {"message_id": "user_" + event, "text": "Get incident context for my reported current location."}}

    def claim(self):
        self.service.execute(self.token, self.message())
        claim = self.service.claim_agent_turn(self.token, self.case_id, "incident_chat", 60)
        return AgentContext(self.service, self.token, self.case_id, "incident_chat", claim["run_id"], claim["snapshot"]["case_version"],
                            time.monotonic() + 60, 10, 48000, incident_facade=self.facade)

    def fetch(self, context):
        return self.registry.invoke("get_incident_context", {"location_scope": "current"}, context)

    def test_context_and_sources_persist_with_audit_and_single_effect_replay(self):
        context = self.claim()
        result = self.fetch(context)
        self.assertEqual(result["status"], "applied")
        first_version = result["case_snapshot"]["case_version"]
        self.assertEqual(self.fetch(context)["status"], "already_applied")
        self.assertEqual(len(self.transport.calls), 3)
        restored = CaseService(self.path).read_case(self.token, self.case_id)
        self.assertEqual(restored["case_version"], first_version)
        self.assertEqual(len(restored["sources"]), 3)
        self.assertEqual(restored["incident_context"]["current"]["state"], "available")
        self.assertIsNone(restored["shared_location"])
        self.assertEqual(restored["facts"]["current_location"]["value"], GEO)
        with self.service._connection() as connection:
            row = connection.execute("SELECT before_case_json FROM events WHERE command_json LIKE '%incident.context%'").fetchone()
            self.assertNotIn("incident_context", json.loads(row[0]))

    def test_unauthorized_or_model_selected_authority_never_triggers_lookup(self):
        context = self.claim()
        for extra in ({"case_id": "another_case"}, {"latitude": 0}, {"url": "https://untrusted.example"}):
            result = self.registry.invoke("get_incident_context", {"location_scope": "current", **extra}, context)
            self.assertEqual(result["error"]["code"], "invalid_tool_input")
        context.token = self.service.create_session()["session_token"]
        self.assertEqual(self.fetch(context)["error"]["code"], "case_unavailable")
        self.assertEqual(self.transport.calls, [])

    def test_concurrent_input_change_conflicts_and_blocks_followup_write(self):
        context = self.claim()
        def change():
            command = self.message("external", context.expected_version)
            command.update(type="fact.correct", payload={"fact_key": "current_location", "value": {"state": "CA"}, "observed_at": NOW})
            self.service.execute(self.token, command)
        self.transport.callback = change
        self.assertEqual(self.fetch(context)["status"], "conflict")
        self.assertNotIn("incident_context", self.service.read_case(self.token, self.case_id))
        with self.assertRaises(AgentFailure):
            self.fetch(context)

    def test_expired_run_rejects_result_without_source_or_case_write(self):
        context = self.claim()
        self.transport.callback = lambda: setattr(self, "now", "2026-10-10T15:01:01Z")
        result = self.fetch(context)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["issues"][0]["code"], "agent_run_inactive")
        self.assertEqual(self.service.read_case(self.token, self.case_id)["sources"], [])

    def test_provider_failure_keeps_reported_facts_and_persists_visible_unavailability(self):
        self.transport.payloads = {name: SourceFailure("source_timeout_or_network") for name in self.transport.payloads}
        context = self.claim()
        result = self.fetch(context)
        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["case_snapshot"]["incident_context"]["current"]["state"], "unavailable")
        self.assertEqual(result["case_snapshot"]["facts"]["current_location"]["value"], GEO)

    def test_new_turn_retrieves_again_and_replaces_sources_without_growth(self):
        context = self.claim()
        self.fetch(context)
        self.service.finish_agent_turn(self.token, self.case_id, context.event_id, context.run_id, "Synthetic reply.")
        snapshot = self.service.read_case(self.token, self.case_id)
        self.service.execute(self.token, self.message("new_turn", snapshot["case_version"]))
        claim = self.service.claim_agent_turn(self.token, self.case_id, "new_turn", 60)
        other = AgentContext(self.service, self.token, self.case_id, "new_turn", claim["run_id"], claim["snapshot"]["case_version"], time.monotonic()+60, 10, 48000, incident_facade=self.facade)
        self.fetch(other)
        self.assertEqual(len(self.transport.calls), 6)
        self.assertEqual(len(self.service.read_case(self.token, self.case_id)["sources"]), 3)

    def test_location_correction_marks_retained_context_stale_and_invalidates_freshness(self):
        context = self.claim()
        self.fetch(context)
        command = self.message("location_change", context.expected_version)
        command.update(type="fact.correct", payload={"fact_key": "current_location", "value": {"state": "CA"}, "observed_at": NOW})
        result = self.service.execute(self.token, command)
        retained = result["case_snapshot"]["incident_context"]["current"]
        self.assertEqual(retained["state"], "stale")
        self.assertEqual(retained["query"]["geography"]["state"], "CO")
        self.assertTrue(all(source["fresh_until"] <= NOW for source in result["case_snapshot"]["sources"]))
        self.assertEqual(len(self.transport.calls), 3)

    def test_invalid_backend_result_rejects_without_partial_source_write(self):
        context = self.claim()
        query = build_query(self.service.read_case(self.token, self.case_id), {"location_scope": "current"}, NOW)
        result = self.facade.collect(query, context.expected_version)
        result["providers"]["nws"]["records"][0]["source_id"] = "wrong_source"
        rejected = self.service.commit_agent_incident_context(self.token, self.case_id, context.event_id, context.run_id, result, context.expected_version)
        self.assertEqual(rejected["status"], "rejected")
        self.assertEqual(self.service.read_case(self.token, self.case_id)["sources"], [])
        malformed = self.service.commit_agent_incident_context(self.token, self.case_id, context.event_id, context.run_id, {}, context.expected_version)
        self.assertEqual(malformed["issues"][0]["code"], "invalid_input")

    def test_current_and_damaged_contexts_and_sources_persist_separately(self):
        context = self.claim()
        self.fetch(context)
        self.registry.invoke("correct_fact", {"fact_key": "damaged_location", "value": GEO, "observed_at": NOW}, context)
        result = self.registry.invoke("get_incident_context", {"location_scope": "damaged"}, context)
        snapshot = result["case_snapshot"]
        self.assertEqual(set(snapshot["incident_context"]), {"current", "damaged"})
        self.assertEqual(snapshot["incident_context"]["current"]["state"], "available")
        current = snapshot["incident_context"]["current"]["providers"]["nws"]["records"][0]
        damaged = snapshot["incident_context"]["damaged"]["providers"]["nws"]["records"][0]
        self.assertNotEqual(current["id"], damaged["id"])
        self.assertEqual(len({source["id"] for source in snapshot["sources"]}), 6)

    def test_storage_failure_rolls_back_context_and_sources_and_cached_retry_is_one_effect(self):
        context = self.claim()
        with self.service._connection() as connection:
            connection.execute("CREATE TRIGGER reject_incident BEFORE INSERT ON events WHEN NEW.command_json LIKE '%incident.context%' BEGIN SELECT RAISE(ABORT, 'synthetic storage failure'); END")
        self.assertEqual(self.fetch(context)["status"], "unavailable")
        snapshot = self.service.read_case(self.token, self.case_id)
        self.assertNotIn("incident_context", snapshot)
        self.assertEqual(snapshot["sources"], [])
        with self.service._connection() as connection:
            connection.execute("DROP TRIGGER reject_incident")
        self.assertEqual(self.fetch(context)["status"], "applied")
        self.assertEqual(self.fetch(context)["status"], "already_applied")
        self.assertEqual(len(self.transport.calls), 3)

    def test_runtime_registration_is_explicit_and_incident_results_reach_reply(self):
        class Provider:
            def reply(inner, snapshot, history, text, context, registry):
                result = registry.invoke("get_incident_context", {"location_scope": "current"}, context)
                return "Synthetic incident state: " + result["case_snapshot"]["incident_context"]["current"]["state"]
        config = AgentConfig(enable_incidents=True)
        runtime = AgentRuntime(self.service, config, provider=Provider(), incident_facade=self.facade)
        self.assertIn("get_incident_context", runtime.registry.by_name)
        result = runtime.handle(self.token, self.message())
        self.assertEqual(result["case_snapshot"]["conversation"]["turns"][-1]["text"], "Synthetic incident state: available")
        self.assertEqual(runtime.handle(self.token, self.message())["status"], "already_applied")
        self.assertEqual(len(self.transport.calls), 3)
        self.assertNotIn("get_incident_context", AgentRuntime(self.service).registry.by_name)

    def test_incident_model_smoke_checks_saved_sources_reply_and_replay_without_credentials(self):
        from backend.stillhere.agent.smoke import main
        class Provider:
            def reply(inner, snapshot, history, text, context, registry):
                registry.invoke("get_incident_context", {"location_scope": "current"}, context)
                return "Synthetic incident reply; source flags do not establish eligibility."
        def runtime(service, config, diagnostics=None):
            return AgentRuntime(service, config, provider=Provider(), diagnostics=diagnostics,
                                incident_facade=IncidentFacade(FixtureTransport()))
        log = Path(self.directory.name) / "synthetic-smoke.jsonl"
        output = io.StringIO()
        with patch("sys.argv", ["smoke", "--incidents", "--log-file", str(log)]), \
             patch("backend.stillhere.agent.smoke.AgentConfig.from_environment", return_value=AgentConfig(model_id="synthetic_model", region="synthetic_region")), \
             patch("backend.stillhere.agent.smoke.AgentRuntime", side_effect=runtime), \
             patch("backend.stillhere.agent.smoke.load_local_environment") as load_environment, redirect_stdout(output):
            self.assertEqual(main(), 0)
        load_environment.assert_not_called()
        self.assertIn("durable context/attribution/reply", output.getvalue())
        self.assertIn('"event": "smoke_passed"', log.read_text())
        self.assertNotIn("synthetic_model", log.read_text())
        self.assertNotIn("Synthetic Denver", log.read_text())


class IncidentTransportTests(unittest.TestCase):
    def transport(self, body=b'{}', status=200):
        class Response(io.BytesIO):
            pass
        response = Response(body)
        response.status = status
        class Opener:
            def open(inner, request, timeout):
                self.request, self.timeout = request, timeout
                return response
        return PublicJSONTransport(Opener())

    def test_transport_has_fixed_public_headers_and_rejects_unapproved_hosts(self):
        transport = self.transport(b'{"features":[]}')
        self.assertEqual(transport.get_json("https://api.weather.gov/alerts/active", time.monotonic()+10), {"features": []})
        self.assertLessEqual(self.timeout, 6)
        self.assertNotIn("Authorization", dict(self.request.header_items()))
        self.assertIn("StillHere", self.request.get_header("User-agent"))
        for url in ("http://api.weather.gov/alerts", "https://localhost/", "https://user:pass@api.weather.gov/alerts"):
            with self.assertRaises(SourceFailure):
                self.transport().get_json(url, time.monotonic()+10)

    def test_204_empty_and_invalid_or_oversized_json_have_distinct_results(self):
        self.assertEqual(self.transport(status=204).get_json("https://earthquake.usgs.gov/fdsnws/event/1/query", time.monotonic()+10)["features"], [])
        for body, code in ((b'{"x":NaN}', "source_invalid_response"), (b'{"x":1,"x":2}', "source_invalid_response"), (b'not json', "source_invalid_response"), (b'x'*(MAX_BYTES+1), "source_response_limit")):
            with self.assertRaises(SourceFailure) as caught:
                self.transport(body).get_json("https://api.weather.gov/alerts/active", time.monotonic()+10)
            self.assertEqual(caught.exception.code, code)

    def test_deadline_and_rate_limit_and_cross_host_redirect_are_bounded(self):
        with self.assertRaises(SourceFailure):
            self.transport().get_json("https://api.weather.gov/alerts/active", time.monotonic()-1)
        class Opener:
            def open(inner, request, timeout):
                raise HTTPError(request.full_url, 429, "secret_fixture_message", {}, io.BytesIO(b"secret_fixture_body"))
        with self.assertRaises(SourceFailure) as caught:
            PublicJSONTransport(Opener()).get_json("https://api.weather.gov/alerts/active", time.monotonic()+10)
        self.assertEqual(str(caught.exception), "source_rate_limited")
        from urllib.request import Request
        with self.assertRaises(SourceFailure):
            OfficialRedirect().redirect_request(Request("https://api.weather.gov/alerts/active"), None, 302, "", {}, "https://untrusted.example/")


if __name__ == "__main__":
    unittest.main()
