"""Explicit correction proposals for reported completion; CaseService supplies audit/replay."""

import copy

from .validation import actions, check, fail, instant, owned


def correct_completion(plan, payload, *, occurred_at, received_at, event_id, input_case_version):
    """Return a pending plan after correcting one exact latest completion report.

    Original history is retained. Correction never declares an action ready,
    rewrites a fact, retracts agency confirmation or adjusts financial spending.
    Replay/version authorization belongs to CaseService; divergent reused event
    IDs and missing (including truncated) completion references are rejected here.
    """
    check("PlannerCompletionCorrection", payload)
    check("Id", event_id)
    occurred, received = instant(occurred_at), instant(received_at)
    if occurred > received:
        fail("$.occurred_at", "Completion corrections cannot occur in the future.")
    if type(input_case_version) is not int or input_case_version < 1:
        fail("$.input_case_version", "Expected a positive input case version.")
    mapping = actions(plan)
    action = owned(mapping, payload["action_id"])
    if action["input_case_version"] > input_case_version:
        fail("$.input_case_version", "Completion inputs cannot come from a later case version.")
    if any(report["event_id"] == event_id for a in mapping.values() if a.get("origin") == "recovery_planner" for report in a["history"]):
        fail("$.event_id", "CaseService must resolve event replay before domain correction.")
    if action["status"] != "completed" or not action["history"]:
        fail("$.completion_event_id", "Only an explicitly reported completed action can be corrected.")
    original = action["history"][-1]
    if original["event_id"] != payload["completion_event_id"] or original["status"] != "completed":
        fail("$.completion_event_id", "Correction must reference the latest retained completion report.")
    if occurred < instant(original["occurred_at"]) or received < instant(original["received_at"]):
        fail("$.occurred_at", "Correction timestamps cannot precede the original report.")
    if len(action["history"]) >= 64:
        fail("$.history", "Resolve history capacity through CaseService audit before correction; no report was removed.")
    result = copy.deepcopy(plan)
    action = owned(actions(result), payload["action_id"])
    action["status"] = "blocked" if action["blockers"] else "waiting"
    action["input_freshness"] = "stale"
    action["reason"] = "The household explicitly corrected its completion report; prerequisites require reassessment."
    action["history"].append({"event_id": event_id, "from_status": "completed", "status": action["status"],
                              "reason_code": None, "occurred_at": occurred_at, "received_at": received_at,
                              "provenance": "user_reported", "correction_of": original["event_id"],
                              "correction_reason": payload["reason_code"]})
    # Accepted correction makes every active transitive consumer stale. Reported
    # terminal work is retained even if a historical prerequisite was corrected.
    invalidated = {action["id"]}
    while True:
        added = set()
        for consumer in result["actions"]:
            if consumer.get("origin") != "recovery_planner" or consumer["status"] in ("completed", "skipped"):
                continue
            if any(link["kind"] == "action" and link["target_id"] in invalidated and
                   link["target_rule_id"] == mapping[link["target_id"]]["rule_id"] and
                   link["target_rule_version"] == mapping[link["target_id"]]["rule_version"]
                   for link in consumer.get("dependency_links", [])):
                consumer["input_freshness"] = "stale"
                consumer["status"] = "blocked" if consumer["blockers"] else "waiting"
                added.add(consumer["id"])
        if added <= invalidated:
            break
        invalidated |= added
    result.update(state="pending", version=plan["version"] + 1, pending_input_case_version=input_case_version + 1)
    for field in ("blockers", "questions"):
        result[field] = [item for item in result.get(field, []) if item.get("action_id") != action["id"]]
        result[field] += [{**copy.deepcopy(item), "action_id": action["id"]} for item in action[field]]
    actions(result)
    return result
