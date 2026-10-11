"""Explicit factories with provider schemas distinct from authoritative unions."""

import inspect
from dataclasses import dataclass
from typing import Any

from ..agent.registry import ToolRegistry
from ..agent.tools import AgentFailure, failure
from ..contracts import InvalidInput, canonical_json, validate as shared_validate
from ..outputs.validation import OutputValidationError
from ..service import ServiceError
from . import adapters
from .config import ExtensionConfig
from .schema import bounded, inline_schema, validate
from .validation import validate_household_financial_input


@dataclass(frozen=True)
class ExtensionTool:
    name: str
    description: str
    arguments_schema: str
    result_schema: str
    family: str
    operation: str = ""
    access: str = "read"
    role: str = "household"


TOOLS = (
    ExtensionTool("read_financial_summary", "Read actual entered balances, restrictions and unreceived aid separately from projected and hypothetical outcomes. No authoritative arithmetic by the model.", "EmptyArguments", "FinancialSummary", "finance_calculation"),
    ExtensionTool("update_financial_state", "Record only explicit household financial reports using the exact update union. Ambiguity requires clarification. CaseService reconciles and calculates; never infer receipt, approval, provenance, ownership or amounts.", "FinancialUpdateArguments", "DomainMutationResult", "finance_updates", "finance.update", "write"),
    ExtensionTool("calculate_cash_flow", "Save the deterministic fixed 14-day baseline using current case inputs. Inspect incomplete inputs, gap dates and assumptions; current accessible money differs from projections.", "ForecastArguments", "DomainMutationResult", "finance_calculation", "finance.calculate", "read_and_commit"),
    ExtensionTool("set_financial_scenario", "Save one explicitly requested hypothetical scenario, at most three in the ledger. No actual receipt, balance or approval changes. Action IDs require the reviewed backend cost boundary.", "ScenarioArguments", "DomainMutationResult", "finance_scenarios", "scenario.set", "write"),
    ExtensionTool("compare_financial_scenarios", "Recalculate saved hypothetical scenarios and baseline through the same deterministic engine. Scenarios are conditional and do not change actual money. Preserve unknown inputs.", "ForecastArguments", "DomainMutationResult", "finance_scenarios", "finance.calculate", "read_and_commit"),
    ExtensionTool("prepare_application", "Prepare a provisional Boolean-availability draft and source-attributed call script for an existing current saved action and exact published path. Never submit externally, infer eligibility or request identity numbers.", "PrepareApplicationArguments", "DomainMutationResult", "applications", "application.prepare", "read_and_commit"),
    ExtensionTool("update_application", "Record only explicit user-reported stages, corrections, metadata correspondence and existing evidence changes. Agency outcomes remain separate; reported approval creates no money. Rules unavailable may require the reviewed report-only boundary.", "UpdateApplicationArguments", "DomainMutationResult", "applications", "application.update", "write"),
    ExtensionTool("publish_dashboard_components", "Publish bounded allowlisted descriptors referencing only current saved case records. CaseService revalidates references and freshness; no generated code, authority or new facts.", "PublishDashboardArguments", "DomainMutationResult", "dashboard", "dashboard.publish", "read_and_commit"),
    ExtensionTool("read_check_in_status", "Read scoped schedules and timestamped reports. All follow-up attempts are simulated; overdue means condition unknown, not confirmed distress or active human response.", "EmptyArguments", "CheckInSummary", "check_ins"),
    ExtensionTool("record_check_in_reply", "Record an explicit household report for a saved occurrence. check_later requires an explicitly selected next time. Never enroll, grant consent or silently close a review.", "CheckInReplyArguments", "DomainMutationResult", "check_ins", "check_in.reply", "write"),
    ExtensionTool("pause_check_ins", "Pause or stop future scheduled simulated attempts at the user's explicit request; retain existing reviews and separate location consent.", "CheckInPauseArguments", "DomainMutationResult", "check_ins", "check_in.pause", "write"),
    ExtensionTool("clear_shared_location", "Remove active shared-location access at the user's explicit request. Do not change residence facts or grant any sharing permission.", "EmptyArguments", "DomainMutationResult", "check_ins", "location.clear", "write"),
    ExtensionTool("request_help", "Record a simulated help request only when the exact direct-control consented request is already attached by the household to this saved turn. No consent argument, operator action, real contact or dispatch is permitted.", "HelpArguments", "DomainMutationResult", "check_ins", "help.request", "write"),
    ExtensionTool("prepare_structured_reply", "Prepare bounded plain reply text and at most two display-only optional questions. This stages no durable write; only CaseService can finish the saved turn. Choices never execute commands or grant consent. Call last, after domain changes.", "StructuredReplyArguments", "StructuredReplyResult", "structured_replies", access="prepare"),
)


