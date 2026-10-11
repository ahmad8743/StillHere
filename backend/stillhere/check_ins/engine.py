"""Deterministic transitions over a detached, JSON-serializable domain state.

Effects are proposals for CaseService's atomic audit/outbox, never dispatches.
No filesystem/database/provider writes, threads, implicit clock, or auth store.
"""

import copy
import hashlib
from datetime import timedelta

from .authorization import authorize
from .contracts import CheckInError, canonical, instant, timestamp, validate


PAYLOADS = {
    "check_in.enroll": "CheckInEnrollPayload", "check_in.reply": "CheckInReplyPayload",
    "check_in.pause": "CheckInPausePayload", "help.request": "HelpRequestPayload",
    "location.share": "LocationSharePayload", "location.clear": "LocationClearPayload",
    "follow_up.acknowledge": "FollowUpAcknowledgePayload", "follow_up.record": "FollowUpRecordPayload",
}
URGENT_DIRECTION = ("Show official urgent-help resources immediately. This simulated review queue "
                    "has not contacted emergency services and does not mean help is on the way.")


def stable_id(case_id, kind, parent):
    digest = hashlib.sha256(canonical([case_id, kind, parent]).encode()).hexdigest()[:32]
    return kind + "_" + digest


def empty_state(case_id):
    state = {"domain_version": "check-ins.proposal.1", "case_id": case_id,
             "check_in": {"enrolled": False, "status": "not_enrolled", "consent": None,
                          "current_occurrence_id": None, "occurrences": [], "last_report": None},
             "shared_location": None, "follow_ups": [], "processed_events": {},
             "controls": {"check_in": None, "location": None}}
    validate("State", state)
    return state


def _error(code, field, message):
    raise CheckInError(code, field, message)


def _occurrence(state, identifier):
    for occurrence in state["check_in"]["occurrences"]:
        if occurrence["id"] == identifier:
            return occurrence
    _error("not_found", "$.payload.occurrence_id", "Select an occurrence in this case.")


def _request(state, identifier):
    for request in state["follow_ups"]:
        if request["id"] == identifier:
            return request
    _error("not_found", "$.payload.request_id", "Select a review in this case.")


def _future(value, received_at, field):
    if instant(value) <= instant(received_at):
        _error("invalid_schedule", field, "Select an explicit due time after server receipt.")


def _consent(event_id, reported_at, received_at, need_ids):
    return {"active": True, "granted_at": reported_at, "received_at": received_at,
            "event_id": event_id, "permitted_need_ids": sorted(need_ids), "purpose": "simulated_follow_up"}


def _control(state, kind, reported_at):
    previous = state["controls"][kind]
    if previous and instant(reported_at) < instant(previous):
        _error("stale_control", "$.occurred_at", "An older offline control cannot replace newer consent or scheduling intent.")
    state["controls"][kind] = reported_at


def _effect(state, effects, kind, parent, reported_at, received_at, **context):
    effects.append({"id": stable_id(state["case_id"], "effect", [kind, parent]),
                    "kind": kind, "simulation": True, "reported_at": reported_at,
                    "received_at": received_at, **context})


def _result(state, effects, *, changed, duplicate=False):
    result = {"state": state, "effects": effects, "changed": changed, "duplicate": duplicate}
    validate("TransitionResult", result)
    return result


