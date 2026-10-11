"""Strict new-information proof; synthetic transport never counts as live evidence."""

import copy
import io
import json
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from backend.stillhere.agent import AgentConfig, AgentRuntime
from backend.stillhere.contracts import InvalidInput, utc_now, validate
from backend.stillhere.knowledge.fetch_smoke import SOURCE_ID, live_guidance, main as fetch_main
from backend.stillhere.knowledge.official import OfficialSourceFailure, OfficialSourceFetcher, PublicPageTransport, source_registry, source_url_allowed
from tests.test_knowledge import Opener, Response

URL = "https://www.usa.gov/replace-vital-documents"
QUOTE = "Contact your state motor vehicle agency for a replacement license or state ID card."
TEXT = "Synthetic public-page fixture. " + QUOTE + " Complete requirements and fees remain unknown."


class FixtureTransport:
    def __init__(self, fail=False, text=TEXT):
        self.fail, self.text, self.calls = fail, text, 0

    def get_text(self, source, deadline):
        self.calls += 1
        if self.fail:
            raise OfficialSourceFailure("source_http_error")
        return self.text, False


class LiveFetchExampleTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def fetched(self, **kwargs):
        return OfficialSourceFetcher(FixtureTransport(**kwargs)).fetch(SOURCE_ID, utc_now(), time.monotonic() + 10)

    def test_usagov_transport_keeps_exact_registered_https_url_and_extracts_useful_text(self):
        source = source_registry()[SOURCE_ID]
        opener = Opener(Response(("<main>" + TEXT + "</main>").encode(), url=URL))
        fetched = OfficialSourceFetcher(PublicPageTransport(opener)).fetch(SOURCE_ID, utc_now(), time.monotonic() + 10)
        self.assertEqual(live_guidance(fetched), QUOTE)
        self.assertEqual(fetched["receipt"]["jurisdiction"], {"country": "US", "state": None})
        self.assertEqual(fetched["receipt"]["data_mode"], "live")
        self.assertTrue(source_url_allowed(source, URL))
        for url in ("https://www.usa.gov/other", "https://dmv.colorado.gov/replace-vital-documents",
                    URL + "?private=value", "http://www.usa.gov/replace-vital-documents",
                    "https://user:pass@www.usa.gov/replace-vital-documents"):
            self.assertFalse(source_url_allowed(source, url))

    def test_failure_cannot_use_a_seed_or_count_as_live_success(self):
        fetched = self.fetched(fail=True)
        self.assertEqual(fetched["state"], "unavailable")
        self.assertIsNone(fetched["receipt"])
        with self.assertRaises(InvalidInput):
            live_guidance(fetched)

    def test_http_success_without_expected_guidance_is_not_a_working_example(self):
        with self.assertRaises(InvalidInput):
            live_guidance(self.fetched(text="Synthetic login/challenge page without ID guidance."))

    def test_forged_provenance_or_a_different_source_cannot_pass(self):
        original = self.fetched()
        for mutate in (lambda r: r["receipt"].update(content_sha256="0" * 64),
                       lambda r: r["receipt"].update(data_mode="seeded"),
                       lambda r: r.update(source_id="source_rule_co_renewal")):
            altered = copy.deepcopy(original)
            mutate(altered)
            with self.assertRaises(InvalidInput):
                live_guidance(altered)

    def test_national_guidance_is_fetchable_but_not_colorado_rule_submission_evidence(self):
        validate("OfficialSourceToolArguments", {"source_id": SOURCE_ID})
        common = {"source_id": SOURCE_ID, "program_id": "co_state_id_replacement", "base_version": "2026-10-10.1"}
        for schema, args in (("RuleCandidateToolArguments", {**common, "requirement_keys": ["email_access"],
                                                            "relationship": "all_of", "evidence_start": 0, "evidence_end": 30}),
                             ("RuleDiscrepancyToolArguments", {**common, "reason": "source_unavailable"})):
            with self.assertRaises(InvalidInput):
                validate(schema, args)

    def test_credential_free_example_prints_actual_public_guidance_and_provenance(self):
        output = io.StringIO()
        with patch("backend.stillhere.knowledge.fetch_smoke.OfficialSourceFetcher", return_value=OfficialSourceFetcher(FixtureTransport())), redirect_stdout(output):
            self.assertEqual(fetch_main(), 0)
        result = json.loads(output.getvalue())
        self.assertTrue(result["live_fetch_passed"])
        self.assertEqual(result["guidance_excerpt"], QUOTE)
        self.assertEqual(result["url"], URL)
        self.assertEqual(result["data_mode"], "live")
        self.assertIn("retrieved_at", result)
        self.assertNotIn("Complete requirements", output.getvalue())

    def test_credential_free_example_fails_on_fetch_failure_or_deadline(self):
        for fetcher in (OfficialSourceFetcher(FixtureTransport(fail=True)),):
            output = io.StringIO()
            with patch("backend.stillhere.knowledge.fetch_smoke.OfficialSourceFetcher", return_value=fetcher), redirect_stdout(output):
                self.assertEqual(fetch_main(), 1)
            self.assertFalse(json.loads(output.getvalue())["live_fetch_passed"])
        with patch("backend.stillhere.knowledge.fetch_smoke.OfficialSourceFetcher.fetch", side_effect=TimeoutError("private_marker")), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(fetch_main(), 1)
        self.assertNotIn("private_marker", output.getvalue())

    def run_agent_smoke(self, fail=False, reply=None, text=TEXT, mutate=False):
        from backend.stillhere.agent.smoke import main
        transport = FixtureTransport(fail=fail, text=text)
        class Provider:
            def reply(inner, snapshot, history, user_text, context, registry):
                registry.invoke("fetch_official_source", {"source_id": SOURCE_ID}, context)
                if mutate:
                    registry.invoke("correct_fact", {"fact_key": "mobility", "value": "no_car", "observed_at": utc_now()}, context)
                return reply if reply is not None else QUOTE + " " + URL
        def runtime(service, config, diagnostics=None):
            return AgentRuntime(service, config, provider=Provider(), diagnostics=diagnostics, official_fetcher=OfficialSourceFetcher(transport))
        log = Path(self.directory.name) / "fetch-smoke.jsonl"
        log.unlink(missing_ok=True)
        output = io.StringIO()
        with patch("sys.argv", ["smoke", "--fetch", "--log-file", str(log)]), \
             patch("backend.stillhere.agent.smoke.AgentConfig.from_environment", return_value=AgentConfig(model_id="synthetic_private_model", region="synthetic_region")), \
             patch("backend.stillhere.agent.smoke.AgentRuntime", side_effect=runtime), \
             patch("backend.stillhere.agent.smoke.load_local_environment") as load, redirect_stdout(output):
            status = main()
        load.assert_not_called()
        return status, [json.loads(line) for line in log.read_text().splitlines()], output.getvalue(), transport

    def test_strict_agent_smoke_requires_live_text_cited_reply_and_replay(self):
        status, records, output, transport = self.run_agent_smoke()
        self.assertEqual(status, 0)
        self.assertEqual(records[-1]["mode"], "fetch")
        self.assertEqual(records[-1]["retrieval_state"], "available")
        self.assertEqual(transport.calls, 1)
        self.assertIn(QUOTE, output)
        self.assertNotIn("synthetic_private_model", str(records))

    def test_strict_agent_smoke_rejects_fallback_wrong_text_or_uncited_reply(self):
        for kwargs, code in (({"fail": True}, "official_live_fetch_unavailable"),
                             ({"text": "Synthetic challenge page"}, "official_example_content_missing"),
                             ({"reply": "An answer from memory without the official source."}, "official_example_reply_missing")):
            with self.subTest(code=code):
                status, records, _, _ = self.run_agent_smoke(**kwargs)
                self.assertEqual(status, 1)
                self.assertEqual(records[-1]["code"], code)
                self.assertFalse(any(row["event"] == "smoke_passed" for row in records))

    def test_strict_read_only_smoke_rejects_domain_changes(self):
        status, records, _, _ = self.run_agent_smoke(mutate=True)
        self.assertEqual(status, 1)
        self.assertEqual(records[-1]["code"], "knowledge_domain_changed")
