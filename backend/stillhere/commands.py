"""Deterministic household commands; storage and authorization stay in CaseService."""

import copy
import hashlib

from .contracts import validate


def user_fact(value, observed_at):
    return {
        "value": value, "state": "unknown" if value is None else "user_reported",
        "observed_at": observed_at, "source_ids": [],
    }


def _apply_intake(snapshot, selections, observed_at):
    for key, value in selections.items():
        if value is None or value == "unsure" or value == [] or value == ["unsure"]:
            value = None
        # The intake field describes reported selections, not an exhaustive list of needs.
        fact_key = "requested_needs" if key == "needs" else key
        snapshot["facts"][fact_key] = user_fact(value, observed_at)

    urgency = snapshot["facts"].get("help_urgency", {}).get("value")
    if urgency not in ("urgent_safety", "essentials_today", "recovery_steps"):
        urgency = "unknown"
    for kind in selections.get("needs") or []:
        if kind == "unsure":
            continue
        existing = next((need for need in snapshot["needs"] if need.get("kind") == kind), None)
        if existing is not None:
            existing["reported_urgency"] = urgency
            if isinstance(existing.get("fact_keys"), list) and "help_urgency" in snapshot["facts"] and "help_urgency" not in existing["fact_keys"]:
                existing["fact_keys"].append("help_urgency")
            continue
        identifier = hashlib.sha256(f"{snapshot['case_id']}\0{kind}".encode()).hexdigest()[:32]
        need = {
            "id": "need_" + identifier, "kind": kind, "reported_urgency": urgency,
            "state": "unknown", "source_ids": [], "fact_keys": ["requested_needs"],
        }
        if "help_urgency" in snapshot["facts"]:
            need["fact_keys"].append("help_urgency")
        validate("IntakeNeed", need)
        snapshot["needs"].append(need)


def with_intake(snapshot, selections, observed_at):
    """Initialize a case without turning its initial intake into a second case version."""
    validate("IntakeSelections", selections)
    updated = copy.deepcopy(snapshot)
    _apply_intake(updated, selections, observed_at)
    validate("CaseSnapshot", updated)
    return updated


def _correct_fact(snapshot, payload, occurred_at):
    snapshot["facts"][payload["fact_key"]] = user_fact(payload["value"], payload["observed_at"])


def assistant_turn_id(case_id, event_id):
    return "turn_" + hashlib.sha256(f"{case_id}\0{event_id}\0assistant".encode()).hexdigest()[:32]


def _conversation_message(snapshot, payload, occurred_at):
    turns = snapshot["conversation"]["turns"]
    turns.append({
        "id": payload["message_id"], "role": "user", "text": payload["text"],
        "created_at": occurred_at, "state": "complete",
    })


def _task_update(snapshot, payload, occurred_at, received_at=None, event_id=None):
    from .planner.tasks import record_task
    record_task(snapshot, payload, occurred_at, received_at, event_id)


COMMAND_HANDLERS = {
    "fact.correct": ("FactCorrectionPayload", _correct_fact),
    "intake.submit": ("IntakeSelections", _apply_intake),
    "conversation.message": ("ConversationMessagePayload", _conversation_message),
    "task.update": ("TaskUpdatePayload", _task_update),
}

# These handlers need trusted session/time and shared transaction context.
# CaseService dispatches them; they never run as free-standing snapshot writes.
SERVICE_COMMANDS = {
    "finance.update": "FinanceUpdatePayload", "scenario.set": "ScenarioSetPayload",
    "application.update": "UpdateApplicationArguments",
    "check_in.enroll": "CheckInEnrollPayload", "check_in.reply": "CheckInReplyPayload",
    "check_in.pause": "CheckInPausePayload", "help.request": "HelpRequestPayload",
    "location.share": "LocationSharePayload", "location.clear": "LocationClearPayload",
    "follow_up.acknowledge": "FollowUpAcknowledgePayload", "follow_up.record": "FollowUpRecordPayload",
}
COMMAND_HANDLERS.update({name: (schema, None) for name, schema in SERVICE_COMMANDS.items()})


def validate_payload(command_type, payload):
    validate(COMMAND_HANDLERS[command_type][0], payload)


def apply_command(snapshot, command, received_at):
    """Apply an already validated command to a copy, preserving the prior audit state."""
    updated = copy.deepcopy(snapshot)
    if command["type"] == "task.update":
        _task_update(updated, command["payload"], command["occurred_at"], received_at, command["event_id"])
    else:
        COMMAND_HANDLERS[command["type"]][1](updated, command["payload"], command["occurred_at"])
    if command["type"] == "conversation.message":
        if "choice_id" in command["payload"]:
            updated["conversation"]["turns"][-1]["choice_id"] = command["payload"]["choice_id"]
        updated["conversation"]["turns"].append({
            "id": assistant_turn_id(command["case_id"], command["event_id"]),
            "event_id": command["event_id"], "role": "assistant", "text": "",
            "created_at": received_at, "state": "queued",
        })
    updated["case_version"] += 1
    updated["updated_at"] = received_at
    changed_inputs = ({command["payload"]["fact_key"]} if command["type"] == "fact.correct"
                      else set(command["payload"]) if command["type"] == "intake.submit" else set())
    resources = updated["resources"]
    search = resources.get("search")
    if search and changed_inputs & {search["query"]["location_scope"] + "_location", "requested_needs", "needs"}:
        search["freshness"] = "stale"
        source_ids = {identifier for item in resources["items"] for identifier in item["source_ids"]}
        for source in updated["sources"]:
            if source.get("id") in source_ids:
                source["freshness"] = "stale"
        if not any(notice.get("code") == "resource_inputs_changed" for notice in resources["notices"]):
            resources["notices"].append({"code": "resource_inputs_changed", "message": "Saved referrals refer to earlier location or need inputs. Retrieve again before using them for the corrected case.", "retryable": False})
    for scope, incident in updated.get("incident_context", {}).items():
        if changed_inputs & {scope + "_location", "crisis_type"}:
            incident["state"] = "stale"
            source_ids = {provider["source"]["id"] for provider in incident["providers"].values()}
            for provider in incident["providers"].values():
                provider["source"]["fresh_until"] = min(provider["source"]["fresh_until"], received_at)
            for source in updated["sources"]:
                if source.get("id") in source_ids:
                    source["fresh_until"] = min(source["fresh_until"], received_at)
    if command["type"] != "conversation.message" and updated["plan"]["state"] != "not_requested":
        updated["plan"]["state"] = "pending"
        updated["plan"]["pending_input_case_version"] = updated["case_version"]
        if command["type"] in ("fact.correct", "intake.submit"):
            for action in updated["plan"]["actions"]:
                if action.get("origin") == "recovery_planner":
                    action["input_freshness"] = "stale"
    if updated["finance"]["state"] == "not_calculated":
        updated["finance"]["input_case_version"] = updated["case_version"]
    elif command["type"] != "conversation.message":
        updated["finance"]["state"] = "pending"
        updated["finance"]["pending_input_case_version"] = updated["case_version"]
    validate("CaseSnapshot", updated)
    return updated