def _schedule(state, event_id, reported_at, received_at, due_at, time_zone, grace_minutes, channel, consent):
    _future(due_at, received_at, "$.payload.due_at")
    try:
        deadline = timestamp(instant(due_at) + timedelta(minutes=grace_minutes))
    except OverflowError:
        _error("invalid_schedule", "$.payload.due_at", "The due time plus grace exceeds the supported timestamp range.")
    check_in = state["check_in"]
    if check_in["current_occurrence_id"]:
        old = _occurrence(state, check_in["current_occurrence_id"])
        if old["status"] in ("scheduled", "due", "reminder_attempted"):
            old["status"] = "canceled"
    occurrence_id = stable_id(state["case_id"], "occurrence", event_id)
    occurrence = {"id": occurrence_id, "schedule_id": stable_id(state["case_id"], "schedule", event_id),
                  "due_at": due_at, "grace_deadline": deadline,
                  "time_zone": time_zone, "grace_minutes": grace_minutes, "channel": channel,
                  "status": "scheduled", "condition": "unknown", "created_at": reported_at,
                  "received_at": received_at, "consent": copy.deepcopy(consent),
                  "reminder_attempt_id": stable_id(state["case_id"], "attempt", [occurrence_id, "reminder"]),
                  "review_request_id": None, "attempts": [], "reports": []}
    check_in["occurrences"].append(occurrence)
    check_in.update(enrolled=True, status="scheduled", consent=copy.deepcopy(consent),
                    current_occurrence_id=occurrence_id)
    return occurrence


def _review(state, effects, parent, trigger, occurrence, consent, reported_at, received_at, message=None):
    # Timer retries/open-review help coalesce. Fresh explicit help after an
    # outcome gets a new unassigned request, preserving the completed review.
    if occurrence and occurrence["review_request_id"]:
        linked = [request for request in state["follow_ups"] if request["occurrence_id"] == occurrence["id"]]
        pending = [request for request in linked if request["status"] != "outcome_recorded"]
        if pending:
            return pending[-1]
        if trigger == "overdue":
            return _request(state, occurrence["review_request_id"])
        identity = [occurrence["id"], "explicit_help", parent]
    else:
        identity = occurrence["id"] if occurrence else parent
    identifier = stable_id(state["case_id"], "review", identity)
    request = {"id": identifier, "trigger": trigger, "occurrence_id": occurrence["id"] if occurrence else None,
               "status": "requested", "condition": "unknown", "reported_at": reported_at,
               "received_at": received_at, "message": message, "consent": copy.deepcopy(consent),
               "assignment": None, "attempts": [], "outcomes": [], "report_updates": [],
               "unresolved_need_ids": copy.deepcopy(consent["permitted_need_ids"]),
               "next_action": "Await simulated operator acknowledgment.", "next_due_at": None, "simulation": True}
    state["follow_ups"].append(request)
    if occurrence:
        occurrence["review_request_id"] = identifier
    _effect(state, effects, "review_requested", identifier, reported_at, received_at, request_id=identifier)
    return request


def apply_command(state, command_type, payload, *, event_id, reported_at, received_at, caller):
    """Return {state, effects, changed, duplicate}; never mutate inputs.

    C01 supplies original command.occurred_at as reported_at and authoritative
    receipt/identity. expected_case_version and durable replay are C01 concerns.
    """
    authorize(state["case_id"], command_type, caller)  # Before private replay lookup.
    validate("State", state)
    validate("Identifier", event_id)
    validate(PAYLOADS[command_type], payload)
    validate("Timestamp", reported_at)
    validate("Timestamp", received_at)
    if instant(reported_at) > instant(received_at):
        _error("invalid_time", "$.occurred_at", "Report time cannot be after receipt.")
    fingerprint = hashlib.sha256(canonical([command_type, payload, reported_at, caller.role, caller.subject_id]).encode()).hexdigest()
    previous = state["processed_events"].get(event_id)
    if previous:
        if previous["fingerprint"] != fingerprint:
            _error("event_reused", "$.event_id", "A changed intent or actor requires a new event ID.")
        return _result(copy.deepcopy(state), [], changed=False, duplicate=True)
    updated, effects = copy.deepcopy(state), []
    handler = _HANDLERS[command_type]
    handler(updated, payload, event_id, reported_at, received_at, caller, effects)
    updated["processed_events"][event_id] = {"fingerprint": fingerprint, "received_at": received_at}
    return _result(updated, effects, changed=True)


def _enroll(state, payload, event_id, reported_at, received_at, caller, effects):
    _control(state, "check_in", reported_at)
    consent = _consent(event_id, reported_at, received_at, payload.get("permitted_need_ids", []))
    occurrence = _schedule(state, event_id, reported_at, received_at, payload["due_at"], payload["time_zone"],
                           payload["grace_minutes"], payload["channel"], consent)
    _effect(state, effects, "schedule_changed", event_id, reported_at, received_at, occurrence_id=occurrence["id"])


