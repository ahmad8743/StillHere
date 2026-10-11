"""Shared MVP assembly. Domain proposals never write the database themselves."""

import copy
import hashlib
import json
import secrets
import sqlite3
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from .contracts import InvalidInput, VERSION, canonical_json, validate


class IntegrationServiceMixin:
    def _apply_integrated_command(self, connection, owner, snapshot, command, now):
        from .check_ins import Authority
        snapshot = copy.deepcopy(snapshot)
        if command["type"] in ("finance.update", "scenario.set"):
            from .finance import apply_financial_update, set_financial_scenario
            from .finance.forecast import FinanceInputError
            if self._instant(command["occurred_at"]) > self._instant(now):
                raise InvalidInput("$.occurred_at", "Financial reports cannot be after receipt.")
            ledger = snapshot["finance"]["ledger"]
            if command["type"] == "finance.update":
                proposed = apply_financial_update(ledger, command["payload"], event_id=command["event_id"],
                          effective_at=command["occurred_at"], received_at=now, time_zone=snapshot["time_zone"])
            else:
                start = command["payload"].get("start_date") or self._instant(now).astimezone(ZoneInfo(snapshot["time_zone"])).date().isoformat()
                try:
                    alternatives = self._finance_alternatives(snapshot, command["payload"]["scenario"].get("alternative_ids", []), now)
                except InvalidInput as error:
                    return snapshot, self._result(command["event_id"], "needs_clarification", now, snapshot, issue={"code": "action_costs_unresolved", "field": error.field, "message": str(error), "retryable": False})
                proposed = set_financial_scenario(ledger, command["payload"]["scenario"], event_id=command["event_id"],
                          effective_at=command["occurred_at"], received_at=now, time_zone=snapshot["time_zone"], start_date=start, action_alternatives=alternatives)
            validate("C08FinanceUpdateResult", proposed)
            if proposed["status"] != "applied":
                result = self._result(command["event_id"], proposed["status"], now, snapshot)
                result["issues"] = proposed["issues"]
                return snapshot, result
            snapshot["finance"]["ledger"] = proposed["next_ledger"]
            try:
                self._refresh_finance(snapshot, now, command["event_id"],
                                      start_date=command["payload"].get("start_date"),
                                      input_version=snapshot["case_version"]+1,
                                      changed_ids=proposed["changed_record_ids"])
            except FinanceInputError as error:
                # Preserve accepted ledger edits while retaining the last valid forecast.
                # A later calculation can use a reconciled scenario/reference snapshot.
                snapshot["finance"].update(state="pending", pending_input_case_version=snapshot["case_version"]+1)
                snapshot["notices"].append({"code": "finance_calculation_unavailable", "message": "Financial inputs are saved; the prior forecast is retained pending reconciliation and recalculation.", "retryable": False})
            return snapshot, None
        if command["type"] in ("check_in.enroll", "check_in.reply", "check_in.pause", "help.request", "location.share", "location.clear"):
            permissions = frozenset({"check_in.write", "help.write", "location.write"})
            caller = Authority(snapshot["case_id"], "household", "household_" + owner[:32], permissions, True)
            return self._apply_check_in_command(connection, snapshot, command, now, caller), None
        if command["type"] == "application.update":
            from .applications import update_application
            application = next((item for item in snapshot["applications"] if item["id"] == command["payload"]["application_id"]), None)
            if application is None:
                raise InvalidInput("$.application_id", "Select a saved application in this case.")
            rules = self._application_rules(snapshot, application["program_id"], application["rule_version"], now)
            proposal = update_application(snapshot, command["payload"], rules, event_id=command["event_id"], occurred_at=command["occurred_at"], received_at=now)
            snapshot["applications"] = [proposal["application"] if item["id"] == application["id"] else item for item in snapshot["applications"]]
            snapshot["evidence"] = proposal["evidence"]
            if command["payload"].get("evidence_changes"):
                if snapshot["plan"]["state"] != "not_requested":
                    snapshot["plan"].update(state="pending", pending_input_case_version=snapshot["case_version"]+1)
                if snapshot["finance"]["state"] != "not_calculated":
                    snapshot["finance"].update(state="pending", pending_input_case_version=snapshot["case_version"]+1)
            return snapshot, None
        raise InvalidInput("$.type", "Integrated handler is unavailable.")

    @staticmethod
    def _instant(value):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    def _finance_alternatives(self, snapshot, selected_ids, now):
        from .planner.costs import export_action_costs, propose_alternative_selection
        if not selected_ids:
            return []
        exported = export_action_costs(snapshot["plan"], input_case_version=snapshot["case_version"], as_of=now, time_zone=snapshot["time_zone"])
        proposal = propose_alternative_selection(exported, selected_ids, existing_commitments=snapshot["finance"]["ledger"]["expense_commitments"])
        if proposal["state"] != "proposed":
            raise InvalidInput("$.scenario.alternative_ids", "Reconcile current path selection and explicit dated costs before comparing; unknown costs remain unknown.")
        alternatives = []
        for identifier in selected_ids:
            individual = propose_alternative_selection(exported, [identifier], existing_commitments=snapshot["finance"]["ledger"]["expense_commitments"])
            costs = copy.deepcopy(individual["add_commitments"])
            # Domain export ownership metadata remains a trusted backend input.
            for cost in costs:
                if cost["date"] is None or cost["amount_cents"] is None:
                    raise InvalidInput("$.scenario.alternative_ids", "An action comparison requires known costs and explicit dates.")
                if cost.get("due_at") is None:
                    cost.pop("due_at", None)
                cost.update(origin="recovery_planner", fulfilled_cents=0, actual_event_ids=[])
            action = next(item for item in snapshot["plan"]["actions"] if item["id"] == identifier)
            alternatives.append({"id": identifier, "label": action["title"], "costs": costs, "replaces_commitment_ids": individual["remove_commitment_ids"]})
        return alternatives

    def _refresh_finance(self, snapshot, now, event_id, *, start_date=None, input_version=None, changed_ids=()):
        from .finance import compare_financial_scenarios, finance_reassessment, prepare_forecast_publication
        version = snapshot["case_version"] if input_version is None else input_version
        start_date = start_date or self._instant(now).astimezone(ZoneInfo(snapshot["time_zone"])).date().isoformat()
        prior = copy.deepcopy(snapshot["finance"])
        forecasts = compare_financial_scenarios(snapshot["finance"]["ledger"], start_date=start_date,
                    time_zone=snapshot["time_zone"], input_case_version=version)
        validate("C08ForecastBundle", forecasts)
        published = prepare_forecast_publication(forecasts, current_case_version=version, computed_at=now, publication_event_id=event_id)
        validate("C08CurrentFinance", published["proposed_finance"])
        reassessment = finance_reassessment(prior if prior.get("baseline") else None, forecasts, changed_record_ids=changed_ids)
        validate("C08FinanceReassessment", reassessment)
        snapshot["finance"] = {**published["proposed_finance"], "ledger": snapshot["finance"]["ledger"], "reassessment": reassessment}
        if reassessment["required"] and snapshot["plan"]["state"] != "not_requested":
            # Financial constraints request a new evaluation; terminal work is retained.
            snapshot["plan"].update(state="pending", pending_input_case_version=version, finance_reassessment=copy.deepcopy(reassessment))

    def _application_rules(self, snapshot, program_id, version, now):
        from .knowledge import ProgramRuleStore
        from .knowledge.rules import build_query
        from .service import ServiceError
        store = ProgramRuleStore(loader=self.read_program_catalog, version_loader=self.read_program_version)
        rules = store.lookup(build_query(snapshot, {"program_id": program_id, "version": version}, now), time.monotonic()+10)
        if rules["state"] != "available":
            raise ServiceError(503, "application_rules_unavailable", "A current published application reference is required; existing drafts are retained.", True)
        return rules

    def _init_integration(self, connection):
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS operators (
                token_digest TEXT PRIMARY KEY, operator_id TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS operator_scopes (
                token_digest TEXT NOT NULL REFERENCES operators(token_digest),
                case_id TEXT NOT NULL REFERENCES cases(case_id),
                permissions_json TEXT NOT NULL,
                PRIMARY KEY (token_digest, case_id)
            );
            CREATE TABLE IF NOT EXISTS check_in_states (
                case_id TEXT PRIMARY KEY REFERENCES cases(case_id), state_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS simulated_effects (
                effect_id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(case_id),
                event_id TEXT NOT NULL, effect_json TEXT NOT NULL
            );
        """)

    def provision_operator(self, case_ids, *, operator_id=None, permissions=None):
        """Local OS/database-authorized administration; never exposed over HTTP."""
        from .service import ServiceError
        allowed = {"follow_up.read", "follow_up.write", "needs.read", "location.read"}
        permissions = allowed if permissions is None else set(permissions)
        operator_id = operator_id or "operator_" + secrets.token_hex(16)
        validate("Id", operator_id)
        if not permissions <= allowed or "follow_up.read" not in permissions:
            raise InvalidInput("$.permissions", "Use explicit MVP operator permissions.")
        if not isinstance(case_ids, list) or not 1 <= len(case_ids) <= 256 or len(set(case_ids)) != len(case_ids):
            raise InvalidInput("$.case_ids", "Provide unique explicit case scopes.")
        token = "operator_session_" + secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self._transaction() as connection:
            for case_id in case_ids:
                validate("Id", case_id)
                if not connection.execute("SELECT 1 FROM cases WHERE case_id=?", (case_id,)).fetchone():
                    raise ServiceError(404, "case_unavailable", "Operator scope requires an existing case.")
            connection.execute("INSERT INTO operators VALUES (?,?,?,1)", (digest, operator_id, self.clock()))
            for case_id in case_ids:
                connection.execute("INSERT INTO operator_scopes VALUES (?,?,?)", (digest, case_id, canonical_json(sorted(permissions))))
        return {"contract_version": VERSION, "operator_id": operator_id, "session_token": token,
                "case_ids": list(case_ids), "permissions": sorted(permissions)}

    def revoke_operator(self, operator_id):
        validate("Id", operator_id)
        with self._transaction() as connection:
            connection.execute("UPDATE operators SET active=0 WHERE operator_id=?", (operator_id,))

    @staticmethod
    def _operator(connection, token, case_id=None, permission="follow_up.read"):
        from .service import ServiceError
        from .check_ins import Authority
        if not isinstance(token, str) or not 1 <= len(token) <= 128:
            raise ServiceError(401, "unauthorized", "A scoped operator session is required.")
        digest = hashlib.sha256(token.encode()).hexdigest()
        operator = connection.execute("SELECT * FROM operators WHERE token_digest=? AND active=1", (digest,)).fetchone()
        if operator is None:
            raise ServiceError(401, "unauthorized", "A scoped operator session is required.")
        if case_id is None:
            return digest
        scope = connection.execute("SELECT permissions_json FROM operator_scopes WHERE token_digest=? AND case_id=?", (digest, case_id)).fetchone()
        if scope is None or permission not in json.loads(scope["permissions_json"]):
            raise ServiceError(404, "case_unavailable", "Review is unavailable to this operator.")
        return Authority(case_id, "operator", operator["operator_id"], frozenset(json.loads(scope["permissions_json"])))

    @staticmethod
    def _check_in_state(connection, case_id):
        from .check_ins import empty_state
        row = connection.execute("SELECT state_json FROM check_in_states WHERE case_id=?", (case_id,)).fetchone()
        return json.loads(row["state_json"]) if row else empty_state(case_id)

    def _save_check_in(self, connection, snapshot, transition, event_id):
        from .check_ins import validate as validate_check_in
        state = transition["state"]
        validate_check_in("State", state)
        if state["case_id"] != snapshot["case_id"]:
            raise InvalidInput("$.case_id", "Check-in result must belong to this case.")
        connection.execute("INSERT INTO check_in_states VALUES (?,?) ON CONFLICT(case_id) DO UPDATE SET state_json=excluded.state_json",
                           (snapshot["case_id"], canonical_json(state)))
        projection = copy.deepcopy(state["check_in"])
        current = next((item for item in projection["occurrences"] if item["id"] == projection["current_occurrence_id"]), None)
        projection["schedule"] = ({"id": current["schedule_id"], "occurrence_id": current["id"],
                                  **{key: current[key] for key in ("due_at", "grace_deadline", "grace_minutes", "time_zone", "channel", "status")}}
                                 if current else None)
        projection["attempts"] = [copy.deepcopy(attempt) for occurrence in projection["occurrences"] for attempt in occurrence["attempts"]]
        snapshot.update(check_in=projection, shared_location=copy.deepcopy(state["shared_location"]),
                        follow_ups=copy.deepcopy(state["follow_ups"]))
        for effect in transition["effects"]:
            if effect["simulation"] is not True:
                raise InvalidInput("$.simulation", "Only simulated check-in effects are supported.")
            connection.execute("INSERT OR IGNORE INTO simulated_effects VALUES (?,?,?,?)",
                               (effect["id"], snapshot["case_id"], event_id, canonical_json(effect)))
            if effect["kind"] == "urgent_help_required":
                notice = {"code": "simulated_help_requested", "message": "For immediate danger call 911. For local essential-help referrals contact 211. This is a simulated review; no contact or dispatch has occurred.",
                          "retryable": False}
                if notice not in snapshot["notices"]:
                    snapshot["notices"].append(notice)

    def _apply_check_in_command(self, connection, snapshot, command, now, caller):
        from .check_ins import CheckInError, apply_command
        try:
            needs = command["payload"].get("permitted_need_ids", [])
            if not set(needs) <= {need["id"] for need in snapshot["needs"]}:
                raise InvalidInput("$.payload.permitted_need_ids", "Select only needs in this authorized case.")
            if command["type"] == "check_in.enroll" and command["payload"]["time_zone"] != snapshot["time_zone"]:
                raise InvalidInput("$.payload.time_zone", "Use the case time zone.")
            transition = apply_command(self._check_in_state(connection, snapshot["case_id"]), command["type"], command["payload"],
                                       event_id=command["event_id"], reported_at=command["occurred_at"], received_at=now, caller=caller)
            self._save_check_in(connection, snapshot, transition, command["event_id"])
        except CheckInError as error:
            raise InvalidInput(error.field, str(error)) from None
        return snapshot

    def process_due_check_ins(self, *, batch_size=100):
        """Standalone worker entry point; local database authority, no model/network."""
        from .check_ins import Authority, process_due
        if type(batch_size) is not int or not 1 <= batch_size <= 1000:
            raise ValueError("batch_size must be between 1 and 1000")
        with self._connection() as connection:
            ids = [row["case_id"] for row in connection.execute("SELECT case_id FROM check_in_states ORDER BY case_id")]
        changed = 0
        # Scan every case so paused/answered cases cannot starve later active ones.
        for case_id in ids:
            with self._transaction() as connection:
                now = self.clock()
                state = self._check_in_state(connection, case_id)
                transition = process_due(state, now=now, caller=Authority(case_id, "worker", "check_in_worker", frozenset({"check_in.process"})))
                if not transition["changed"]:
                    continue
                row = connection.execute("SELECT snapshot_json FROM cases WHERE case_id=?", (case_id,)).fetchone()
                snapshot = json.loads(row["snapshot_json"])
                before = canonical_json(snapshot)
                event_id = "worker_" + self._fingerprint([case_id, [effect["id"] for effect in transition["effects"]]])[:48]
                self._save_check_in(connection, snapshot, transition, event_id)
                self._commit_derived(connection, snapshot, before, event_id, {"type": "check_in.process_due", "simulation": True}, now)
                changed += 1
            if changed >= batch_size:
                break
        return {"contract_version": VERSION, "processed_cases": changed, "simulation": True}

    def _commit_derived(self, connection, snapshot, before, event_id, transition, now):
        snapshot["case_version"] += 1
        snapshot["updated_at"] = now
        validate("CaseSnapshot", snapshot)
        connection.execute("UPDATE cases SET snapshot_json=? WHERE case_id=?", (canonical_json(snapshot), snapshot["case_id"]))
        connection.execute("INSERT INTO events (case_id,event_id,fingerprint,command_json,first_received_at,applied_received_at,applied_version,before_case_json) VALUES (?,?,?,?,?,?,?,?)",
                           (snapshot["case_id"], event_id, self._fingerprint(transition), canonical_json(transition), now, now, snapshot["case_version"], before))
        return self._result(event_id, "applied", now, snapshot, snapshot["case_version"])

    def execute_agent_derivation(self, token, case_id, parent_event_id, run_id, operation, arguments,
                                 expected_version, deadline, max_result_chars=48000):
        """Recompute derived domain proposals under authorization, version and lease."""
        from .service import ServiceError
        event_id = "agent_tool_" + self._fingerprint([case_id, parent_event_id, operation, arguments])[:48]
        now = self.clock()
        try:
            with self._transaction() as connection:
                now = self.clock()
                owner = self._session(connection, token)
                snapshot = self._snapshot(connection, owner, case_id)
                self._active_run(connection, case_id, parent_event_id, run_id, now)
                if time.monotonic() >= deadline:
                    raise ServiceError(409, "agent_timeout", "Derived work reached the active run deadline.")
                previous = connection.execute("SELECT * FROM events WHERE case_id=? AND event_id=?", (case_id, event_id)).fetchone()
                if previous and previous["applied_version"] is not None:
                    return self._result(event_id, "already_applied", now, snapshot, previous["applied_version"])
                if snapshot["case_version"] != expected_version:
                    return self._result(event_id, "conflict", now, snapshot, issue={"code": "version_conflict", "message": "Case inputs changed before derived publication.", "retryable": False})
                before = canonical_json(snapshot)
                if operation == "application.prepare":
                    from .applications import prepare_application
                    validate("PrepareApplicationArguments", arguments)
                    rules = self._application_rules(snapshot, arguments["program_id"], arguments["rule_version"], now)
                    proposed = prepare_application(snapshot, arguments, rules, prepared_at=now)
                    validate("C06ApplicationPreparationResult", proposed)
                    if len(snapshot["applications"]) >= 32:
                        raise InvalidInput("$.applications", "Application capacity reached.")
                    snapshot["applications"].append(proposed["application"])
                    self._merge_sources(snapshot, proposed["sources"])
                elif operation == "dashboard.publish":
                    from .outputs import prepare_dashboard_publication, validate_dashboard_publication
                    validate("PublishDashboardArguments", arguments)
                    proposed = prepare_dashboard_publication(snapshot, arguments, now=now)
                    proposed = validate_dashboard_publication(snapshot, proposed, now=now)
                    snapshot["components"] = proposed["components"]
                    snapshot["dashboard_output"] = {key: proposed[key] for key in ("input_case_version", "prepared_at", "component_states")}
                elif operation == "finance.calculate":
                    validate("ForecastToolArguments", arguments)
                    self._refresh_finance(snapshot, now, event_id, start_date=arguments.get("start_date"))
                else:
                    raise ServiceError(400, "tool_forbidden", "Derived operation is outside the household allowlist.")
                # Check compact output before committing any effect.
                preview = self._result(event_id, "applied", now, snapshot, snapshot["case_version"]+1)
                if len(canonical_json(self.domain_summary(preview, operation))) > max_result_chars:
                    raise ServiceError(400, "agent_context_limit", "Derived output exceeds the result limit; no result was saved.")
                self._active_run(connection, case_id, parent_event_id, run_id, self.clock())
                if time.monotonic() >= deadline:
                    raise ServiceError(409, "agent_timeout", "Late derived work cannot publish.")
                return self._commit_derived(connection, snapshot, before, event_id, {"type": operation, "arguments": arguments, "parent_event_id": parent_event_id}, now)
        except (InvalidInput, ServiceError, sqlite3.Error) as error:
            return self._failed(event_id, now, error)
        except ValueError as error:
            # Domain errors have bounded messages; no provider exception is passed here.
            return self._failed(event_id, now, InvalidInput(getattr(error, "field", "$"), str(error)))

    @staticmethod
    def _merge_sources(snapshot, sources):
        identifiers = {source["id"] for source in sources}
        snapshot["sources"] = [source for source in snapshot["sources"] if source.get("id") not in identifiers] + copy.deepcopy(sources)

    @staticmethod
    def domain_summary(result, operation):
        snapshot = result["case_snapshot"]
        summary = None
        if snapshot is not None:
            summary = {"case_version": snapshot["case_version"]}
            if operation.startswith("application"):
                summary["applications"] = [{key: app[key] for key in ("id", "official_url", "preparation_state", "stage_report", "agency_outcome", "next_step")}
                                           for app in snapshot["applications"]]
            elif operation.startswith("dashboard"):
                summary["components"] = snapshot["components"]
            elif operation.startswith("finance") or operation == "scenario.set":
                finance = snapshot["finance"]
                summary["finance"] = {"state": finance["state"], "input_case_version": finance["input_case_version"], "computed_at": finance["computed_at"],
                                      "baseline": {key: finance["baseline"].get(key) for key in ("state", "opening_accessible_cents", "first_gap", "first_essential_gap", "ending_projected_position_cents", "warnings")} if finance["baseline"] else None,
                                      "scenarios": [{key: item.get(key) for key in ("scenario_id", "label", "state", "first_gap", "ending_projected_position_cents", "scenario_assumptions")} for item in finance["scenarios"]]}
            else:
                summary.update(check_in=snapshot["check_in"], follow_ups=snapshot["follow_ups"], notices=snapshot["notices"])
        output = {key: copy.deepcopy(value) for key, value in result.items() if key != "case_snapshot"}
        output["summary"] = summary
        validate("DomainMutationResult", output)
        return output

    def read_operator_queue(self, token, case_id=None):
        from .check_ins import operator_projection
        with self._connection() as connection:
            digest = self._operator(connection, token)
            case_ids = ([case_id] if case_id is not None else [row["case_id"] for row in connection.execute(
                "SELECT case_id FROM operator_scopes WHERE token_digest=? ORDER BY case_id", (digest,))])
            projections = []
            for identifier in case_ids:
                caller = self._operator(connection, token, identifier)
                snapshot = json.loads(connection.execute("SELECT snapshot_json FROM cases WHERE case_id=?", (identifier,)).fetchone()["snapshot_json"])
                view = operator_projection(self._check_in_state(connection, identifier), caller=caller, now=self.clock(), relevant_needs=snapshot["needs"])
                view.update(contract_version=VERSION, case_version=snapshot["case_version"])
                projections.append(view)
            return {"contract_version": VERSION, "cases": projections, "simulation": True}

    def execute_operator(self, token, command):
        from .service import ServiceError
        event_id, now = self._event_id(command), self.clock()
        try:
            with self._transaction() as connection:
                validate("CommandEnvelope", command)
                caller = self._operator(connection, token, command["case_id"], "follow_up.write")
                if command["channel"] != "operator" or command["type"] not in ("follow_up.acknowledge", "follow_up.record"):
                    raise ServiceError(403, "channel_forbidden", "Operators can only change the scoped simulated review workflow.")
                if event_id.startswith(("agent_", "worker_")):
                    raise InvalidInput("$.event_id", "Internal event identities are reserved.")
                from .commands import validate_payload
                validate_payload(command["type"], command["payload"])
                snapshot = json.loads(connection.execute("SELECT snapshot_json FROM cases WHERE case_id=?", (command["case_id"],)).fetchone()["snapshot_json"])
                logical = {key: value for key, value in command.items() if key != "expected_case_version"}
                logical["operator_id"] = caller.subject_id
                fingerprint = self._fingerprint(logical)
                previous = connection.execute("SELECT * FROM events WHERE case_id=? AND event_id=?", (command["case_id"], event_id)).fetchone()
                if previous and previous["fingerprint"] != fingerprint:
                    raise ServiceError(400, "event_id_reused", "Changed intent or actor requires a new event_id.")
                if previous and previous["applied_version"] is not None:
                    result = self._result(event_id, "already_applied", now, snapshot, previous["applied_version"])
                elif command["expected_case_version"] != snapshot["case_version"]:
                    if previous is None:
                        connection.execute("INSERT INTO events (case_id,event_id,fingerprint,command_json,first_received_at) VALUES (?,?,?,?,?)",
                                           (command["case_id"], event_id, fingerprint, canonical_json(logical), now))
                    result = self._result(event_id, "conflict", now, snapshot, issue={"code": "version_conflict", "message": "Refresh the review before retrying.", "retryable": False})
                else:
                    before = canonical_json(snapshot)
                    snapshot = self._apply_check_in_command(connection, snapshot, command, now, caller)
                    snapshot["case_version"] += 1
                    snapshot["updated_at"] = now
                    validate("CaseSnapshot", snapshot)
                    connection.execute("UPDATE cases SET snapshot_json=? WHERE case_id=?", (canonical_json(snapshot), command["case_id"]))
                    if previous is None:
                        connection.execute("INSERT INTO events (case_id,event_id,fingerprint,command_json,first_received_at) VALUES (?,?,?,?,?)",
                                           (command["case_id"], event_id, fingerprint, canonical_json(logical), now))
                    connection.execute("UPDATE events SET applied_version=?,applied_received_at=?,before_case_json=? WHERE case_id=? AND event_id=?",
                                       (snapshot["case_version"], now, before, command["case_id"], event_id))
                    result = self._result(event_id, "applied", now, snapshot, snapshot["case_version"])
            # Household data is discarded before crossing the operator boundary.
            result.pop("case_snapshot")
            result["operator_projection"] = self.read_operator_queue(token, command["case_id"])["cases"][0]
            return result
        except (InvalidInput, ServiceError, sqlite3.Error) as error:
            result = self._failed(event_id, now, error)
            result.pop("case_snapshot")
            result["operator_projection"] = None
            return result
