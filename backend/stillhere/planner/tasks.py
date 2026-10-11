"""Explicit household task reports; no inference of facts, money or eligibility."""

import copy

from ..contracts import InvalidInput, validate
from .plans import ORIGIN, TERMINAL, apply_inability
from ..knowledge.rules import _instant


def record_task(snapshot, payload, occurred_at, received_at, event_id):
    validate("TaskUpdatePayload", payload)
    if _instant(occurred_at) > _instant(received_at):
        raise InvalidInput("$.occurred_at", "A task report cannot claim future completion or inability as a current report.")
    action = next((action for action in snapshot["plan"]["actions"] if action.get("id") == payload["action_id"]), None)
    if action is None or action.get("origin") != ORIGIN:
        raise InvalidInput("$.payload.action_id", "Select a saved planner action from this case.")
    validate("RecoveryPlanAction", action)
    if action["status"] == "completed" and payload.get("status") != "completed":
        raise InvalidInput("$.payload.status", "Completed work is preserved; correcting completion needs a separate future correction workflow.")
    before = action["status"]
    reason = payload.get("inability_reason")
    if "inability_reason" in payload:
        if reason in ("no_car", "transport_unavailable", "appointment_unavailable") and action["execution_mode"] != "in_person":
            raise InvalidInput("$.payload.inability_reason", "This access reason applies to an in-person action.")
        if reason == "no_internet" and action["execution_mode"] != "online":
            raise InvalidInput("$.payload.inability_reason", "This access reason applies to an online action.")
        if reason is not None:
            apply_inability(action, reason)
        else:
            action["inability_reason"] = None
            action["blockers"] = [item for item in action["blockers"] if item["code"] != "task_inability_reported"]
            action["questions"] = [item for item in action["questions"] if item["code"] != "task_access_unresolved"]
            action["status"] = "blocked" if action["blockers"] else "waiting"
            action["reason"] = "The household withdrew/resolved its inability report; remaining requirements still need reassessment."
    else:
        action["status"] = payload["status"]
        action["inability_reason"] = None
        action["reason"] = "The household reported this route " + payload["status"] + "; this is not agency verification or an eligibility decision."
    history = {"event_id": event_id, "from_status": before, "status": action["status"], "reason_code": reason,
               "occurred_at": occurred_at, "received_at": received_at, "provenance": "user_reported"}
    action["history"] = (action["history"] + [history])[-64:]
    action["input_freshness"] = "stale"
    validate("RecoveryPlanAction", action)
    plan = snapshot["plan"]
    plan["version"] += 1
    # Reassess this route immediately using its explicit report. All other
    # alternatives keep their own conditions and availability unanswered.
    for field in ("blockers", "questions"):
        plan[field] = [item for item in plan[field] if item.get("action_id") != action["id"]]
        if action["status"] not in TERMINAL:
            plan[field] += [{**copy.deepcopy(item), "action_id": action["id"]} for item in action[field]]
