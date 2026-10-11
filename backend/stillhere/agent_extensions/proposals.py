"""Generate exact owner-review patches; never apply them to the shared checkout.

Run this only to refresh proposals after reviewing a changed shared baseline.
Tests and live smoke consume the saved patch in an isolated disposable checkout.
"""

import difflib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DESTINATION = Path(__file__).parent / "integration_proposals" / "shared-wiring.patch"
DOMAIN_DESTINATION = Path(__file__).parent / "integration_proposals" / "domain-dependencies.patch"
DOCUMENT_DESTINATION = Path(__file__).parent / "integration_proposals" / "documentation.patch"
FIXTURE_DESTINATION = Path(__file__).parent / "integration_proposals" / "shared-fixtures.patch"


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError("Shared proposal baseline changed; review before regenerating.")
    return source.replace(old, new, 1)


EXTENSION_COMMAND = '''    def execute_agent_extension_command(self, token, case_id, parent_event_id, run_id,
                                        command_type, arguments, expected_version,
                                        deadline, max_result_chars=48000):
        """Reviewed household-only writes; lease, bounds and commit are atomic."""
        from .agent_extensions.adapters import COMMANDS, child_event_id
        from .agent_extensions.schema import bounded
        child_id = "agent_tool_invalid_input"
        now = self.clock()
        try:
            with self._transaction() as connection:
                now = self.clock()
                owner = self._session(connection, token)
                self._snapshot(connection, owner, case_id)
                self._active_run(connection, case_id, parent_event_id, run_id, now)
                if command_type not in COMMANDS:
                    raise ServiceError(403, "tool_forbidden", "Operation is outside the household extension allowlist.")
                if time.monotonic() >= deadline:
                    raise ServiceError(409, "agent_timeout", "Late extension work cannot commit.")
                bounded(arguments, 16000)
                child_id = child_event_id(case_id, parent_event_id, command_type, arguments)
                parent = json.loads(connection.execute(
                    "SELECT command_json FROM events WHERE case_id=? AND event_id=?",
                    (case_id, parent_event_id)).fetchone()["command_json"])
                payload = arguments
                if command_type == "help.request":
                    # Only the exact authenticated direct-control request attests consent.
                    # No Boolean, role, prompt text or model output can grant this scope.
                    validate("HelpRequestPayload", {**arguments, "consent": True})
                    attested = parent["payload"].get("help_request")
                    if "consent" in arguments or attested != {**arguments, "consent": True}:
                        raise ServiceError(403, "explicit_help_consent_required", "Submit this exact help request through an authenticated direct control.")
                    payload = attested
                command = {"contract_version": VERSION, "case_id": case_id,
                           "event_id": child_id, "expected_case_version": expected_version,
                           "occurred_at": parent["occurred_at"], "channel": "chat",
                           "type": command_type, "payload": payload}
                result = self._execute(connection, owner, command, child_id, now)
                compact = self.domain_summary(result, command_type)
                try:
                    bounded(compact, max_result_chars)
                except InvalidInput:
                    raise ServiceError(400, "agent_context_limit", "Extension output exceeds its bound; no new effect was saved.") from None
                self._active_run(connection, case_id, parent_event_id, run_id, self.clock())
                if time.monotonic() >= deadline:
                    raise ServiceError(409, "agent_timeout", "Late extension work cannot commit.")
                return result
        except (InvalidInput, ServiceError, sqlite3.Error) as error:
            return self._failed(child_id, now, error)

'''


