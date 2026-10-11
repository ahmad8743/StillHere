"""User-run live Bedrock proof with a disposable synthetic case; never prints secrets."""

import argparse
import re
import tempfile
from dataclasses import replace
from pathlib import Path

from ..contracts import utc_now
from ..service import CaseService
from .config import AgentConfig, load_local_environment
from .diagnostics import SafeDiagnostics, record
from .runtime import AgentRuntime
from .registry import ToolRegistry


class RuleProofRegistry(ToolRegistry):
    """Inspect validated public rule results for this disposable CLI proof only."""
    def __init__(self, definitions):
        super().__init__(definitions)
        self.rule_result = None
        self.public_results = {}
        self.planner_result = None
        self.planner_calls = 0
        self.plan_results = []
        self.task_results = []

    def invoke(self, name, arguments, context):
        result = super().invoke(name, arguments, context)
        if name == "retrieve_program_rules" and "error" not in result:
            self.rule_result = result
        if name in ("fetch_official_source", "propose_rule_candidate", "report_rule_discrepancy") and "error" not in result:
            self.public_results[name] = result
        if name == "evaluate_recovery_options" and "error" not in result:
            self.planner_result = result
            self.planner_calls += 1
        if name == "revise_recovery_plan" and "error" not in result:
            self.plan_results.append(result)
        if name == "update_task" and "error" not in result:
            self.task_results.append(result)
        return result


