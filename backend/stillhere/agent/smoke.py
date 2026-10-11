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


def main():
    parser = argparse.ArgumentParser(description="Live Strands/Bedrock synthetic tool proof")
    parser.add_argument("--env-file", help="Explicit optional local configuration file")
    parser.add_argument("--log-file", default="var/agent-smoke.jsonl", help="Safe phase/error-code log (default: var/agent-smoke.jsonl)")
    parser.add_argument("--check-access", action="store_true", help="Read-only account/model activation checks; no inference or case writes")
    parser.add_argument("--incidents", action="store_true", help="Live model/C03 proof using a disposable case and synthetic Denver geography")
    parser.add_argument("--expected-account-id", help="With --check-access, privately compare the 12-digit console account ID; never prints or logs it")
    args = parser.parse_args()
    if args.incidents and args.check_access:
        parser.error("Choose either --incidents or --check-access.")
    if args.expected_account_id is not None and (not args.check_access or not re.fullmatch(r"[0-9]{12}", args.expected_account_id)):
        parser.error("--expected-account-id requires --check-access and a 12-digit account ID.")
    diagnostics = SafeDiagnostics(args.log_file)
    diagnostics.record("smoke_started")
    print("Safe diagnostic log:", diagnostics.path)
    if args.env_file:
        load_local_environment(args.env_file)
    config = AgentConfig.from_environment()
    if args.incidents:
        config = replace(config, enable_incidents=True)
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
        if args.incidents:
            request["intake"] = {"current_location": {"place": "Synthetic Denver", "latitude": 39.7392,
                "longitude": -104.9903, "state": "CO", "county_fips": "08031"}}
        snapshot = service.create_case(token, request)["case_snapshot"]
        now = utc_now()
        text = ("This is a synthetic test. Call get_incident_context for location_scope current with lookback_days 30, "
                "using the reported case geography. Reply after checking each provider state. Distinguish no matching records "
                "from missing geography or failed sources; do not claim household eligibility or absence of a disaster."
                if args.incidents else f"This is a synthetic test. I have no car as of {now}. Call read_case, then correct_fact to save mobility as no_car with that observation time. Reply after the tool succeeds.")
        command = {
            "contract_version": "0.1", "case_id": snapshot["case_id"], "event_id": "live_proof_message",
            "expected_case_version": snapshot["case_version"], "occurred_at": now, "channel": "chat",
            "type": "conversation.message", "payload": {"message_id": "live_proof_user",
                "text": text},
        }
        runtime = AgentRuntime(service, config, diagnostics=diagnostics)
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
        elif case["facts"].get("mobility", {}).get("value") != "no_car":
            record(diagnostics, "smoke_failed", code="required_fact_missing")
            print("Live proof incomplete: required fact tool did not save the reported value.")
            return 1
        replay = runtime.handle(token, command)
        if replay["status"] != "already_applied" or replay["case_snapshot"]["case_version"] != case["case_version"]:
            record(diagnostics, "smoke_failed", code="replay_failed")
            print("Live proof incomplete: replay verification failed.")
            return 1
        record(diagnostics, "smoke_passed")
        if args.incidents:
            print("Live Bedrock incident tool, durable context/attribution/reply, and event replay passed on a disposable synthetic case.")
        else:
            print("Live Bedrock tool call, durable fact/reply, and event replay passed on a disposable synthetic case.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
