"""Case-scoped operator allowlist. No full case, ledger, residence, or chat."""

import copy

from .authorization import authorize
from .contracts import SCHEMA, instant, validate


def operator_projection(state, *, caller, now, relevant_needs=()):
    """Project only consented fields from trusted, case-scoped need records.

    C01 supplies relevant_needs from this same case, never from model arguments.
    Extra need fields are discarded; location also requires location.read and the
    consented recipient policy. assigned_handler restricts it to the current owner.
    """
    authorize(state["case_id"], "operator_projection", caller)
    validate("State", state)
    validate("Timestamp", now)
    relevant_needs = tuple(relevant_needs)
    reviews = []
    for request in state["follow_ups"]:
        if not request["consent"]["active"]:
            continue
        occurrence = next((item for item in state["check_in"]["occurrences"]
                           if item["id"] == request["occurrence_id"]), None)
        consented_ids = set(request["consent"]["permitted_need_ids"])
        needs = []
        if "needs.read" in caller.permissions:
            for need in relevant_needs:
                if need.get("id") not in consented_ids:
                    continue
                permitted = {key: need.get(key, "unknown") for key in ("id", "kind", "state", "reported_urgency")}
                # Unknown or newly expanded shared vocabulary is never copied blindly.
                for key in ("kind", "state", "reported_urgency"):
                    choices = SCHEMA["$defs"]["PermittedNeed"]["properties"][key]["enum"]
                    if permitted[key] not in choices:
                        permitted[key] = "unknown"
                validate("PermittedNeed", permitted)
                if permitted not in needs:
                    needs.append(permitted)
        location = state["shared_location"]
        location_view = None
        owner = request["assignment"]["operator_id"] if request["assignment"] else None
        if location and "location.read" in caller.permissions and location["consent"] is True:
            permitted_recipient = location["recipients"] == "case_handlers" or owner == caller.subject_id
            unexpired = not location.get("expires_at") or instant(now) < instant(location["expires_at"])
            if permitted_recipient and unexpired and instant(now) >= instant(location["received_at"]):
                location_view = {"last_shared_location": copy.deepcopy(location),
                                 "age_seconds": max(0, int((instant(now) - instant(location["observed_at"])).total_seconds())),
                                 "verified_current_destination": False}
        review = {"request_id": request["id"], "trigger": request["trigger"], "status": request["status"],
                  "consent": copy.deepcopy(request["consent"]), "reported_at": request["reported_at"],
                  "received_at": request["received_at"], "condition": "unknown", "message": request["message"],
                  "last_report": copy.deepcopy(state["check_in"]["last_report"]),
                  "occurrence": {"occurrence_id": occurrence["id"],
                                 **{key: occurrence[key] for key in ("status", "due_at", "grace_deadline", "condition")}} if occurrence else None,
                  "attempts": copy.deepcopy((occurrence["attempts"] if occurrence else []) + request["attempts"]),
                  "relevant_needs": needs, "shared_location": location_view,
                  **{key: copy.deepcopy(request[key]) for key in ("assignment", "outcomes", "report_updates", "unresolved_need_ids", "next_action", "next_due_at")},
                  "simulation": True}
        reviews.append(review)
    result = {"case_reference": state["case_id"], "as_of": now, "simulation": True,
              "response_service": "uncommitted_simulation", "reviews": reviews}
    validate("OperatorProjection", result)
    return result