def _reply(state, payload, event_id, reported_at, received_at, caller, effects):
    occurrence = _occurrence(state, payload["occurrence_id"])
    if instant(reported_at) < instant(occurrence["created_at"]):
        _error("invalid_time", "$.occurred_at", "A reply cannot predate the agreed occurrence.")
    check_in = state["check_in"]
    next_due = payload.get("next_due_at")
    if payload["reply"] == "check_later" and not next_due:
        _error("invalid_schedule", "$.payload.next_due_at", "Check later requires an explicitly selected next time.")
    if next_due:
        if check_in["current_occurrence_id"] != occurrence["id"] or not check_in["enrolled"]:
            _error("schedule_conflict", "$.payload.next_due_at", "An old or paused occurrence cannot replace the current schedule; enroll explicitly.")
        if occurrence["reports"] and instant(reported_at) < max(instant(report["reported_at"]) for report in occurrence["reports"]):
            _error("stale_control", "$.occurred_at", "An older offline reply cannot reschedule after a newer explicit report.")
        _future(next_due, received_at, "$.payload.next_due_at")
    report = {"id": stable_id(state["case_id"], "report", event_id), "event_id": event_id,
              "occurrence_id": occurrence["id"], "reply": payload["reply"], "reported_at": reported_at,
              "received_at": received_at, "late": instant(received_at) > instant(occurrence["grace_deadline"]) or occurrence["review_request_id"] is not None}
    occurrence["reports"].append(report)
    latest = max(occurrence["reports"], key=lambda r: (instant(r["reported_at"]), instant(r["received_at"]), r["id"]))
    occurrence.update(status="answered", condition=latest["reply"])
    last_report = check_in["last_report"]
    if last_report is None or (instant(report["reported_at"]), instant(report["received_at"]), report["id"]) > (instant(last_report["reported_at"]), instant(last_report["received_at"]), last_report["id"]):
        check_in["last_report"] = copy.deepcopy(report)
    if check_in["current_occurrence_id"] == occurrence["id"] and check_in["enrolled"]:
        check_in["status"] = "answered"
    _effect(state, effects, "report_received", event_id, reported_at, received_at, occurrence_id=occurrence["id"])
    if payload["reply"] == "need_help":
        _review(state, effects, event_id, "need_help", occurrence, occurrence["consent"], reported_at, received_at)
        _effect(state, effects, "urgent_help_required", event_id, reported_at, received_at, direction=URGENT_DIRECTION)
    for request in state["follow_ups"]:
        if request["occurrence_id"] != occurrence["id"]:
            continue
        owner = request["assignment"]["operator_id"] if request["assignment"] else None
        request["report_updates"].append({"id": stable_id(state["case_id"], "update", [event_id, request["id"]]),
                                          "report": copy.deepcopy(report), "notify_operator_id": owner, "simulation": True})
        context = {"request_id": request["id"]}
        if owner:
            context["operator_id"] = owner
        _effect(state, effects, "reviewer_update", [event_id, request["id"]], reported_at, received_at, **context)
    if next_due:
        _control(state, "check_in", reported_at)
        following = _schedule(state, event_id, reported_at, received_at, next_due, occurrence["time_zone"],
                              occurrence["grace_minutes"], occurrence["channel"], check_in["consent"])
        _effect(state, effects, "schedule_changed", event_id, reported_at, received_at, occurrence_id=following["id"])


def _pause(state, payload, event_id, reported_at, received_at, caller, effects):
    _control(state, "check_in", reported_at)
    check_in = state["check_in"]
    status = "paused" if payload["intent"] == "pause" else "canceled"
    check_in.update(enrolled=False, status=status)
    if check_in["consent"]:
        check_in["consent"]["active"] = False
    for occurrence in check_in["occurrences"]:
        if occurrence["status"] in ("scheduled", "due", "reminder_attempted"):
            occurrence["status"] = status
    _effect(state, effects, "schedule_paused", event_id, reported_at, received_at)


