"""Credential-free end-to-end C04 proof; all transport/data and storage are synthetic."""

import tempfile
import time
from pathlib import Path

from ..agent.registry import CASE_TOOLS, CANDIDATE_TOOL, DISCREPANCY_TOOL, OFFICIAL_TOOL, ToolRegistry
from ..agent.tools import AgentContext
from ..contracts import utc_now
from ..service import CaseService
from .manage import draft_review
from .official import OfficialSourceFetcher
from .review import ManualReviewAuthority
from .rules import ProgramRuleStore, build_query


class SyntheticTransport:
    def get_text(self, source, deadline):
        return "Synthetic public test evidence: email access and a payment method are available requirements in this mock renewal reference.", False


def main():
    with tempfile.TemporaryDirectory(prefix="stillhere-offline-knowledge-") as directory:
        service = CaseService(Path(directory)/"cases.sqlite3")
        token = service.create_session()["session_token"]
        snapshot = service.create_case(token,{"contract_version":"0.1","event_id":"create","time_zone":"America/Chicago"})["case_snapshot"]
        now = utc_now()
        issuer = {"contract_version":"0.1","case_id":snapshot["case_id"],"event_id":"issuer","expected_case_version":snapshot["case_version"],
                  "occurred_at":now,"channel":"dashboard","type":"fact.correct","payload":{"fact_key":"document_issuing_state","value":"CO","observed_at":now}}
        snapshot = service.execute(token,issuer)["case_snapshot"]
        command = {"contract_version":"0.1","case_id":snapshot["case_id"],"event_id":"knowledge_chat","expected_case_version":snapshot["case_version"],
                   "occurred_at":now,"channel":"chat","type":"conversation.message","payload":{"message_id":"synthetic_user","text":"Synthetic offline public review proof."}}
        service.execute(token,command)
        claim = service.claim_agent_turn(token,snapshot["case_id"],"knowledge_chat",60)
        context = AgentContext(service,token,snapshot["case_id"],"knowledge_chat",claim["run_id"],claim["snapshot"]["case_version"],
                               time.monotonic()+60,12,48000,official_fetcher=OfficialSourceFetcher(SyntheticTransport()))
        registry = ToolRegistry(CASE_TOOLS+(OFFICIAL_TOOL,CANDIDATE_TOOL,DISCREPANCY_TOOL))
        source_id = "source_rule_co_renewal"
        fetched = registry.invoke("fetch_official_source",{"source_id":source_id},context)
        assert fetched["state"] == "available"
        original_catalog = service.read_program_catalog()
        base = next(rule for rule in original_catalog["rules"] if rule["program_id"] == "co_state_id_replacement")
        arguments = {"program_id":base["program_id"],"base_version":base["version"],"source_id":source_id,
                     "requirement_keys":["email_access"],"relationship":"all_of","evidence_start":0,"evidence_end":80}
        submitted = registry.invoke("propose_rule_candidate",arguments,context)
        duplicate = registry.invoke("propose_rule_candidate",arguments,context)
        assert submitted["candidate_id"] == duplicate["candidate_id"] and duplicate["state"] == "already_submitted"
        discrepancy = registry.invoke("report_rule_discrepancy",{key:value for key,value in arguments.items() if key not in ("requirement_keys","relationship")} | {"reason":"requirements_changed"},context)
        assert discrepancy["state"] == "submitted"
        authority = ManualReviewAuthority("synthetic_reviewer")
        queue = service.read_review_queue(authority)
        assert len(queue) == 2 and all(item["review_state"] == "pending" for item in queue)
        assert service.read_program_catalog() == original_catalog
        assert service.read_case(token,snapshot["case_id"]) == claim["snapshot"]
        request = draft_review(service,authority,submitted["candidate_id"])
        request["event_id"] = "synthetic_manual_review"
        request["publication"]["rule"]["version"] = base["version"] + ".synthetic"
        approved = service.review_rule_candidate(authority,request)
        assert approved["review_state"] == "published"
        assert service.review_rule_candidate(authority,request)["status"] == "already_applied"
        restarted = CaseService(service.path)
        store = ProgramRuleStore(loader=restarted.read_program_catalog,version_loader=restarted.read_program_version)
        query = build_query(claim["snapshot"],{"program_id":base["program_id"]},utc_now())
        assert store.lookup(query)["rules"][0]["version"] == request["publication"]["rule"]["version"]
        query["requested_version"] = base["version"]
        assert store.lookup(query)["rules"][0] == base
        after = service.finish_agent_turn(token,snapshot["case_id"],"knowledge_chat",claim["run_id"],"Synthetic offline C04 proof completed.")
        replay = service.execute(token,command)
        assert replay["status"] == "already_applied" and replay["case_snapshot"]["case_version"] == after["case_version"]
    print("Offline C04 fetch, private-safe candidate/discrepancy queue, manual publication, immutable history, restart and replay passed. All evidence, transport and storage were synthetic; no credentials or network were used.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
