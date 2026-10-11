"""Explicit simulated household probe; proves progress and stable duplicate-free effects.

Use arm BEFORE stopping/killing the worker and wait AFTER its independent restart.
State contains disposable synthetic bearer tokens; never print it.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import secrets
import sys
import time

from verify_http import call, validate_origin


def save(path, state):
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(state, stream)


def arm(base, state_file, due_seconds=60):
    base = validate_origin(base)
    status, household = call(base, "/v1/sessions", {"contract_version": "0.1"})
    assert status == 201
    token = household["session_token"]
    event = "deploy_worker_" + secrets.token_hex(12)
    status, result = call(base, "/v1/cases", {"contract_version": "0.1", "event_id": event, "time_zone": "America/Chicago"}, token)
    assert status == 200 and result["status"] == "applied"
    now = datetime.now(timezone.utc)
    due = now + timedelta(seconds=due_seconds)
    stamp = lambda instant: instant.isoformat(timespec="seconds").replace("+00:00", "Z")
    snapshot = result["case_snapshot"]
    command = {"contract_version": "0.1", "case_id": snapshot["case_id"], "event_id": event + "_enroll",
               "expected_case_version": snapshot["case_version"], "occurred_at": stamp(now), "channel": "dashboard",
               "type": "check_in.enroll", "payload": {"consent": True, "follow_up_consent": True,
               "due_at": stamp(due), "time_zone": "America/Chicago", "grace_minutes": 0, "channel": "in_app"}}
    status, result = call(base, "/v1/commands", command, token)
    assert status == 200 and result["status"] == "applied"
    save(state_file, {"origin": base, "token": token, "command": command,
                      "due_epoch": due.timestamp(), "enrollment_version": result["applied_case_version"]})


def effects(snapshot):
    attempts, reviews = snapshot["check_in"]["attempts"], snapshot["follow_ups"]
    assert len(attempts) == len(reviews) == 1
    assert attempts[0]["simulation"] is True and attempts[0]["result"] == "simulated"
    assert reviews[0]["simulation"] is True and reviews[0]["assignment"] is None
    return {"attempts": attempts, "reviews": reviews, "version": snapshot["case_version"]}


def verify(base, state_file, wait_seconds=150, stable_seconds=35):
    base = validate_origin(base)
    state = json.loads(state_file.read_text())
    assert state["origin"] == base
    deadline = time.monotonic() + wait_seconds
    while True:
        status, snapshot = call(base, "/v1/cases/" + state["command"]["case_id"], token=state["token"])
        assert status == 200
        if snapshot["follow_ups"]:
            observed = effects(snapshot)
            assert observed["version"] > state["enrollment_version"]
            break
        assert time.monotonic() < deadline, "Worker progress deadline"
        time.sleep(1)
    if "observed" in state:
        assert observed == state["observed"]
    # Observe at least two default 15s polling intervals, with no extra writes.
    end = time.monotonic() + stable_seconds
    while time.monotonic() < end:
        time.sleep(1)
        status, snapshot = call(base, "/v1/cases/" + state["command"]["case_id"], token=state["token"])
        assert status == 200 and effects(snapshot) == observed
    status, replay = call(base, "/v1/commands", state["command"], state["token"])
    assert status == 200 and replay["status"] == "already_applied"
    assert replay["applied_case_version"] == state["enrollment_version"]
    assert effects(replay["case_snapshot"]) == observed
    state["observed"] = observed
    pending = state_file.with_name(state_file.name + ".next")
    save(pending, state)
    os.replace(pending, state_file)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("arm", "wait"))
    parser.add_argument("--base", required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--due-seconds", type=int, default=60)
    args = parser.parse_args()
    try:
        if args.operation == "arm":
            if not 30 <= args.due_seconds <= 3600:
                raise ValueError("Bounded future due time required")
            arm(args.base, args.state, args.due_seconds)
        else:
            verify(args.base, args.state)
    except Exception:
        sys.exit("worker_probe_failed")
    print("worker_probe_armed" if args.operation == "arm" else "worker_progress_replay_ok")