def proposed_files():
    files = {}
    path = "backend/stillhere/agent/registry.py"
    source = (ROOT / path).read_text()
    source = replace_once(source, "    def invoke(self, name, arguments, context):", '''    def validate_arguments(self, name, arguments):
        definition = self.by_name.get(name)
        if definition is None:
            raise InvalidInput("$", "Tool is outside the household allowlist.")
        validate(definition.arguments_schema, arguments)

    def invoke(self, name, arguments, context):''')
    files[path] = source
    path = "backend/stillhere/agent/provider.py"
    source = (ROOT / path).read_text()
    source = replace_once(source, '                validate(definition.arguments_schema, event.tool_use["input"])',
                          '                registry.validate_arguments(event.tool_use["name"], event.tool_use["input"])')
    # Append instructions to the existing prompt, preserving current grounding rules.
    source = replace_once(source, 'system_prompt=SYSTEM_PROMPT, tools=registry.strands_tools()',
                          'system_prompt=SYSTEM_PROMPT + EXTENSION_PROMPT, tools=registry.strands_tools()')
    source += '''\n\nEXTENSION_PROMPT = """
Use household extensions only for explicit user requests. CaseService owns calculations,
reconciliation and writes. Inspect applied/already_applied and saved versions before
claiming a result. Scenario money is hypothetical; approval is not received money.
Enrollment and location sharing remain direct controls. Never provision an operator,
assign authority or send welfare outreach. A help request requires a matching consented
direct-control payload already saved on this exact turn. Questions grant no authority.
If structured replies are enabled, call prepare_structured_reply last with grounded
plain text and optional questions, after all domain changes; preserve unknowns and
source attribution. Never claim an uncalled tool, unsuccessful write or live delivery.
"""\n'''
    files[path] = source
    path = "backend/stillhere/integration.py"
    source = (ROOT / path).read_text()
    source = replace_once(source, "changed_record_ids=changed_ids)", "changed_record_ids=list(changed_ids))")
    source = replace_once(source, 'self._refresh_finance(snapshot, now, event_id, start_date=arguments.get("start_date"))',
                          'self._refresh_finance(snapshot, now, event_id, start_date=arguments.get("start_date"), input_version=snapshot["case_version"]+1)')
    files[path] = source
    path = "backend/stillhere/agent/config.py"
    source = (ROOT / path).read_text()
    source = replace_once(source, '    enable_tasks: bool = False', '''    enable_tasks: bool = False
    extensions: object = None''')
    source = replace_once(source, '        settings = {}', '''        from ..agent_extensions import ExtensionConfig
        settings = {"extensions": ExtensionConfig.from_environment(os.environ)}''')
    files[path] = source
    path = "backend/stillhere/agent/runtime.py"
    source = (ROOT / path).read_text()
    source = replace_once(source, '        if self.config.enable_incidents and incident_facade is None:', '''        from ..agent_extensions import ExtensionConfig, create_registry
        from ..agent_extensions.provider import ExtensionProvider
        flags = self.config.extensions or ExtensionConfig()
        if any(vars(flags).values()):
            self.registry = create_registry(self.registry, flags)
        if flags.structured_replies:
            self.provider = ExtensionProvider(self.provider)
        if self.config.enable_incidents and incident_facade is None:''')
    source = replace_once(source, '                if not isinstance(text, str) or not text.strip() or len(text) > 8000:\n                    raise AgentFailure("invalid_agent_reply", "The agent did not return a valid bounded reply.")', '''                from ..agent_extensions import ExtensionConfig, normalize_reply
                if not isinstance(text, str) and not (self.config.extensions or ExtensionConfig()).structured_replies:
                    raise AgentFailure("invalid_agent_reply", "Structured replies are not enabled.")
                normalize_reply(self.service.read_case(token, case_id), text, now=self.service.clock())''')
    source = replace_once(source, 'snapshot = self.service.finish_agent_turn(token, case_id, event_id, claim["run_id"], text, issue)',
                          'snapshot = self.service.finish_agent_turn(token, case_id, event_id, claim["run_id"], text if isinstance(text, str) else "", issue, reply=text if isinstance(text, dict) else None)')
    files[path] = source
    path = "backend/stillhere/service.py"
    source = (ROOT / path).read_text()
    if 'import time\n' not in source:
        source = replace_once(source, 'import sqlite3\n', 'import sqlite3\nimport time\n')
    source = replace_once(source, '    def finish_agent_turn(self, token, case_id, event_id, run_id, text="", issue=None):',
                          EXTENSION_COMMAND + '    def finish_agent_turn(self, token, case_id, event_id, run_id, text="", issue=None, *, reply=None):')
    source = replace_once(source, '                state = "failed" if issue else "complete"', '''                if reply is not None and issue is None:
                    from .agent_extensions import normalize_reply
                    from .outputs.validation import OutputValidationError
                    try:
                        normalized = normalize_reply(snapshot, reply, now=now)
                        text = normalized["text"]
                        turn["questions"] = normalized["questions"]
                    except (InvalidInput, OutputValidationError):
                        text = ""
                        turn.pop("questions", None)
                        issue = {"code": "invalid_structured_reply", "message": "The structured reply is invalid or stale; accepted changes remain saved.", "retryable": False}
                state = "failed" if issue else "complete"''')
    # Exact correlation is checked after replay/version gates, inside the write transaction.
    source = replace_once(source, '        before_case = canonical_json(snapshot)', '''        if command["type"] == "conversation.message":
            from .agent_extensions import correlate_answer
            correlate_answer(snapshot, command["payload"])
        before_case = canonical_json(snapshot)''')
    files[path] = source
    path = "backend/stillhere/commands.py"
    source = (ROOT / path).read_text()
    source = replace_once(source, '    validate(COMMAND_HANDLERS[command_type][0], payload)', '''    validate(COMMAND_HANDLERS[command_type][0], payload)
    if command_type == "finance.update":
        from .agent_extensions.validation import validate_household_financial_input
        validate_household_financial_input(payload)''')
    source = replace_once(source, '        if "choice_id" in command["payload"]:', '''        for key in ("reply_to_turn_id", "question_id", "choice_ids", "skipped"):
            if key in command["payload"]:
                updated["conversation"]["turns"][-1][key] = copy.deepcopy(command["payload"][key])
        if "choice_id" in command["payload"]:''')
    files[path] = source
    path = "contracts/case-service.schema.json"
    shared = json.loads((ROOT / path).read_text())
    extension = json.loads((ROOT / "contracts/parallel/agent-extensions.schema.json").read_text())
    properties = shared["$defs"]["ConversationMessagePayload"]["properties"]
    for name in ("reply_to_turn_id", "question_id", "choice_ids", "skipped"):
        properties[name] = extension["$defs"]["CorrelatedMessage"]["properties"][name]
        shared["$defs"]["ConversationTurn"]["properties"][name] = properties[name]
    properties["help_request"] = {"$ref": "#/$defs/HelpRequestPayload"}
    shared["$defs"]["ConversationMessagePayload"]["not"] = {"required": ["choice_id", "choice_ids"]}
    files[path] = json.dumps(shared, indent=2) + "\n"
    path = "backend/stillhere/agent/smoke.py"
    source = (ROOT / path).read_text()
    source = replace_once(source, '    parser.add_argument("--env-file",', '    parser.add_argument("--extensions", choices=("finance", "applications", "outputs", "no-car"), help="Delegate strict new-tool proof to agent_extensions.live_smoke")\n    parser.add_argument("--env-file",')
    source = replace_once(source, '    args = parser.parse_args()', '''    args = parser.parse_args()
    if args.extensions:
        from ..agent_extensions.live_smoke import main as extension_main
        extension_arguments = ["--mode", args.extensions, "--run-live"]
        if args.env_file:
            extension_arguments += ["--env-file", args.env_file]
        return extension_main(extension_arguments)''')
    files[path] = source
    # Existing contracts.py can validate the new optional message shape already:
    # no code change is necessary. Server uses the same runtime/config factories.
    return files


