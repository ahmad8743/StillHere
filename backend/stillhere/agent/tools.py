"""C01 adapters. Backend-only context fixes session, case, turn and write version."""

import threading
import time
from dataclasses import dataclass, field

from ..contracts import VERSION


class AgentFailure(Exception):
    def __init__(self, code, message):
        self.issue = {"code": code, "message": message, "retryable": False}
        super().__init__(message)


@dataclass
class AgentContext:
    service: object = field(repr=False)
    token: str = field(repr=False)
    case_id: str
    event_id: str
    run_id: str = field(repr=False)
    expected_version: int
    deadline: float
    max_tool_calls: int
    max_result_chars: int
    calls: int = 0
    completed_tool_calls: int = 0
    tool_seconds: float = 0
    writes_conflicted: bool = False
    terminal_issue: object = None
    lock: object = field(default_factory=threading.RLock, repr=False)
    incident_facade: object = field(default=None, repr=False)
    incident_results: dict = field(default_factory=dict, repr=False)
    resource_catalog: object = field(default=None, repr=False)
    resource_results: dict = field(default_factory=dict, repr=False)
    rule_store: object = field(default=None, repr=False)
    official_fetcher: object = field(default=None, repr=False)
    official_results: dict = field(default_factory=dict, repr=False)

    def check_budget(self):
        if time.monotonic() >= self.deadline:
            error = AgentFailure("agent_timeout", "The agent time limit was reached. Accepted changes remain saved.")
            self.terminal_issue = error.issue
            raise error
        if self.calls >= self.max_tool_calls:
            error = AgentFailure("agent_tool_limit", "The agent tool limit was reached. Accepted changes remain saved.")
            self.terminal_issue = error.issue
            raise error
        self.calls += 1


def read_case(context, arguments):
    snapshot = context.service.read_case(context.token, context.case_id)
    # A read cannot silently reconcile a write that has already conflicted.
    if not context.writes_conflicted:
        context.expected_version = snapshot["case_version"]
    return snapshot


def _write(context, command_type, payload):
    if context.writes_conflicted:
        raise AgentFailure("version_conflict", "A concurrent change needs user reconciliation before another write.")
    result = context.service.execute_agent_command(
        context.token, context.case_id, context.event_id, context.run_id,
        command_type, payload, context.expected_version,
    )
    if result["status"] == "conflict":
        context.writes_conflicted = True
    elif result["status"] in ("applied", "already_applied"):
        context.expected_version = result["applied_case_version"]
    return result


def correct_fact(context, arguments):
    return _write(context, "fact.correct", arguments)


def submit_intake(context, arguments):
    return _write(context, "intake.submit", arguments["selections"])


def get_incident_context(context, arguments):
    from ..contracts import canonical_json
    from ..incidents import build_query, query_identity
    if context.writes_conflicted:
        raise AgentFailure("version_conflict", "A concurrent change needs user reconciliation before another write.")
    if context.incident_facade is None:
        raise AgentFailure("tool_forbidden", "Incident retrieval is not enabled.")
    snapshot = read_case(context, {})
    query = build_query(snapshot, arguments, context.service.clock())
    key = canonical_json(query_identity(query))
    result = context.incident_results.get(key)
    if result is None:
        result = context.incident_facade.collect(query, snapshot["case_version"], context.deadline)
        context.incident_results[key] = result
    if time.monotonic() >= context.deadline:
        error = AgentFailure("agent_timeout", "Incident retrieval reached the agent time limit; no late source result was committed.")
        context.terminal_issue = error.issue
        raise error
    committed = context.service.commit_agent_incident_context(
        context.token, context.case_id, context.event_id, context.run_id, result, context.expected_version)
    if committed["status"] == "conflict":
        context.writes_conflicted = True
    elif committed["status"] in ("applied", "already_applied"):
        context.expected_version = committed["case_snapshot"]["case_version"]
    return committed


