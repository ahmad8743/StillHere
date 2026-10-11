"""Pure projection of validated evaluations into a bounded, versioned plan."""

import copy
import hashlib

from ..contracts import InvalidInput, validate

ORIGIN = "recovery_planner"
TERMINAL = ("completed", "skipped")


def action_id(program_id, path_id):
    return "action_" + hashlib.sha256(f"{program_id}\0{path_id}".encode()).hexdigest()[:32]


def revise_plan(previous, evaluated, now, event_id, input_fact_fingerprint):
    """Merge one program's current paths; preserve unrelated and completed work."""
    validate("RecoveryOptionResult", evaluated)
    if evaluated["state"] != "available":
        raise InvalidInput("$.plan", "Plan revision requires a current, unambiguous published reference.")
    query = evaluated["query"]
    program_id = query["program_id"]
    old = {action["id"]: action for action in previous["actions"]}
    if len(old) != len(previous["actions"]):
        raise InvalidInput("$.plan.actions", "Saved action identities must be unique.")
    for action in previous["actions"]:
        if action.get("origin") == ORIGIN:
            validate("RecoveryPlanAction", action)
    current_ids = {action_id(program_id, option["path_id"]) for option in evaluated["options"]}
    actions = []
    for action in previous["actions"]:
        if action.get("origin") != ORIGIN or action.get("program_id") != program_id:
            retained = copy.deepcopy(action)
            if action.get("origin") == ORIGIN and (action["input_fact_fingerprint"] != input_fact_fingerprint
                                                   or action["input_catalog_version"] != evaluated["catalog_version"]):
                retained["input_freshness"] = "stale"
            actions.append(retained)
        elif action["id"] not in current_ids:
            retained = copy.deepcopy(action)
            retained["is_current"] = False
            retained["input_freshness"] = "stale"
            if retained["status"] not in TERMINAL:
                retained["status"] = "waiting"
                retained["reason"] = "This path is absent from the current published reference; confirm before continuing."
            actions.append(retained)
    for option in evaluated["options"]:
        identifier = action_id(program_id, option["path_id"])
        prior = old.get(identifier)
        if prior and prior.get("origin") != ORIGIN:
            raise InvalidInput("$.plan.actions", "A planner action cannot replace an unrelated record.")
        if prior and prior["status"] == "completed":
            retained = copy.deepcopy(prior)
            retained["is_current"] = prior["rule_version"] == option["rule_version"]
            if prior["input_fact_fingerprint"] != input_fact_fingerprint or not retained["is_current"]:
                retained["input_freshness"] = "stale"
            actions.append(retained)
            continue
        action = {"id": identifier, "origin": ORIGIN, "program_id": program_id,
                  "rule_id": option["rule_id"], "rule_version": option["rule_version"], "path_id": option["path_id"],
                  "title": option["title"], "purpose": "Review this published recovery route and resolve its prerequisites.",
                  "status": "blocked" if option["status"] == "blocked" else "ready" if option["status"] == "feasible" else "waiting",
                  "execution_mode": option["execution_mode"], "official_url": option["official_url"],
                  "requirements": copy.deepcopy(option["requirements"]), "constraints": copy.deepcopy(option["constraints"]),
                  "costs": copy.deepcopy(option["costs"]), "deadline": None, "source_ids": list(option["source_ids"]),
                  "source_records": [copy.deepcopy(source) for source in evaluated["sources"] if source["id"] in option["source_ids"]],
                  "reason": "Required conditions are unmet." if option["status"] == "blocked" else "Partial policy, agency confirmations and unknown costs require clarification.",
                  "blockers": copy.deepcopy(option["blockers"]), "questions": copy.deepcopy(option["questions"]),
                  "alternative_ids": [action_id(program_id, other["path_id"]) for other in evaluated["options"] if other["id"] in option["alternative_option_ids"]],
                  "input_case_version": query["input_case_version"], "is_current": True,
                  "input_fact_fingerprint": input_fact_fingerprint, "input_catalog_version": evaluated["catalog_version"],
                  "input_freshness": "current",
                  "history": copy.deepcopy(prior.get("history", [])) if prior else [],
                  "inability_reason": prior.get("inability_reason") if prior else None}
        if prior and prior["status"] == "skipped":
            action["status"] = "skipped"
            action["reason"] = "The household reported skipping this route; revision preserves that decision."
        if action["inability_reason"] and action["status"] not in TERMINAL:
            apply_inability(action, action["inability_reason"])
        validate("RecoveryPlanAction", action)
        actions.append(action)
    if len(actions) > 32:
        raise InvalidInput("$.plan.actions", "The bounded plan supports at most 32 retained actions; no work was removed.")
    revision = {"event_id": event_id, "received_at": now, "input_case_version": query["input_case_version"],
                "program_id": program_id, "reason": "published_requirements_reassessed"}
    plan = {**copy.deepcopy(previous), "state": "provisional", "version": previous["version"] + 1,
            "actions": actions, "blockers": copy.deepcopy(evaluated["blockers"]), "questions": copy.deepcopy(evaluated["questions"]),
            "evaluation_query": copy.deepcopy(query), "catalog_version": evaluated["catalog_version"],
            "input_case_version": query["input_case_version"], "computed_at": now,
            "household_eligibility": "unknown", "revisions": (copy.deepcopy(previous.get("revisions", [])) + [revision])[-32:]}
    plan.pop("pending_input_case_version", None)
    if any(action.get("origin") == ORIGIN and action["status"] not in TERMINAL
           and action["input_freshness"] == "stale" for action in actions):
        plan.update(state="pending", pending_input_case_version=query["input_case_version"] + 1)
    for field in ("blockers", "questions"):
        plan[field] += [{**copy.deepcopy(item), "action_id": action["id"]}
                        for action in actions if action.get("origin") == ORIGIN and action["status"] not in TERMINAL
                        for item in action[field]]
    return plan


def apply_inability(action, reason):
    """A task report changes this route only; it never asserts a household fact."""
    action["inability_reason"] = reason
    action["blockers"] = [item for item in action["blockers"] if item["code"] != "task_inability_reported"]
    action["questions"] = [item for item in action["questions"] if item["code"] != "task_access_unresolved"]
    action["status"] = "blocked" if action["blockers"] else "waiting"
    if reason in ("no_car", "other"):
        if action["status"] != "blocked":
            action["status"] = "waiting"
        action["questions"].append({"node_id": None, "fact_key": None, "code": "task_access_unresolved",
                                    "message": "Clarify this reported inability and available alternatives; no car alone does not rule out other transport.", "source_ids": []})
    else:
        action["status"] = "blocked"
        action["blockers"].append({"node_id": None, "fact_key": None, "code": "task_inability_reported",
                                  "message": "Household-reported inability: " + reason + ". Clarify or select a supported alternative.", "source_ids": []})
    action["reason"] = "This route needs reassessment after a household-reported inability; no facts, costs or eligibility were inferred."