def _help(state, payload, event_id, reported_at, received_at, caller, effects):
    occurrence = _occurrence(state, payload["occurrence_id"]) if payload.get("occurrence_id") else None
    consent = _consent(event_id, reported_at, received_at, payload.get("permitted_need_ids", []))
    request = _review(state, effects, event_id, "help_request", occurrence, consent, reported_at, received_at, payload["message"])
    # A new explicit help request may add volunteered context, preserving owner/outcome.
    request["message"] = payload["message"]
    request["consent"]["permitted_need_ids"] = sorted(set(request["consent"]["permitted_need_ids"]) | set(consent["permitted_need_ids"]))
    if request["assignment"]:
        _effect(state, effects, "reviewer_update", event_id, reported_at, received_at,
                request_id=request["id"], operator_id=request["assignment"]["operator_id"])
    _effect(state, effects, "urgent_help_required", event_id, reported_at, received_at, direction=URGENT_DIRECTION)


def _location_share(state, payload, event_id, reported_at, received_at, caller, effects):
    _control(state, "location", reported_at)
    if instant(payload["observed_at"]) > instant(reported_at):
        _error("invalid_time", "$.payload.observed_at", "Observation cannot be after the sharing report.")
    coordinates = "latitude" in payload and "longitude" in payload
    if ("latitude" in payload) != ("longitude" in payload):
        _error("invalid_location", "$.payload", "Supply both coordinates together.")
    if payload["source"] == "device_fix" and not coordinates:
        _error("invalid_location", "$.payload", "A one-time device fix needs coordinates.")
    if payload["source"] == "user_entered" and not payload.get("place"):
        _error("invalid_location", "$.payload.place", "An entered location needs a place.")
    if "accuracy_meters" in payload and not coordinates:
        _error("invalid_location", "$.payload.accuracy_meters", "Accuracy applies to coordinates.")
    if payload.get("expires_at"):
        _future(payload["expires_at"], received_at, "$.payload.expires_at")
    state["shared_location"] = {"id": stable_id(state["case_id"], "location", event_id),
                                **copy.deepcopy(payload), "reported_at": reported_at, "received_at": received_at}
    _effect(state, effects, "location_shared", event_id, reported_at, received_at)


def _location_clear(state, payload, event_id, reported_at, received_at, caller, effects):
    _control(state, "location", reported_at)
    state["shared_location"] = None  # No historical location copies in requests or replay records.
    _effect(state, effects, "location_cleared", event_id, reported_at, received_at)


def _acknowledge(state, payload, event_id, reported_at, received_at, caller, effects):
    request = _request(state, payload["request_id"])
    if request["assignment"]:
        if request["assignment"]["operator_id"] != caller.subject_id:
            _error("already_assigned", "$.payload.request_id", "This review has an acknowledged owner.")
        return  # Same owner accepting again is harmless, with no new assignment effect.
    if instant(reported_at) < instant(request["received_at"]):
        _error("invalid_time", "$.occurred_at", "Acknowledgment cannot predate review receipt.")
    request.update(status="assigned_acknowledged", assignment={"operator_id": caller.subject_id,
                   "acknowledged_at": reported_at, "received_at": received_at},
                   next_action="Review context and record a simulated attempt or outcome.")
    _effect(state, effects, "assignment_acknowledged", request["id"], reported_at, received_at,
            request_id=request["id"], operator_id=caller.subject_id)


