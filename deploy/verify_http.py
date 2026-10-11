"""Explicit operator smoke against synthetic households; never print tokens or cases."""
import argparse
import json
import os
from pathlib import Path
import secrets
import sys
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, ProxyHandler, HTTPRedirectHandler, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        # Never forward a bearer token to another origin or downgrade to HTTP.
        return None


def call(base, path, body=None, token=None):
    headers = {"X-Contract-Version": "0.1", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request(base + path, data=None if body is None else json.dumps(body).encode(), headers=headers)
    try:
        response = build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=15)
    except HTTPError as error:
        response = error
    with response:
        return response.status, json.loads(response.read(1024 * 1024))


def validate_origin(base):
    if not __debug__:
        raise RuntimeError("Verification requires assertions enabled")
    parsed = urlsplit(base)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise ValueError("Use an origin without user information")
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname == "127.0.0.1"):
        raise ValueError("TLS is required outside loopback")
    return base.rstrip("/")


def verify(base, state_file, resume=False):
    base = validate_origin(base)
    status, health = call(base, "/health")
    assert status == 200 and health["status"] == "ok" and health["contract_version"] == "0.1"
    if resume:
        state = json.loads(state_file.read_text())
        assert state["origin"] == base
    else:
        assert not state_file.exists()
        status, household = call(base, "/v1/sessions", {"contract_version": "0.1"})
        assert status == 201
        token = household["session_token"]
        event = "deploy_" + secrets.token_hex(12)
        create = {"contract_version": "0.1", "event_id": event, "time_zone": "America/Chicago"}
        status, result = call(base, "/v1/cases", create, token)
        assert status == 200 and result["status"] == "applied"
        snapshot = result["case_snapshot"]
        command = {"contract_version": "0.1", "case_id": snapshot["case_id"], "event_id": event + "_correct",
                   "expected_case_version": snapshot["case_version"], "occurred_at": "2026-10-11T12:00:00Z",
                   "channel": "dashboard", "type": "fact.correct",
                   "payload": {"fact_key": "mobility", "value": "no_car", "observed_at": "2026-10-11T12:00:00Z"}}
        status, result = call(base, "/v1/commands", command, token)
        assert status == 200 and result["status"] == "applied"
        state = {"origin": base, "token": token, "create": create, "command": command, "version": result["case_snapshot"]["case_version"]}
        status, second = call(base, "/v1/sessions", {"contract_version": "0.1"})
        assert status == 201
        second_create = dict(create, event_id=event + "_second")
        status, second_result = call(base, "/v1/cases", second_create, second["session_token"])
        assert status == 200 and second_result["status"] == "applied"
        state["second"] = {"token": second["session_token"], "create": second_create,
                           "case_id": second_result["case_snapshot"]["case_id"], "version": 1}
        descriptor = os.open(state_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as output:
            json.dump(state, output)
    case_id = state["command"]["case_id"]
    status, snapshot = call(base, "/v1/cases/" + case_id, token=state["token"])
    assert status == 200 and snapshot["case_version"] == state["version"]
    assert snapshot["facts"]["mobility"]["value"] == "no_car"
    status, replay = call(base, "/v1/commands", state["command"], state["token"])
    assert status == 200 and replay["status"] == "already_applied"
    assert replay["case_snapshot"]["case_version"] == state["version"]
    status, created = call(base, "/v1/cases", state["create"], state["token"])
    assert status == 200 and created["case_snapshot"]["case_id"] == case_id
    assert replay["applied_case_version"] == state["version"]
    second = state["second"]
    outsider = second["token"]
    status, second_snapshot = call(base, "/v1/cases/" + second["case_id"], token=outsider)
    assert status == 200 and second_snapshot["case_version"] == second["version"]
    status, second_replay = call(base, "/v1/cases", second["create"], outsider)
    assert status == 200 and second_replay["status"] == "already_applied"
    assert second_replay["case_snapshot"] == second_snapshot
    status, existing = call(base, "/v1/cases/" + case_id, token=outsider)
    missing_status, missing = call(base, "/v1/cases/nonexistent_deploy_case", token=outsider)
    assert status == missing_status == 404 and existing == missing
    status, _ = call(base, "/v1/commands", state["command"], outsider)
    assert status == 404
    status, _ = call(base, "/v1/cases/" + second["case_id"], token=state["token"])
    assert status == 404
    status, unchanged = call(base, "/v1/cases/" + case_id, token=state["token"])
    assert status == 200 and unchanged == snapshot
    status, _ = call(base, "/v1/cases/" + case_id)
    assert status == 401
    for candidate_token in (None, state["token"]):
        status, _ = call(base, "/v1/operator/queue", token=candidate_token)
        assert status == 401
    forbidden = dict(state["command"], event_id="deploy_" + secrets.token_hex(12), channel="operator", expected_case_version=state["version"])
    status, _ = call(base, "/v1/commands", forbidden, state["token"])
    assert status == 403


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--state", type=Path, required=True, help="Private disposable SYNTHETIC test state; contains synthetic bearer token")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    try:
        verify(args.base, args.state, args.resume)
    except Exception:
        sys.exit("deployed_verification_failed")
    print("deployed_verification_ok")