def main():
    chunks = []
    for path, proposed in proposed_files().items():
        current = (ROOT / path).read_text()
        chunks.extend(difflib.unified_diff(current.splitlines(True), proposed.splitlines(True),
                                         fromfile="a/" + path, tofile="b/" + path))
    DESTINATION.write_text("".join(chunks))
    baseline = proposed_files()
    chunks = []
    for path, proposed in domain_proposed_files(baseline).items():
        current = baseline.get(path, (ROOT / path).read_text())
        chunks.extend(difflib.unified_diff(current.splitlines(True), proposed.splitlines(True),
                                         fromfile="a/" + path, tofile="b/" + path))
    DOMAIN_DESTINATION.write_text("".join(chunks))
    chunks = []
    additions = {
        "README.md": '''
## Household agent extension proposal

New finance, application, dashboard, allowed check-in and structured-reply
adapters are independently default-off. Integration wiring remains an owner
review proposal; live verification remains pending user-run new-tool proof.
See [the extension handoff](docs/parallel/agent-extensions-handoff.md) for exact
patches, flags, offline checks and mandatory executable Bedrock assertions.
No deployment follows from slice tests.
''',
        "docs/contracts-and-progress.md": '''
### Household agent extensions — separate proposal gates

The [extension handoff](parallel/agent-extensions-handoff.md) records the new
default-off adapters, structured questions/exact answer correlation, actual
pinned-SDK outgoing schemas and direct operator/consent authorization checks.
Owned slice readiness is recorded separately from disposable proposed assembly.
Shared integrated readiness remains pending owner review/application/acceptance;
new-tool LIVE Bedrock verification remains pending genuine user-run evidence.
Existing text/planner proof cannot satisfy this new proof. CaseService owns every
durable effect. No full-component, production or deployment claim is added.
''',
        "docs/strands-capabilities.md": '''
### New household adapters — review proposal

Executable extension factories expose independently enabled finance updates,
calculation/scenarios, application preparation/reports, dashboard publication,
allowed check-ins and structured replies. Every provider-facing input has an
object root; financial union validation remains authoritative inside the nested
update envelope. Pinned Strands 1.59.0 transport checks are offline evidence.
Shared wiring/integrated acceptance and genuine new-tool live proof remain
separate pending gates. [Exact patch and user-run proof](parallel/agent-extensions-handoff.md).
''',
    }
    for path, addition in additions.items():
        current = (ROOT / path).read_text()
        proposed = current.rstrip() + "\n" + addition
        chunks.extend(difflib.unified_diff(current.splitlines(True), proposed.splitlines(True),
                                         fromfile="a/" + path, tofile="b/" + path))
    DOCUMENT_DESTINATION.write_text("".join(chunks))
    chunks = []
    for path, target, version, old in (
        ("tests/test_case_service.py", "snapshot", 1, 'snapshot["finance"].update(state="calculated", baseline={"input_case_version": 1}, computed_at=NOW)'),
        ("tests/test_intake.py", "first", 2, 'first["finance"].update(state="calculated", input_case_version=2, baseline={"input_case_version": 2}, computed_at=NOW)'),
    ):
        current = (ROOT / path).read_text()
        new = f'''from backend.stillhere.finance import compare_financial_scenarios, prepare_forecast_publication
        forecasts = compare_financial_scenarios({target}["finance"]["ledger"], start_date="2026-10-10",
            time_zone={target}["time_zone"], input_case_version={version})
        publication = prepare_forecast_publication(forecasts, current_case_version={version},
            computed_at=NOW, publication_event_id="synthetic_fixture_forecast")
        {target}["finance"] = {{**publication["proposed_finance"], "ledger": {target}["finance"]["ledger"]}}'''
        proposed = replace_once(current, old, new)
        chunks.extend(difflib.unified_diff(current.splitlines(True), proposed.splitlines(True),
                                         fromfile="a/" + path, tofile="b/" + path))
    FIXTURE_DESTINATION.write_text("".join(chunks))


