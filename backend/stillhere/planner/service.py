"""C05 CaseService extension: recompute, authorize and atomically save a plan."""

import time

from ..contracts import InvalidInput, canonical_json, validate
from ..knowledge.rules import ProgramRuleStore, build_query, validate_catalog
from .evaluator import evaluate_options
from .plans import ORIGIN, revise_plan
from .summaries import mutation_summary


class PlannerServiceMixin:
    def revise_agent_plan(self, token, case_id, parent_event_id, run_id, arguments, expected_version,
                          deadline, max_result_chars=48000):
        from ..service import ServiceError
        import sqlite3
        now = self.clock()
        child_id = "agent_tool_" + self._fingerprint([case_id, parent_event_id, "plan.revise", arguments])[:48]
        try:
            validate("ReviseRecoveryPlanToolArguments", arguments)
            with self._transaction() as connection:
                now = self.clock()
                owner = self._session(connection, token)
                snapshot = self._snapshot(connection, owner, case_id)
                self._active_run(connection, case_id, parent_event_id, run_id, now)
                if time.monotonic() >= deadline:
                    raise ServiceError(409, "agent_timeout", "Late plan revisions cannot be saved.")
                # Only domain inputs influence replay identity. Our own case/plan
                # version increment and chat transitions cannot create another effect.
                tasks = [{key: action.get(key) for key in ("id", "status", "inability_reason")}
                         for action in snapshot["plan"]["actions"] if action.get("origin") == ORIGIN
                         and (action["status"] in ("completed", "skipped") or action.get("inability_reason") or action.get("history"))]
                try:
                    catalog = self.read_program_catalog()
                    validate_catalog(catalog)
                except (OSError, ValueError, TypeError, RecursionError):
                    return self._result(child_id, "unavailable", now, snapshot, issue={"code": "plan_rules_unresolved",
                        "message": "Published rules could not be read or validated; the previous plan is retained.", "retryable": True})
                identity = [arguments, snapshot["facts"], tasks, catalog["version"]]
                child_id = "agent_tool_" + self._fingerprint([case_id, parent_event_id, "plan.revise", identity])[:48]
                existing = connection.execute("SELECT applied_version FROM events WHERE case_id=? AND event_id=?", (case_id, child_id)).fetchone()
                if existing:
                    return self._result(child_id, "already_applied", now, snapshot, existing["applied_version"])
                if expected_version != snapshot["case_version"]:
                    return self._result(child_id, "conflict", now, snapshot, issue={"code": "version_conflict",
                        "message": "Case inputs changed before plan revision; reconcile before another write.", "retryable": False})
                store = ProgramRuleStore(loader=lambda: catalog, version_loader=self.read_program_version)
                evaluated = evaluate_options(snapshot, store.lookup(build_query(snapshot, arguments, now), deadline))
                if evaluated["state"] != "available":
                    return self._result(child_id, "unavailable" if evaluated["state"] == "unavailable" else "needs_clarification", now, snapshot,
                        issue={"code": "plan_rules_unresolved", "message": "Plan revision needs a current, unambiguous published rule reference; the previous plan is retained.", "retryable": evaluated["state"] == "unavailable"})
                before = canonical_json(snapshot)
                plan = revise_plan(snapshot["plan"], evaluated, now, child_id, self._fingerprint(snapshot["facts"]))
                snapshot["plan"] = plan
                # Pinned source records inside each action retain historical attribution.
                new_ids = {source["id"] for source in evaluated["sources"]}
                snapshot["sources"] = [source for source in snapshot["sources"] if source.get("id") not in new_ids] + evaluated["sources"]
                snapshot["case_version"] += 1
                snapshot["updated_at"] = now
                if snapshot["finance"]["state"] == "not_calculated":
                    snapshot["finance"]["input_case_version"] = snapshot["case_version"]
                else:
                    snapshot["finance"].update(state="pending", pending_input_case_version=snapshot["case_version"])
                validate("CaseSnapshot", snapshot)
                result = self._result(child_id, "applied", now, snapshot, snapshot["case_version"])
                if len(canonical_json(mutation_summary(result))) > max_result_chars:
                    raise ServiceError(400, "agent_context_limit", "The revised case exceeds the tool result limit; no plan was saved.")
                self._active_run(connection, case_id, parent_event_id, run_id, self.clock())
                if time.monotonic() >= deadline:
                    raise ServiceError(409, "agent_timeout", "Late plan revisions cannot be saved.")
                transition = {"type": "plan.revise", "parent_event_id": parent_event_id, "arguments": arguments,
                              "input_case_version": evaluated["query"]["input_case_version"]}
                connection.execute("UPDATE cases SET snapshot_json=? WHERE case_id=?", (canonical_json(snapshot), case_id))
                connection.execute("INSERT INTO events (case_id,event_id,fingerprint,command_json,first_received_at,applied_received_at,applied_version,before_case_json) VALUES (?,?,?,?,?,?,?,?)",
                    (case_id, child_id, self._fingerprint(identity), canonical_json(transition), now, now, snapshot["case_version"], before))
                return result
        except TimeoutError:
            return self._failed(child_id, now, ServiceError(409, "agent_timeout", "Plan revision reached the agent deadline."))
        except (InvalidInput, ServiceError, sqlite3.Error) as error:
            return self._failed(child_id, now, error)
