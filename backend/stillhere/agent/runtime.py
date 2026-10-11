"""Durable turns with bounded provider work and no automatic replay of failed effects."""

import queue
import threading
import time

from ..contracts import validate
from ..service import ServiceError
from .config import AgentConfig
from .diagnostics import failure, record
from .provider import StrandsBedrockProvider
from .registry import (CASE_TOOLS, CANDIDATE_TOOL, DISCREPANCY_TOOL, INCIDENT_TOOL, INTAKE_TOOL,
                       OFFICIAL_TOOL, RESOURCE_TOOL, RULE_TOOL, ToolRegistry)
from .tools import AgentContext, AgentFailure


class AgentRuntime:
    def __init__(self, service, config=None, provider=None, registry=None, diagnostics=None, incident_facade=None, resource_catalog=None, rule_store=None, official_fetcher=None):
        self.service = service
        self.config = config or AgentConfig()
        self.diagnostics = diagnostics
        self.provider = provider or StrandsBedrockProvider(self.config, diagnostics=diagnostics)
        self.registry = registry or ToolRegistry(CASE_TOOLS + ((INTAKE_TOOL,) if self.config.enable_intake else ())
                                               + ((INCIDENT_TOOL,) if self.config.enable_incidents else ())
                                               + ((RESOURCE_TOOL,) if self.config.enable_resources else ())
                                               + ((RULE_TOOL,) if self.config.enable_rules else ())
                                               + ((OFFICIAL_TOOL,) if self.config.enable_official_sources or self.config.enable_rule_review else ())
                                               + ((CANDIDATE_TOOL, DISCREPANCY_TOOL) if self.config.enable_rule_review else ()))
        if self.config.enable_incidents and incident_facade is None:
            from ..incidents import IncidentFacade
            incident_facade = IncidentFacade()
        self.incident_facade = incident_facade
        if self.config.enable_resources and resource_catalog is None:
            from ..resources import ResourceCatalog
            resource_catalog = ResourceCatalog(clock=service.clock)
        self.resource_catalog = resource_catalog
        if self.config.enable_rules and rule_store is None:
            from ..knowledge import ProgramRuleStore
            rule_store = ProgramRuleStore(loader=service.read_program_catalog, version_loader=service.read_program_version)
        self.rule_store = rule_store
        if (self.config.enable_official_sources or self.config.enable_rule_review) and official_fetcher is None:
            from ..knowledge.official import OfficialSourceFetcher
            official_fetcher = OfficialSourceFetcher()
        self.official_fetcher = official_fetcher

    def handle(self, token, command):
        result = self.service.execute(token, command)
        if command.get("type") != "conversation.message" or result["status"] not in ("applied", "already_applied"):
            return result
        try:
            queued = next((t for t in result["case_snapshot"]["conversation"]["turns"]
                           if t["role"] == "assistant" and t["state"] == "queued"), None)
            self.process(token, command["case_id"], queued["event_id"] if queued else command["event_id"])
            result["case_snapshot"] = self.service.read_case(token, command["case_id"])
        except ServiceError as error:
            result["issues"].append(error.issue)
        validate("CommandResult", result)
        return result

    def process(self, token, case_id, event_id):
        claim = self.service.claim_agent_turn(token, case_id, event_id, self.config.timeout_seconds)
        if claim is None:
            return
        record(self.diagnostics, "run_started")
        snapshot, command = claim["snapshot"], claim["command"]
        context = AgentContext(self.service, token, case_id, event_id, claim["run_id"],
                               snapshot["case_version"], time.monotonic() + self.config.timeout_seconds,
                               self.config.max_tool_calls, self.config.max_context_chars,
                               incident_facade=self.incident_facade, resource_catalog=self.resource_catalog, rule_store=self.rule_store,
                               official_fetcher=self.official_fetcher)
        # Stop at this message; never present a subsequently queued message as part of this turn.
        turns = snapshot["conversation"]["turns"]
        end = next(i for i, t in enumerate(turns) if t.get("event_id") == event_id and t["role"] == "assistant")
        history = [t for t in turns[:end - 1] if t["state"] == "complete"][-self.config.history_turns:]
        scoped = dict(snapshot, conversation={"turns": []})
        outcome = queue.Queue(maxsize=1)

        def work():
            try:
                record(self.diagnostics, "provider_started")
                text = self.provider.reply(scoped, history, command["payload"]["text"], context, self.registry)
                if context.terminal_issue:
                    raise AgentFailure(context.terminal_issue["code"], context.terminal_issue["message"])
                if not isinstance(text, str) or not text.strip() or len(text) > 8000:
                    raise AgentFailure("invalid_agent_reply", "The agent did not return a valid bounded reply.")
                outcome.put((text, None))
            except AgentFailure as error:
                record(self.diagnostics, "provider_failed", code=error.issue["code"])
                outcome.put(("", error.issue))
            except Exception as error:
                failure(self.diagnostics, error)
                # Exception strings can include provider credentials, prompt text or case details.
                outcome.put(("", {"code": "agent_provider_unavailable", "message": "The model provider could not complete this turn. Accepted changes remain saved; send a new message to continue.", "retryable": False}))

        worker = threading.Thread(target=work, daemon=True)
        worker.start()
        try:
            text, issue = outcome.get(timeout=self.config.timeout_seconds)
        except queue.Empty:
            record(self.diagnostics, "run_timeout", code="agent_timeout")
            text, issue = "", {"code": "agent_timeout", "message": "The agent time limit was reached. Accepted changes remain saved; send a new message to continue.", "retryable": False}
        # Revokes all later registry calls even when the provider remains blocked in a socket.
        with context.lock:
            context.deadline = 0
        snapshot = self.service.finish_agent_turn(token, case_id, event_id, claim["run_id"], text, issue)
        turn = next(t for t in snapshot["conversation"]["turns"] if t["role"] == "assistant" and t.get("event_id") == event_id)
        record(self.diagnostics, "run_complete" if turn["state"] == "complete" else "run_failed",
               code=turn.get("issue", {}).get("code"))
        queued = next((t for t in snapshot["conversation"]["turns"]
                       if t["role"] == "assistant" and t["state"] == "queued"), None)
        if queued:
            # A request received during this run is already durable and authorized.
            # Continue it after releasing the case claim, without extending this HTTP wait.
            threading.Thread(target=self._continue, args=(token, case_id, queued["event_id"]), daemon=True).start()

    def _continue(self, token, case_id, event_id):
        try:
            self.process(token, case_id, event_id)
        except ServiceError:
            # Queued turns survive storage failure and can be dispatched on a later retry.
            pass