def domain_proposed_files(baseline):
    """Separate review gate; apply after shared-wiring.patch and boundary review."""
    files = {}
    path = "backend/stillhere/integration.py"
    source = baseline[path]
    start = source.index("    def _finance_alternatives(")
    end = source.index("    def _refresh_finance(", start)
    source = source[:start] + '''    def _finance_alternatives(self, snapshot, selected_ids, now, *, start_date=None):
        from .boundaries import reconcile_action_costs
        if not selected_ids:
            return []
        start_date = start_date or self._instant(now).astimezone(ZoneInfo(snapshot["time_zone"])).date().isoformat()
        proposal = reconcile_action_costs(snapshot["plan"], snapshot["finance"]["ledger"], selected_ids,
            input_case_version=snapshot["case_version"], as_of=now,
            time_zone=snapshot["time_zone"], start_date=start_date)
        if proposal["state"] != "proposed":
            raise InvalidInput("$.scenario.alternative_ids", "Reconcile action selection and dated costs before comparing; unknown dates remain unknown.")
        return proposal["action_alternatives"]

''' + source[end:]
    source = replace_once(source, 'command["payload"]["scenario"].get("alternative_ids", []), now)',
                          'command["payload"]["scenario"].get("alternative_ids", []), now, start_date=start)')
    source = replace_once(source, '        forecasts = compare_financial_scenarios(', '''        from .boundaries import validate_saved_action_scenarios
        freshness = validate_saved_action_scenarios(snapshot["plan"], snapshot["finance"]["ledger"],
            input_case_version=snapshot["case_version"], as_of=now,
            time_zone=snapshot["time_zone"], start_date=start_date)
        if freshness["state"] != "current":
            from .finance.forecast import FinanceInputError
            raise FinanceInputError("$.scenarios", "Saved action quotes require explicit scenario refresh before comparing.")
        forecasts = compare_financial_scenarios(''')
    source = replace_once(source, '            from .applications import update_application',
                          '            from .boundaries import update_application_boundary')
    source = replace_once(source, '            rules = self._application_rules(snapshot, application["program_id"], application["rule_version"], now)\n            proposal = update_application(snapshot, command["payload"], rules, event_id=command["event_id"], occurred_at=command["occurred_at"], received_at=now)', '''            from .service import ServiceError
            try:
                rules = self._application_rules(snapshot, application["program_id"], application["rule_version"], now)
            except ServiceError as error:
                if error.issue["code"] != "application_rules_unavailable":
                    raise
                rules = None
            proposal = update_application_boundary(snapshot, command["payload"], rules,
                event_id=command["event_id"], occurred_at=command["occurred_at"], received_at=now)''')
    files[path] = source
    path = "backend/stillhere/service.py"
    source = baseline[path]
    source += '''
    def seed_agent_extension_smoke_costs(self, token, case_id, action_id, date):
        """Local user-run synthetic fixture API; never register with HTTP or tools.

        The date is an explicit synthetic demonstration assumption. The amount
        remains unknown. This method provides no public fee/agency claim.
        """
        from .planner import set_action_costs
        with self._transaction() as connection:
            owner = self._session(connection, token)
            snapshot = self._snapshot(connection, owner, case_id)
            if snapshot["household_mode"] != "synthetic":
                raise ServiceError(403, "synthetic_case_required", "This local fixture is limited to synthetic cases.")
            validate("Id", action_id)
            from .contracts import _validate
            _validate({"type": "string", "format": "date"}, date, "$.date")
            action = next((item for item in snapshot["plan"]["actions"] if item["id"] == action_id), None)
            if action is None:
                raise InvalidInput("$.action_id", "Select the scoped synthetic action.")
            update = {"action_id": action_id, "rule_id": action["rule_id"], "rule_version": action["rule_version"],
                      "items": [{"id": "synthetic_unknown_fee", "category": "documents", "essential": False,
                                 "amount_cents": None, "date": date, "due_at": None, "state": "unknown",
                                 "observed_at": None, "source_ids": []}]}
            now = self.clock()
            transition = {"type": "synthetic.action_costs", "update": update}
            event_id = "smoke_fixture_" + self._fingerprint([case_id, transition])[:40]
            if connection.execute("SELECT 1 FROM events WHERE case_id=? AND event_id=?", (case_id, event_id)).fetchone():
                return snapshot
            before = canonical_json(snapshot)
            snapshot["plan"] = set_action_costs(snapshot["plan"], [update], as_of=now)
            snapshot["plan"]["version"] += 1
            result = self._commit_derived(connection, snapshot, before, event_id, transition, now)
            return result["case_snapshot"]
'''
    files[path] = source
    path = "contracts/case-service.schema.json"
    schema = json.loads(baseline[path])
    planner = json.loads((ROOT / "contracts/parallel/planner.schema.json").read_text())
    def expand(value):
        if isinstance(value, dict):
            if "$ref" in value:
                return expand(planner["$defs"][value["$ref"].split("/")[-1]])
            return {key: expand(child) for key, child in value.items()}
        if isinstance(value, list):
            return [expand(child) for child in value]
        return value
    schema["$defs"]["RecoveryPlanAction"]["properties"]["cost_items"] = {
        "type": "array", "maxItems": 16, "items": expand(planner["$defs"]["PlannerCostItem"])}
    files[path] = json.dumps(schema, indent=2) + "\n"
    return files


if __name__ == "__main__":
    main()
