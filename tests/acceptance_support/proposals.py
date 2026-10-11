"""Generate review-only diffs for independently reproduced shared-file failures.

Writes only the owned shared-fixes.patch. Never applies it. Recheck the baseline
before combining with boundary/agent owner proposals. This is not test wiring.
"""

import difflib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DESTINATION = Path(__file__).with_name("shared-fixes.patch")


def once(source, old, new):
    if source.count(old) != 1:
        raise ValueError("Shared baseline changed; review and refresh the proposal")
    return source.replace(old, new, 1)


def proposed_files():
    result = {}
    path = "backend/stillhere/integration.py"
    source = (ROOT/path).read_text()
    source = once(source, "changed_record_ids=changed_ids)", "changed_record_ids=list(changed_ids))")
    source = once(source, 'self._refresh_finance(snapshot, now, event_id, start_date=arguments.get("start_date"))',
                  'self._refresh_finance(snapshot, now, event_id, start_date=arguments.get("start_date"), input_version=snapshot["case_version"]+1)')
    source = once(source, '''            from .applications import update_application
''', '''            from .boundaries import update_application_boundary
            from .service import ServiceError
''')
    source = once(source, '''            rules = self._application_rules(snapshot, application["program_id"], application["rule_version"], now)
            proposal = update_application(snapshot, command["payload"], rules, event_id=command["event_id"], occurred_at=command["occurred_at"], received_at=now)
''', '''            try:
                rules = self._application_rules(snapshot, application["program_id"], application["rule_version"], now)
            except ServiceError as error:
                if error.issue["code"] != "application_rules_unavailable":
                    raise
                rules = None
            # A source outage cannot suppress an explicit household stage report.
            # Evidence edits still require current path validation; do not guess.
            proposal = update_application_boundary(snapshot, command["payload"], rules,
                event_id=command["event_id"], occurred_at=command["occurred_at"], received_at=now)
''')
    source = once(source, '''            CREATE TABLE IF NOT EXISTS operators (
''', '''            CREATE TABLE IF NOT EXISTS access_audit (
                id INTEGER PRIMARY KEY,
                operator_id TEXT NOT NULL,
                case_id TEXT,
                operation TEXT NOT NULL,
                received_at TEXT NOT NULL,
                outcome TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS operators (
''')
    # Writer transaction makes authorization/projection/audit consistent with revocation.
    source = once(source, '''    def read_operator_queue(self, token, case_id=None):
        from .check_ins import operator_projection
        with self._connection() as connection:
''', '''    def read_operator_queue(self, token, case_id=None):
        from .service import ServiceError
        try:
            return self._read_operator_queue_audited(token, case_id)
        except ServiceError as error:
            try:
                with self._transaction() as connection:
                    digest = hashlib.sha256(token.encode()).hexdigest() if isinstance(token, str) and len(token) <= 128 else None
                    actor = connection.execute("SELECT operator_id FROM operators WHERE token_digest=?", (digest,)).fetchone()
                    # Never retain the bearer, volunteered messages, or attempted raw URL.
                    connection.execute("INSERT INTO access_audit(operator_id,case_id,operation,received_at,outcome) VALUES(?,?,?,?,?)",
                        (actor["operator_id"] if actor else "unverified", None, "read_operator_projection", self.clock(), error.issue["code"]))
            except sqlite3.Error:
                raise ServiceError(503, "storage_unavailable", "Audited operator access is unavailable.", True) from None
            raise
        except sqlite3.Error:
            raise ServiceError(503, "storage_unavailable", "Audited operator access is unavailable.", True) from None

    def _read_operator_queue_audited(self, token, case_id=None):
        from .check_ins import operator_projection
        with self._transaction() as connection:
''')
    source = once(source, '''                projections.append(view)
            return {"contract_version": VERSION, "cases": projections, "simulation": True}
''', '''                projections.append(view)
                connection.execute("INSERT INTO access_audit(operator_id,case_id,operation,received_at,outcome) VALUES(?,?,?,?,?)",
                    (caller.subject_id, identifier, "read_operator_projection", self.clock(), "granted"))
            return {"contract_version": VERSION, "cases": projections, "simulation": True}
''')
    result[path] = source

    path = "backend/stillhere/planner/service.py"
    source = (ROOT/path).read_text()
    source = once(source, '''                identity = [arguments, snapshot["facts"], tasks, catalog["version"]]
''', '''                # Domain-input generations survive our own plan/chat commits.
                # A repeated unchanged report still invalidates derived records;
                # it must not collide with the earlier revision's replay identity.
                input_generation = connection.execute(
                    "SELECT COALESCE(MAX(applied_version),0) FROM events WHERE case_id=? "
                    "AND json_extract(command_json,'$.type') IN "
                    "('fact.correct','intake.submit','task.update','application.update',"
                    "'finance.update','scenario.set','planner.inputs')",
                    (case_id,)).fetchone()[0]
                identity = [arguments, snapshot["facts"], tasks, catalog["version"], input_generation]
''')
    result[path] = source

    path = "backend/stillhere/commands.py"
    source = (ROOT/path).read_text()
    source = once(source, "from .contracts import validate", "from .contracts import InvalidInput, validate")
    source = once(source, '''    validate(COMMAND_HANDLERS[command_type][0], payload)
''', '''    validate(COMMAND_HANDLERS[command_type][0], payload)
    if command_type == "finance.update":
        reserved = {"origin", "planner_cost_id", "planner_commitment_id", "rule_id",
                    "rule_version", "actual_event_ids", "verification_state"}
        def reject_reserved(value, depth=0):
            if depth > 8:
                raise InvalidInput("$.payload", "Financial metadata exceeds the bounded depth.")
            if isinstance(value, dict):
                if reserved & value.keys():
                    raise InvalidInput("$.payload", "Backend ownership and verification fields cannot be household financial input.")
                for child in value.values():
                    reject_reserved(child, depth+1)
            elif isinstance(value, list):
                for child in value:
                    reject_reserved(child, depth+1)
        reject_reserved(payload)
''')
    source = once(source, '''    resources = updated["resources"]
''', '''    if changed_inputs and updated["applications"]:
        from .boundaries import invalidate_applications
        invalidation = invalidate_applications(updated,
            target_case_version=updated["case_version"], changed_fact_keys=sorted(changed_inputs))
        updated["applications"] = invalidation["applications"]
    resources = updated["resources"]
''')
    result[path] = source

    path = "backend/stillhere/service.py"
    source = (ROOT/path).read_text()
    source = once(source, '''    def read_case(self, token, case_id, contract_version=VERSION):
        try:
            with self._connection() as connection:
''', '''    def read_case(self, token, case_id, contract_version=VERSION):
        try:
            # Resume exposes expired interrupted work through the existing
            # audited terminal transition, without restarting provider effects.
            with self._transaction() as connection:
''')
    source = once(source, '''                return self._snapshot(connection, owner, case_id)
''', '''                snapshot = self._snapshot(connection, owner, case_id)
                self._expire_agent_runs(connection, snapshot, self.clock())
                if "dashboard_output" in snapshot:
                    from .outputs import prepare_dashboard_publication
                    refreshed = prepare_dashboard_publication(snapshot,
                        {"components": snapshot["components"]}, now=self.clock())
                    # Read projection only: retain the original publication identity
                    # and input time; derive changing source/record display states.
                    snapshot["dashboard_output"]["component_states"] = refreshed["component_states"]
                return snapshot
''')
    source = once(source, '''        before_case = canonical_json(snapshot)
''', '''        if command["type"] == "conversation.message":
            payload = command["payload"]
            if any(key in payload for key in ("choice_id", "choice_ids")) and not {"reply_to_turn_id", "question_id"} <= payload.keys():
                raise InvalidInput("$.payload.question_id", "Choice answers require the exact complete saved turn and question.")
        before_case = canonical_json(snapshot)
''')
    result[path] = source

    # Existing stricter finance shapes invalidate two legacy abbreviated
    # fixtures. Preserve their assertions; propose authoritative forecast data.
    for path, name, version in (("tests/test_case_service.py", "snapshot", 1),
                                ("tests/test_intake.py", "first", 2)):
        source = (ROOT/path).read_text()
        old = (f'        {name}["finance"].update(state="calculated", '
               + ('input_case_version=2, ' if version == 2 else '')
               + f'baseline={{"input_case_version": {version}}}, computed_at=NOW)\n')
        new = (f'        from backend.stillhere.finance import forecast_finances\n'
               f'        forecast = forecast_finances({name}["finance"]["ledger"],\n'
               f'                    start_date=NOW[:10], time_zone={name}["time_zone"], input_case_version={version})\n'
               f'        {name}["finance"].update(state="calculated", input_case_version={version},\n'
               f'                                  baseline=forecast["baseline"], computed_at=NOW)\n')
        result[path] = once(source, old, new)
    return result


def main():
    chunks = []
    for path, proposed in proposed_files().items():
        current = (ROOT/path).read_text()
        chunks.extend(difflib.unified_diff(current.splitlines(True), proposed.splitlines(True),
                                         fromfile="a/"+path, tofile="b/"+path))
    DESTINATION.write_text("".join(chunks))


if __name__ == "__main__":
    main()