def _record(state, payload, event_id, reported_at, received_at, caller, effects):
    request = _request(state, payload["request_id"])
    if not request["assignment"] or request["assignment"]["operator_id"] != caller.subject_id:
        _error("assignment_required", "$.payload.request_id", "Only the acknowledged authenticated owner can record follow-up.")
    if instant(reported_at) < instant(request["assignment"]["acknowledged_at"]):
        _error("invalid_time", "$.occurred_at", "An operator record cannot predate acknowledgment.")
    previous_records = request["attempts"] + request["outcomes"]
    if previous_records and instant(reported_at) < max(instant(record["reported_at"]) for record in previous_records):
        _error("stale_operator_record", "$.occurred_at", "An older operator record cannot overwrite newer review work.")
    if not set(payload["unresolved_need_ids"]) <= set(request["consent"]["permitted_need_ids"]):
        _error("consent_required", "$.payload.unresolved_need_ids", "Use only need IDs permitted for this review.")
    if payload.get("next_due_at"):
        _future(payload["next_due_at"], received_at, "$.payload.next_due_at")
    if payload["kind"] == "attempt":
        if request["status"] == "outcome_recorded":
            _error("review_complete", "$.payload.request_id", "An outcome-recorded review cannot resume contact implicitly.")
        attempt = {"id": stable_id(state["case_id"], "attempt", event_id), "kind": "operator_contact",
                   "channel": payload["channel"], "result": payload["result"], "simulation": True,
                   "scheduled_at": reported_at, "reported_at": reported_at, "received_at": received_at,
                   "operator_id": caller.subject_id}
        request["attempts"].append(attempt)
        request["status"] = "contact_attempted"
        _effect(state, effects, "contact_simulated", attempt["id"], reported_at, received_at,
                request_id=request["id"], operator_id=caller.subject_id)
    else:
        outcome = {"id": stable_id(state["case_id"], "outcome", event_id), "outcome": payload["outcome"],
                   "operator_id": caller.subject_id, "reported_at": reported_at, "received_at": received_at, "simulation": True}
        request["outcomes"].append(outcome)
        request["status"] = "outcome_recorded"
        _effect(state, effects, "outcome_recorded", outcome["id"], reported_at, received_at,
                request_id=request["id"], operator_id=caller.subject_id)
    request.update(unresolved_need_ids=sorted(payload["unresolved_need_ids"]),
                   next_action=payload["next_action"], next_due_at=payload.get("next_due_at"))


_HANDLERS = {"check_in.enroll": _enroll, "check_in.reply": _reply, "check_in.pause": _pause,
             "help.request": _help, "location.share": _location_share, "location.clear": _location_clear,
             "follow_up.acknowledge": _acknowledge, "follow_up.record": _record}


def process_due(state, *, now, caller):
    """One due reminder and one grace-expiry review; restart/retry safe on committed state.

    Only the current consented occurrence is eligible. A delayed tick catches up
    both transitions, with actual processing time distinct from agreed deadlines.
    """
    authorize(state["case_id"], "process_due", caller)
    validate("State", state)
    validate("Timestamp", now)
    updated, effects = copy.deepcopy(state), []
    check_in = updated["check_in"]
    if not check_in["enrolled"] or not check_in["consent"] or not check_in["consent"]["active"]:
        return _result(updated, [], changed=False)
    occurrence = _occurrence(updated, check_in["current_occurrence_id"])
    if occurrence["status"] in ("answered", "paused", "canceled") or instant(now) < instant(occurrence["due_at"]):
        return _result(updated, [], changed=False)
    if not occurrence["attempts"]:
        occurrence["attempts"].append({"id": occurrence["reminder_attempt_id"], "kind": "reminder",
                                       "channel": occurrence["channel"], "result": "simulated", "simulation": True,
                                       "scheduled_at": occurrence["due_at"], "reported_at": now, "received_at": now})
        occurrence["status"] = "reminder_attempted"
        _effect(updated, effects, "reminder_simulated", occurrence["reminder_attempt_id"], now, now, occurrence_id=occurrence["id"])
    if instant(now) >= instant(occurrence["grace_deadline"]) and occurrence["status"] != "overdue":
        occurrence.update(status="overdue", condition="unknown")
        _review(updated, effects, occurrence["id"], "overdue", occurrence, occurrence["consent"], occurrence["grace_deadline"], now)
    check_in["status"] = occurrence["status"]
    return _result(updated, effects, changed=updated != state)


class CheckInProcessor:
    """Inject a callable UTC clock; the integrator loads/commits/registers the worker."""

    def __init__(self, clock):
        self.clock = clock

    def process(self, state, *, caller):
        return process_due(state, now=self.clock(), caller=caller)