def main():
    parser = argparse.ArgumentParser(description="Live Strands/Bedrock synthetic tool proof")
    parser.add_argument("--env-file", help="Explicit optional local configuration file")
    parser.add_argument("--log-file", default="var/agent-smoke.jsonl", help="Safe phase/error-code log (default: var/agent-smoke.jsonl)")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--check-access", action="store_true", help="Read-only account/model activation checks; no inference or case writes")
    modes.add_argument("--incidents", action="store_true", help="Live model/C03 proof using a disposable case and synthetic Denver geography")
    modes.add_argument("--resources", action="store_true", help="Live model/C04 proof using reviewed seeded referrals on a disposable synthetic Colorado case")
    modes.add_argument("--rules", action="store_true", help="Live model/C04 read-only rule proof using an explicit synthetic Colorado document issuer")
    modes.add_argument("--knowledge", action="store_true", help="Live model/C04 official-fetch and unpublished public-review submission proof")
    modes.add_argument("--fetch", action="store_true", help="Strict successful live USAGov fetch, source-backed reply and replay proof; unavailable sources fail")
    modes.add_argument("--planner", action="store_true", help="Read-only C05 no-car evaluation, sourced alternatives, unknowns, saved reply and replay proof")
    modes.add_argument("--plan", action="store_true", help="C05 saved plan, user-reported task completion, preserving revision and replay proof")
    parser.add_argument("--expected-account-id", help="With --check-access, privately compare the 12-digit console account ID; never prints or logs it")
    args = parser.parse_args()
    if args.expected_account_id is not None and (not args.check_access or not re.fullmatch(r"[0-9]{12}", args.expected_account_id)):
        parser.error("--expected-account-id requires --check-access and a 12-digit account ID.")
    diagnostics = SafeDiagnostics(args.log_file)
    mode = "plan" if args.plan else "planner" if args.planner else "fetch" if args.fetch else "knowledge" if args.knowledge else "rules" if args.rules else "resources" if args.resources else "incidents" if args.incidents else "access" if args.check_access else "default"
    diagnostics.record("smoke_started", mode=mode)
    print("Safe diagnostic log:", diagnostics.path)
    if args.env_file:
        load_local_environment(args.env_file)
    config = AgentConfig.from_environment()
    if args.incidents:
        config = replace(config, enable_incidents=True)
    if args.resources:
        config = replace(config, enable_resources=True)
    if args.rules:
        config = replace(config, enable_rules=True)
    if args.knowledge:
        config = replace(config, enable_rule_review=True)
    if args.fetch:
        config = replace(config, enable_official_sources=True, enable_rule_review=False)
    if args.planner:
        config = replace(config, enable_planner=True, enable_rules=False, enable_intake=False,
                         enable_incidents=False, enable_resources=False, enable_official_sources=False, enable_rule_review=False,
                         enable_plan_revision=False, enable_tasks=False)
    if args.plan:
        config = replace(config, enable_plan_revision=True, enable_tasks=True, enable_planner=False, enable_rules=False,
                         enable_intake=False, enable_incidents=False, enable_resources=False, enable_official_sources=False,
                         enable_rule_review=False, max_turns=max(6, config.max_turns), max_total_tokens=max(24000, config.max_total_tokens))
    if config.missing_provider_settings:
        record(diagnostics, "config_missing", code="agent_not_configured")
        print("Live proof incomplete: agent_not_configured")
        print("Missing required settings:", ", ".join(config.missing_provider_settings))
        print("Set these values in the requested environment file or process environment, then rerun.")
        return 1
    record(diagnostics, "config_ready")
    if args.check_access:
        from .access import access_ready, check_access
        status = check_access(config, diagnostics, expected_account_id=args.expected_account_id)
        for key, value in status.items():
            print(key + ":", value)
        provider_failure = diagnostics.provider_failure or {}
        for field in ("code", "reason", "error_type"):
            if field in provider_failure:
                print("Access check error " + field + ":", provider_failure[field])
        print("Read-only checks completed. Live inference remains a separate proof.")
        return 0 if access_ready(status) else 1
    with tempfile.TemporaryDirectory(prefix="stillhere-bedrock-proof-") as directory:
        service = CaseService(Path(directory) / "cases.sqlite3")
        token = service.create_session()["session_token"]
        request = {
            "contract_version": "0.1", "event_id": "live_proof_create", "time_zone": "America/Chicago",
        }
        if args.incidents or args.resources:
            request["intake"] = {"current_location": {"place": "Synthetic Denver", "latitude": 39.7392,
                "longitude": -104.9903, "state": "CO", "county_fips": "08031"}}
        if args.resources:
            request["intake"]["needs"] = ["shelter", "food_water", "transport"]
        snapshot = service.create_case(token, request)["case_snapshot"]
        now = utc_now()
        if args.rules or args.knowledge or args.planner or args.plan:
            correction = {"contract_version": "0.1", "case_id": snapshot["case_id"], "event_id": "live_proof_issuer",
                          "expected_case_version": snapshot["case_version"], "occurred_at": now, "channel": "dashboard",
                          "type": "fact.correct", "payload": {"fact_key": "document_issuing_state", "value": "CO", "observed_at": now}}
            snapshot = service.execute(token, correction)["case_snapshot"]
        if args.planner or args.plan:
            for key, value in (("credential_lost", True), ("mobility", "no_car"),
                               ("office_transport_available", False), ("internet_access", True)):
                correction = {"contract_version": "0.1", "case_id": snapshot["case_id"], "event_id": "live_proof_" + key,
                              "expected_case_version": snapshot["case_version"], "occurred_at": now, "channel": "dashboard",
                              "type": "fact.correct", "payload": {"fact_key": key, "value": value, "observed_at": now}}
                snapshot = service.execute(token, correction)["case_snapshot"]
        text = ("This is a synthetic test. Call get_incident_context for location_scope current with lookback_days 30, "
                "using the reported case geography. Reply after checking each provider state. Distinguish no matching records "
                "from missing geography or failed sources; do not claim household eligibility or absence of a disaster."
                if args.incidents else f"This is a synthetic test. I have no car as of {now}. Call read_case, then correct_fact to save mobility as no_car with that observation time. Reply after the tool succeeds.")
        if args.resources:
            text = ("This is a synthetic test. Call find_resources for location_scope current using the reported case needs and geography. "
                    "Reply with at least one saved referral contact/source. These are reviewed seeded routes, not live capacity checks; "
                    "keep resource availability, service requirements and household eligibility unknown.")
        if args.rules:
            text = ("This is a synthetic test. Call retrieve_program_rules for program_id co_state_id_replacement using the explicitly "
                    "reported document issuer. Explain the returned online and office alternatives with official source links. "
                    "Keep prerequisites, complete eligibility, current fees and unstated effective dates unknown. Do not modify the case or request credential numbers.")
        if args.knowledge:
            text = ("This is a synthetic test. Call fetch_official_source with source_id source_rule_co_renewal. "
                    "For program co_state_id_replacement and base_version 2026-10-10.1: if the retrieval state is available, "
                    "call propose_rule_candidate with a supported known requirement key (email_access or renewal_documents_available), "
                    "relationship all_of and a nonempty public-text evidence span of at most 100 characters; also call "
                    "report_rule_discrepancy with reason fee_unknown and a public evidence span. If retrieval is unavailable, "
                    "call report_rule_discrepancy with reason source_unavailable and no evidence offsets. "
                    "These are pending public review submissions; do not claim discrepancy confirmation or publication. "
                    "Keep household domains unchanged and never request or copy credentials/private household details.")
        if args.fetch:
            text = ("This is a synthetic test of fetching new public information. Call fetch_official_source with "
                    "source_id source_usagov_lost_documents. If it succeeds, explain who the fetched official page "
                    "says to contact for a lost state ID. Quote the returned short sentence beginning 'Contact your "
                    "state motor vehicle agency' only if present, and cite the returned official URL. "
                    "Do not invent an answer if retrieval fails. Keep fees, complete requirements and household "
                    "eligibility unknown. This is a read-only example; do not change facts, submit review material "
                    "or publish policy. Never request credential numbers.")
        if args.planner:
            text = ("This is a synthetic test. Call evaluate_recovery_options for program_id co_state_id_replacement. "
                    "Use the case's explicit Colorado issuer, lost-ID and no-car/transport facts. Explain the returned "
                    "online provisional alternative and blocked office route. Include the words online, office and unknown, "
                    "and cite the online option's official_url from the tool. Keep eligibility, fees and transport costs unknown. "
                    "Do not change any facts, saved plan, tasks, finances, policy or applications. Never request document numbers.")
        if args.plan:
            text = ("This is a synthetic test. First call revise_recovery_plan for program_id co_state_id_replacement. "
                    "I report completing the online route in this synthetic case; call update_task with that saved action ID and status completed. "
                    "Then call revise_recovery_plan again for the same program, preserving my reported completed work. "
                    "Reply with the words saved, completed and unknown, and cite the online action's official_url. "
                    "Completion is user-reported; eligibility, current costs and agency outcomes remain unknown. "
                    "Do not correct facts, record money, change policy or submit an application.")
        catalog_before = service.read_program_catalog() if args.knowledge or args.fetch or args.planner or args.plan else None
        command = {
            "contract_version": "0.1", "case_id": snapshot["case_id"], "event_id": "live_proof_message",
            "expected_case_version": snapshot["case_version"], "occurred_at": now, "channel": "chat",
            "type": "conversation.message", "payload": {"message_id": "live_proof_user",
                "text": text},
        }
        runtime = AgentRuntime(service, config, diagnostics=diagnostics)
        if args.rules or args.knowledge or args.fetch or args.planner or args.plan:
            runtime.registry = RuleProofRegistry(runtime.registry.definitions)
        result = runtime.handle(token, command)
        case = result["case_snapshot"]
        turn = case["conversation"]["turns"][-1]
        if turn["state"] != "complete":
            code = turn.get("issue", {}).get("code", turn["state"])
            record(diagnostics, "smoke_failed", code=code)
            print("Live proof incomplete:", code)
            provider_failure = diagnostics.provider_failure or {}
            if provider_failure.get("code"):
                print("Provider error:", provider_failure["code"])
            if provider_failure.get("reason"):
                print("Provider reason:", provider_failure["reason"])
            return 1
        if args.incidents:
            incident = case.get("incident_context", {}).get("current")
            if incident is None:
                record(diagnostics, "smoke_failed", code="incident_context_missing")
                print("Live proof incomplete: incident context was not saved.")
                return 1
            if not any(provider["state"] in ("available", "no_match") for provider in incident["providers"].values()):
                record(diagnostics, "smoke_failed", code="incident_sources_unavailable")
                print("Live proof incomplete: no official incident source returned validated data.")
                return 1
        elif args.resources:
            resources = case["resources"]
            if resources.get("search") is None or resources["state"] != "available" or not resources["items"]:
                record(diagnostics, "smoke_failed", code="resource_search_missing")
                print("Live proof incomplete: resource referrals were not saved.")
                return 1
            ids = {source["id"] for source in case["sources"]}
            if any(item["availability"]["state"] != "unknown" or item["data_mode"] != "seeded"
                   or not set(item["source_ids"]) <= ids for item in resources["items"]):
                record(diagnostics, "smoke_failed", code="resource_attribution_invalid")
                print("Live proof incomplete: resource labels or attribution are invalid.")
                return 1
        elif args.rules:
            rules = runtime.registry.rule_result
            if rules is None or rules["state"] != "available" or not rules["rules"]:
                record(diagnostics, "smoke_failed", code="rule_lookup_missing")
                print("Live proof incomplete: the current reviewed rule tool did not return available requirements.")
                return 1
            ids = {source["id"] for source in rules["sources"]}
            if (rules["household_eligibility"] != "unknown" or rules["query"]["issuing_state"] != "CO"
                    or any(rule["data_mode"] != "seeded" or not set(rule["source_ids"]) <= ids for rule in rules["rules"])
                    or not {"online", "in_person"} <= {path["execution_mode"] for rule in rules["rules"] for path in rule["paths"]}):
                record(diagnostics, "smoke_failed", code="rule_attribution_invalid")
                print("Live proof incomplete: rule alternatives, scope or source attribution are invalid.")
                return 1
            if any(case[key] != snapshot[key] for key in ("facts", "needs", "evidence", "resources", "plan", "applications",
                                                         "check_in", "shared_location", "follow_ups", "components", "sources")) or case["finance"]["ledger"] != snapshot["finance"]["ledger"]:
                record(diagnostics, "smoke_failed", code="rule_side_effect_unexpected")
                print("Live proof incomplete: a read-only rule test unexpectedly changed domain state.")
                return 1
        elif args.plan:
            registry = runtime.registry
            if len(registry.plan_results) < 2 or not registry.task_results:
                record(diagnostics, "smoke_failed", code="plan_workflow_missing")
                print("Live plan proof incomplete: save, task report and preserving revision were not all performed.")
                return 1
            paths = {action["path_id"]: action for action in case["plan"]["actions"]}
            online, office = paths.get("co_id_online_renewal"), paths.get("co_id_office_renewal")
            if (any(result["status"] not in ("applied", "already_applied") for result in registry.plan_results + registry.task_results)
                    or not online or not office or online["status"] != "completed" or office["status"] != "blocked"
                    or len(case["plan"]["revisions"]) != 2 or len(online["history"]) != 1
                    or online["history"][0]["provenance"] != "user_reported" or case["plan"]["household_eligibility"] != "unknown"
                    or not online["source_records"]
                    or online["costs"]["fee_cents"] is not None or office["costs"]["transport_cents"] is not None):
                record(diagnostics, "smoke_failed", code="plan_workflow_invalid")
                print("Live plan proof incomplete: completion, retained work, sources or unknowns were invalid.")
                return 1
            if not all(word in turn["text"].lower() for word in ("saved", "completed", "unknown")) or online["official_url"] not in turn["text"]:
                record(diagnostics, "smoke_failed", code="plan_workflow_reply_missing")
                print("Live plan proof incomplete: saved reply omitted the report, uncertainty or official link.")
                return 1
            if (service.read_program_catalog() != catalog_before or any(case[key] != snapshot[key] for key in
                    ("facts", "needs", "evidence", "resources", "applications", "check_in", "shared_location", "follow_ups", "components"))
                    or case["finance"]["ledger"] != snapshot["finance"]["ledger"]):
                record(diagnostics, "smoke_failed", code="plan_workflow_side_effect")
                print("Live plan proof incomplete: facts, money, consent or policy were unexpectedly changed.")
                return 1
            if case["plan"]["state"] != "provisional":
                record(diagnostics, "smoke_failed", code="plan_workflow_invalid")
                print("Live plan proof incomplete: the preserving revision was not current.")
                return 1
            plan_calls = len(registry.plan_results) + len(registry.task_results)
        elif args.planner:
            from ..contracts import validate
            planned = runtime.registry.planner_result
            if planned is None:
                record(diagnostics, "smoke_failed", code="planner_result_missing")
                print("Live planner proof incomplete: no recovery evaluation was returned.")
                return 1
            validate("RecoveryOptionResult", planned)
            paths = {option["path_id"]: option for option in planned["options"]}
            online, office = paths.get("co_id_online_renewal"), paths.get("co_id_office_renewal")
            ids = {source["id"] for source in planned["sources"]}
            if (planned["state"] != "available" or planned["query"]["issuing_state"] != "CO"
                    or planned["household_eligibility"] != "unknown" or len(paths) != 2 or not online or not office
                    or online["status"] != "provisional" or office["status"] != "blocked"
                    or online["blockers"] or not online["questions"]
                    or not any(item["fact_key"] == "office_transport_available" for item in office["blockers"])
                    or office["id"] not in online["alternative_option_ids"]
                    or any(option["costs"][key] is not None for option in paths.values() for key in ("fee_cents", "transport_cents", "cost_date"))
                    or not ids or any(not set(option["source_ids"]) <= ids for option in paths.values())):
                record(diagnostics, "smoke_failed", code="planner_result_invalid")
                print("Live planner proof incomplete: options, no-car constraints, costs or provenance were invalid.")
                return 1
            reply = turn["text"].lower()
            if not all(word in reply for word in ("online", "office", "unknown")) or not any(
                    option["official_url"].lower() in reply for option in paths.values()):
                record(diagnostics, "smoke_failed", code="planner_reply_missing")
                print("Live planner proof incomplete: saved reply omitted the alternatives, unknowns or official link.")
                return 1
            if (service.read_program_catalog() != catalog_before or any(case[key] != snapshot[key] for key in
                    ("facts", "needs", "evidence", "resources", "plan", "applications", "check_in", "shared_location", "follow_ups", "components", "sources"))
                    or case["finance"]["ledger"] != snapshot["finance"]["ledger"]):
                record(diagnostics, "smoke_failed", code="planner_side_effect_unexpected")
                print("Live planner proof incomplete: evaluation unexpectedly changed household domains or policy.")
                return 1
            planner_calls = runtime.registry.planner_calls
        elif args.fetch:
            from ..contracts import InvalidInput
            from ..knowledge.fetch_smoke import EVIDENCE_PHRASE, SOURCE_ID, live_guidance
            fetched = runtime.registry.public_results.get("fetch_official_source")
            if fetched is None or fetched["source_id"] != SOURCE_ID:
                record(diagnostics, "smoke_failed", code="official_fetch_missing")
                print("Live fetch proof incomplete: no result from the requested public source.")
                return 1
            if fetched["state"] != "available":
                record(diagnostics, "smoke_failed", code="official_live_fetch_unavailable", mode=mode, retrieval_state=fetched["state"])
                print("Live fetch proof incomplete: the public page was unavailable; fallback handling is not a successful live fetch.")
                return 1
            try:
                excerpt = live_guidance(fetched)
            except InvalidInput:
                record(diagnostics, "smoke_failed", code="official_example_content_missing")
                print("Live fetch proof incomplete: useful lost-ID guidance was absent from the fetched page.")
                return 1
            receipt = fetched["receipt"]
            reply = turn["text"]
            if receipt["url"] not in reply or EVIDENCE_PHRASE not in reply.lower() or excerpt.lower() not in reply.lower():
                record(diagnostics, "smoke_failed", code="official_example_reply_missing")
                print("Live fetch proof incomplete: the saved reply omitted the fetched guidance or its official link.")
                return 1
            if service.read_program_catalog() != catalog_before or any(case[key] != snapshot[key] for key in
                    ("facts", "needs", "evidence", "resources", "plan", "applications", "check_in", "shared_location",
                     "follow_ups", "components", "sources")) or case["finance"]["ledger"] != snapshot["finance"]["ledger"]:
                record(diagnostics, "smoke_failed", code="knowledge_domain_changed")
                print("Live fetch proof incomplete: a read-only fetch unexpectedly changed household domains or policy.")
                return 1
        elif args.knowledge:
            from ..knowledge.review import ManualReviewAuthority
            proofs = runtime.registry.public_results
            fetched = proofs.get("fetch_official_source")
            if fetched is None or fetched["state"] not in ("available", "unavailable") or fetched["source_id"] != "source_rule_co_renewal":
                record(diagnostics, "smoke_failed", code="official_fetch_missing")
                print("Live proof incomplete: no validated official-fetch result.")
                return 1
            required = ("propose_rule_candidate", "report_rule_discrepancy") if fetched["state"] == "available" else ("report_rule_discrepancy",)
            if any(proofs.get(name, {}).get("state") not in ("submitted", "already_submitted") for name in required):
                record(diagnostics, "smoke_failed", code="knowledge_submission_missing")
                print("Live proof incomplete: the required public review submissions were not saved.")
                return 1
            queue = service.read_review_queue(ManualReviewAuthority("synthetic_smoke"))
            if (not queue or any(item["review_state"] != "pending" or item["program_id"] != "co_state_id_replacement"
                                 or item["arguments"]["source_id"] != "source_rule_co_renewal" for item in queue)
                    or service.read_program_catalog() != catalog_before):
                record(diagnostics, "smoke_failed", code="knowledge_publication_unexpected")
                print("Live proof incomplete: review evidence unexpectedly altered published rules.")
                return 1
            if any(case[key] != snapshot[key] for key in ("facts", "needs", "evidence", "resources", "plan", "applications", "check_in", "shared_location", "follow_ups", "components", "sources")) or case["finance"]["ledger"] != snapshot["finance"]["ledger"]:
                record(diagnostics, "smoke_failed", code="knowledge_domain_changed")
                print("Live proof incomplete: public review unexpectedly altered household domains.")
                return 1
        elif case["facts"].get("mobility", {}).get("value") != "no_car":
            record(diagnostics, "smoke_failed", code="required_fact_missing")
            print("Live proof incomplete: required fact tool did not save the reported value.")
            return 1
        replay = runtime.handle(token, command)
        if (replay["status"] != "already_applied" or replay["case_snapshot"]["case_version"] != case["case_version"]
                or args.planner and (runtime.registry.planner_calls != planner_calls
                                     or replay["case_snapshot"]["conversation"]["turns"][-1] != turn)
                or args.plan and (len(runtime.registry.plan_results) + len(runtime.registry.task_results) != plan_calls
                                  or replay["case_snapshot"] != case)):
            record(diagnostics, "smoke_failed", code="replay_failed")
            print("Live proof incomplete: replay verification failed.")
            return 1
        record(diagnostics, "smoke_passed", mode=mode, retrieval_state=fetched["state"] if args.knowledge or args.fetch else None)
        if args.plan:
            print("Live Bedrock saved plan, user-reported task completion, preserving revision, sourced reply and replay passed on a disposable synthetic case. Eligibility, costs and agency outcomes remain unknown.")
        elif args.planner:
            print("Live Bedrock read-only planner, provisional online/blocked office alternatives, unknown costs/eligibility, sourced saved reply, unchanged domains/policy and replay passed on a disposable synthetic case.")
        elif args.fetch:
            print("Live Bedrock fresh official fetch, source-backed saved reply, unchanged domains/policy and replay passed.")
            print("Fetched at:", receipt["retrieved_at"])
            print("Official source:", receipt["url"])
            print("Fetched guidance:", excerpt)
        elif args.incidents:
            print("Live Bedrock incident tool, durable context/attribution/reply, and event replay passed on a disposable synthetic case.")
        elif args.resources:
            print("Live Bedrock resource tool, durable seeded referrals/attribution/reply, and event replay passed on a disposable synthetic case. Live service capacity remains unknown.")
        elif args.rules:
            print("Live Bedrock read-only rule tool, scoped reviewed alternatives/source attribution, durable reply, unchanged domain state, and event replay passed on a disposable synthetic case. Household eligibility remains unknown.")
        elif args.knowledge:
            if fetched["state"] == "available":
                print("Live Bedrock official fetch, unpublished candidate/discrepancy submission, durable reply and replay passed on a disposable synthetic case. Manual publication remains separate.")
            else:
                print("Live Bedrock official-source failure/fallback, unpublished discrepancy submission, durable reply and replay passed on a disposable synthetic case. Successful live extraction remains unverified.")
        else:
            print("Live Bedrock tool call, durable fact/reply, and event replay passed on a disposable synthetic case.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