class ExtensionRegistry(ToolRegistry):
    def __init__(self, base=None, config=None):
        self.base = base or ToolRegistry(())
        self.config = config or ExtensionConfig()
        self.extension_definitions = tuple(item for item in TOOLS if getattr(self.config, item.family))
        super().__init__(self.base.definitions + self.extension_definitions)
        self.extension_names = {item.name for item in self.extension_definitions}

    def validate_arguments(self, name, arguments):
        definition = self.by_name.get(name)
        if definition is None:
            raise InvalidInput("$", "Tool is outside the household allowlist.")
        if name in self.extension_names:
            bounded(arguments, 16000)
            validate(definition.arguments_schema, arguments)
            if name == "update_financial_state":
                validate_household_financial_input(arguments["update"])
        else:
            shared_validate(definition.arguments_schema, arguments)

    def invoke(self, name, arguments, context):
        if name not in self.extension_names:
            return self.base.invoke(name, arguments, context)
        with context.lock:
            context.check_budget()
            try:
                self.validate_arguments(name, arguments)
                definition = self.by_name[name]
                if definition.operation:
                    payload = arguments["update"] if name == "update_financial_state" else arguments
                    result = adapters.mutate(context, definition.operation, payload)
                else:
                    handler = {"read_financial_summary": adapters.read_financial_summary,
                               "read_check_in_status": adapters.read_check_in_status,
                               "prepare_structured_reply": adapters.stage_structured_reply}[name]
                    result = handler(context, arguments)
                try:
                    bounded(result, context.max_result_chars)
                except InvalidInput:
                    raise AgentFailure("agent_context_limit", "Extension output exceeds the context limit. Accepted changes remain saved.")
                try:
                    validate(definition.result_schema, result)
                except InvalidInput:
                    raise AgentFailure("invalid_extension_result", "Extension output violates its contract. Accepted changes remain saved.") from None
                return result
            except (InvalidInput, OutputValidationError):
                # No reflection of model input, dynamic fields or exception text.
                return failure({"code": "invalid_tool_input", "message": "Use the exact enabled extension contract and valid saved references.", "retryable": False})
            except ServiceError as error:
                return failure({"code": error.issue["code"], "message": "The authorized CaseService operation could not complete.", "retryable": error.issue["retryable"]})

    def strands_tools(self):
        from strands import ToolContext, tool

        def bind(definition):
            def invoke(tool_context: ToolContext, **arguments):
                return self.invoke(definition.name, tool_context.tool_use["input"],
                                   tool_context.invocation_state["case_context"])
            schema = inline_schema(definition.arguments_schema)
            if schema.get("type") != "object" or any(key in schema for key in ("anyOf", "oneOf", "allOf")):
                raise ValueError("Provider-facing extension schemas require plain object roots.")
            invoke.__name__ = definition.name
            invoke.__signature__ = inspect.Signature([
                inspect.Parameter(key, inspect.Parameter.KEYWORD_ONLY, annotation=Any,
                                  default=inspect.Parameter.empty if key in schema.get("required", []) else None)
                for key in schema.get("properties", {})
            ] + [inspect.Parameter("tool_context", inspect.Parameter.KEYWORD_ONLY, annotation=ToolContext)])
            invoke.__annotations__ = {key: Any for key in schema.get("properties", {})}
            invoke.__annotations__["tool_context"] = ToolContext
            return tool(name=definition.name, description=definition.description,
                        inputSchema={"json": schema}, context=True)(invoke)
        return self.base.strands_tools() + [bind(item) for item in self.extension_definitions]


def create_registry(base=None, config=None):
    return ExtensionRegistry(base, config)
