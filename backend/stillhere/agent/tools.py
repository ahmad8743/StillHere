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


def failure(issue):
    return {"contract_version": VERSION, "error": issue}
