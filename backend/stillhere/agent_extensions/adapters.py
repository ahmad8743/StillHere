"""No persistence, operator APIs, provider calls or model-selected case context."""

import copy
import hashlib

from ..agent.tools import AgentFailure
from ..contracts import canonical_json, validate as authoritative_validate, InvalidInput

COMMANDS = frozenset({"finance.update", "scenario.set", "application.update", "check_in.reply",
                      "check_in.pause", "location.clear", "help.request"})


def child_event_id(case_id, parent_event_id, operation, arguments):
    return "agent_tool_" + hashlib.sha256(canonical_json([case_id, parent_event_id, operation, arguments]).encode()).hexdigest()[:48]


def _read(context):
    snapshot = context.service.read_case(context.token, context.case_id)
    if snapshot["case_version"] != context.expected_version:
        context.writes_conflicted = True
        raise AgentFailure("version_conflict", "Reconcile the concurrent case change before using new domain outputs.")
    return snapshot


def _accept(context, result):
    try:
        authoritative_validate("CommandResult", result)
    except InvalidInput:
        raise AgentFailure("invalid_extension_result", "CaseService returned an invalid result. Any accepted effects remain saved.") from None
    snapshot = result["case_snapshot"]
    if snapshot is not None and snapshot["case_id"] != context.case_id:
        raise AgentFailure("invalid_extension_result", "CaseService returned an incorrectly scoped result.")
    if result["status"] == "conflict":
        context.writes_conflicted = True
    elif result["status"] == "applied":
        context.expected_version = snapshot["case_version"]
    elif result["status"] == "already_applied" and snapshot["case_version"] != context.expected_version:
        context.writes_conflicted = True
        raise AgentFailure("version_conflict", "The original effect is saved; reconcile the newer case before continuing.")
    if any(item["code"] in ("agent_timeout", "agent_run_inactive") for item in result["issues"]):
        context.terminal_issue = next(item for item in result["issues"] if item["code"] in ("agent_timeout", "agent_run_inactive"))
    return result


def mutate(context, operation, arguments):
    if context.writes_conflicted:
        raise AgentFailure("version_conflict", "Reconcile the concurrent change before another domain write.")
    if operation in COMMANDS:
        execute = getattr(context.service, "execute_agent_extension_command", None)
        if execute is None:
            raise AgentFailure("extension_integration_required", "The reviewed CaseService extension command API is required.")
    else:
        execute = getattr(context.service, "execute_agent_derivation", None)
        if execute is None:
            raise AgentFailure("extension_integration_required", "The reviewed CaseService derivation API is required.")
    result = execute(context.token, context.case_id, context.event_id, context.run_id,
                     operation, arguments, context.expected_version, context.deadline, context.max_result_chars)
    result = _accept(context, result)
    return context.service.domain_summary(result, operation)


def read_financial_summary(context, arguments):
    snapshot = _read(context)
    finance = snapshot["finance"]
    # Actual balances are separate from projected positions; preserve restrictions.
    return {"contract_version": "0.1", "input_case_version": snapshot["case_version"],
            "money_sources": copy.deepcopy(finance["ledger"]["money_sources"]),
            "aid": copy.deepcopy(finance["ledger"]["aid"]),
            "finance": context.service.domain_summary(context.service._result(
                "extension_read", "applied", context.service.clock(), snapshot, snapshot["case_version"]),
                "finance.calculate")["summary"]["finance"]}


def read_check_in_status(context, arguments):
    snapshot = _read(context)
    return {"contract_version": "0.1", "input_case_version": snapshot["case_version"],
            "check_in": copy.deepcopy(snapshot["check_in"]), "follow_ups": copy.deepcopy(snapshot["follow_ups"]),
            "simulation": True}


def stage_structured_reply(context, arguments):
    from ..outputs import prepare_structured_reply
    prepared = prepare_structured_reply(_read(context), arguments, now=context.service.clock())
    context.extension_reply = prepared
    return copy.deepcopy(prepared)
