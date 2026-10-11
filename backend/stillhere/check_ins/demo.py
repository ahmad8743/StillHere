"""Credential-free synthetic demonstration: python3 -m backend.stillhere.check_ins.demo."""

import copy
import json

from . import Authority, CheckInProcessor, apply_command, empty_state, operator_projection


def run_demo():
    case_id = "case_check_in_synthetic"
    household = Authority(case_id, "household", "household_synthetic",
                          frozenset({"check_in.write", "location.write", "help.write"}), True)
    worker = Authority(case_id, "worker", "worker_synthetic", frozenset({"check_in.process"}))
    operator = Authority(case_id, "operator", "operator_synthetic",
                         frozenset({"follow_up.read", "follow_up.write", "location.read", "needs.read"}))
    state, frames = empty_state(case_id), []
    clock = ["2026-10-11T10:00:00Z"]
    processor = CheckInProcessor(lambda: clock[0])

    def command(label, kind, payload, when, actor=household, reported_at=None):
        nonlocal state
        result = apply_command(state, kind, payload, event_id="event_" + label,
                               reported_at=reported_at or when, received_at=when, caller=actor)
        state = result["state"]
        frames.append({"label": label, **copy.deepcopy(result)})

    command("enroll", "check_in.enroll", {"consent": True, "follow_up_consent": True,
            "due_at": "2026-10-11T11:00:00Z", "time_zone": "America/Chicago", "grace_minutes": 30,
            "channel": "text_simulator", "permitted_need_ids": ["need_shelter"]}, clock[0])
    first = state["check_in"]["current_occurrence_id"]
    command("share", "location.share", {"consent": True, "source": "user_entered",
            "place": "Synthetic community center", "observed_at": clock[0],
            "purpose": "simulated_follow_up", "recipients": "assigned_handler"}, clock[0])
    for label, now in (("reminder", "2026-10-11T11:00:00Z"), ("overdue", "2026-10-11T11:30:00Z"),
                       ("duplicate_tick", "2026-10-11T11:30:00Z")):
        clock[0] = now
        result = processor.process(state, caller=worker)
        state = result["state"]
        frames.append({"label": label, **copy.deepcopy(result)})
    request_id = state["follow_ups"][0]["id"]
    command("acknowledge", "follow_up.acknowledge", {"request_id": request_id}, "2026-10-11T11:31:00Z", operator)
    command("attempt", "follow_up.record", {"request_id": request_id, "kind": "attempt", "simulation": True,
            "channel": "phone_simulator", "result": "no_reply", "unresolved_need_ids": ["need_shelter"],
            "next_action": "Review the next explicit household report."}, "2026-10-11T11:32:00Z", operator)
    frames.append({"label": "offline_pending", "queued_local": {"type": "check_in.reply",
                  "event_id": "event_offline_reply", "occurred_at": "2026-10-11T11:10:00Z",
                  "payload": {"occurrence_id": first, "reply": "okay_for_now"}},
                   "state": copy.deepcopy(state)})
    command("offline_reply", "check_in.reply", {"occurrence_id": first, "reply": "okay_for_now"},
            "2026-10-11T11:40:00Z", reported_at="2026-10-11T11:10:00Z")
    command("outcome", "follow_up.record", {"request_id": request_id, "kind": "outcome", "simulation": True,
            "outcome": "needs_follow_up", "unresolved_need_ids": ["need_shelter"],
            "next_action": "Offer a new check-in time; shelter need remains unresolved."}, "2026-10-11T11:41:00Z", operator)
    command("reschedule", "check_in.reply", {"occurrence_id": first, "reply": "check_later",
            "next_due_at": "2026-10-11T13:00:00Z"}, "2026-10-11T11:42:00Z")
    command("pause", "check_in.pause", {"intent": "pause"}, "2026-10-11T11:43:00Z")
    command("clear", "location.clear", {}, "2026-10-11T11:44:00Z")
    clock[0] = "2026-10-11T14:00:00Z"
    result = processor.process(state, caller=worker)
    state = result["state"]
    frames.append({"label": "paused_tick", **copy.deepcopy(result)})
    frames.append({"label": "operator_view", "projection": operator_projection(state, caller=operator, now=clock[0],
                   relevant_needs=[{"id": "need_shelter", "kind": "shelter", "state": "uncovered", "reported_urgency": "essentials_today"}])})
    return frames


def main():
    frames = run_demo()
    print(json.dumps([{"step": frame["label"], "schedule_status": frame.get("state", {}).get("check_in", {}).get("status"),
                       "effects": [effect["kind"] for effect in frame.get("effects", [])],
                       "queued_local": "queued_local" in frame,
                       "simulation": True} for frame in frames], indent=2))


if __name__ == "__main__":
    main()