def find_resources(context, arguments):
    from ..contracts import canonical_json
    from ..resources import build_query, query_identity
    if context.writes_conflicted:
        raise AgentFailure("version_conflict", "A concurrent change needs user reconciliation before another write.")
    if context.resource_catalog is None:
        raise AgentFailure("tool_forbidden", "Resource retrieval is not enabled.")
    snapshot = read_case(context, {})
    query = build_query(snapshot, arguments)
    key = canonical_json(query_identity(query))
    result = context.resource_results.get(key)
    if result is None:
        try:
            result = context.resource_catalog.collect(query, snapshot["case_version"], context.deadline)
        except TimeoutError:
            error = AgentFailure("agent_timeout", "Resource lookup reached the agent time limit; no late result was committed.")
            context.terminal_issue = error.issue
            raise error from None
        context.resource_results[key] = result
    if time.monotonic() >= context.deadline:
        error = AgentFailure("agent_timeout", "Resource lookup reached the agent time limit; no late result was committed.")
        context.terminal_issue = error.issue
        raise error
    committed = context.service.commit_agent_resources(
        context.token, context.case_id, context.event_id, context.run_id, result, context.expected_version)
    if committed["status"] == "conflict":
        context.writes_conflicted = True
    elif committed["status"] in ("applied", "already_applied"):
        context.expected_version = committed["case_snapshot"]["case_version"]
    return committed


def retrieve_program_rules(context, arguments):
    from ..contracts import InvalidInput
    from ..knowledge import build_query, validate_result
    from ..knowledge.rules import notice
    if context.writes_conflicted:
        raise AgentFailure("version_conflict", "A concurrent change needs user reconciliation before another scoped lookup.")
    if context.rule_store is None:
        raise AgentFailure("tool_forbidden", "Program-rule retrieval is not enabled.")
    snapshot = read_case(context, {})
    query = build_query(snapshot, arguments, context.service.clock())
    try:
        result = context.rule_store.lookup(query, context.deadline)
    except TimeoutError:
        error = AgentFailure("agent_timeout", "Rule lookup reached the agent time limit.")
        context.terminal_issue = error.issue
        raise error from None
    if time.monotonic() >= context.deadline:
        error = AgentFailure("agent_timeout", "Rule lookup reached the agent time limit; late requirements were discarded.")
        context.terminal_issue = error.issue
        raise error
    validate_result(result)
    if result["query"] != query:
        raise InvalidInput("$.query", "Rule results must match the backend's exact scoped lookup.")
    latest = context.service.read_case(context.token, context.case_id)
    if time.monotonic() >= context.deadline:
        error = AgentFailure("agent_timeout", "Rule lookup reached the agent time limit during input revalidation.")
        context.terminal_issue = error.issue
        raise error
    if latest["case_version"] != snapshot["case_version"]:
        context.writes_conflicted = True
        result.update(state="conflict", rules=[], sources=[], notices=[notice("version_conflict", "Case inputs changed during rule lookup. Reconcile before using requirements or making another change.")])
    validate_result(result)
    return result


def failure(issue):
    return {"contract_version": VERSION, "error": issue}


def fetch_official_source(context, arguments):
    from ..contracts import InvalidInput
    from ..knowledge.official import validate_fetch
    if context.official_fetcher is None:
        raise AgentFailure("tool_forbidden", "Official-source retrieval is not enabled.")
    snapshot = read_case(context, {})
    source_id = arguments["source_id"]
    result = context.official_results.get(source_id)
    if result is None:
        now = context.service.clock()
        try:
            result = context.official_fetcher.fetch(source_id, now, context.deadline)
        except TimeoutError:
            error = AgentFailure("agent_timeout", "Official-source retrieval reached the agent time limit.")
            context.terminal_issue = error.issue
            raise error from None
        validate_fetch(result)
        if result["source_id"] != source_id or result["requested_at"] != now:
            raise InvalidInput("$.source_id", "Official results must match the exact backend request.")
        latest = context.service.read_case(context.token, context.case_id)
        if time.monotonic() >= context.deadline:
            error = AgentFailure("agent_timeout", "Late official-source results were discarded.")
            context.terminal_issue = error.issue
            raise error
        if latest["case_version"] != snapshot["case_version"]:
            context.writes_conflicted = True
        context.official_results[source_id] = result
    return result


def _submit_knowledge(context, arguments, kind):
    from ..contracts import InvalidInput
    if context.writes_conflicted:
        raise AgentFailure("version_conflict", "Reconcile the concurrent case change before submitting public review evidence.")
    fetched = context.official_results.get(arguments["source_id"])
    if fetched is None:
        raise InvalidInput("$.source_id", "Call fetch_official_source for this public source before submitting review evidence.")
    result = context.service.submit_agent_knowledge(context.token, context.case_id, context.event_id, context.run_id,
                                                  kind, arguments, fetched, context.expected_version, context.deadline)
    if result["state"] == "conflict":
        context.writes_conflicted = True
    return result


def propose_rule_candidate(context, arguments):
    return _submit_knowledge(context, arguments, "candidate")


def report_rule_discrepancy(context, arguments):
    return _submit_knowledge(context, arguments, "discrepancy")
