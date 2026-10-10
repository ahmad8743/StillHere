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


COMMAND_HANDLERS = {
    "fact.correct": ("FactCorrectionPayload", _correct_fact),
    "intake.submit": ("IntakeSelections", _apply_intake),
}


def validate_payload(command_type, payload):
    validate(COMMAND_HANDLERS[command_type][0], payload)


def apply_command(snapshot, command, received_at):
    """Apply an already validated command to a copy, preserving the prior audit state."""
    updated = copy.deepcopy(snapshot)
    COMMAND_HANDLERS[command["type"]][1](updated, command["payload"], command["occurred_at"])
    updated["case_version"] += 1
    updated["updated_at"] = received_at
    if updated["plan"]["state"] != "not_requested":
        updated["plan"]["state"] = "pending"
        updated["plan"]["pending_input_case_version"] = updated["case_version"]
    if updated["finance"]["state"] == "not_calculated":
        updated["finance"]["input_case_version"] = updated["case_version"]
    else:
        updated["finance"]["state"] = "pending"
        updated["finance"]["pending_input_case_version"] = updated["case_version"]
    validate("CaseSnapshot", updated)
    return updated
