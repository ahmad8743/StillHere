"""Verify restored SYNTHETIC proof in a separate database using CaseService.

The proof state was created by verify_http.py. Never run against live state.
CaseService alone performs any startup migration or disposable verification write.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.stillhere.service import CaseService, ServiceError


def verify(database, state_file):
    if not __debug__:
        raise RuntimeError("Verification requires assertions enabled")
    if database.resolve() == Path("/var/lib/stillhere/cases.sqlite3") or not database.is_file():
        raise ValueError("Existing separate restored database required")
    state = json.loads(state_file.read_text())
    service = CaseService(database)
    snapshot = service.read_case(state["token"], state["command"]["case_id"])
    assert snapshot["case_version"] == state["version"]
    assert snapshot["facts"]["mobility"]["value"] == "no_car"
    assert service.execute(state["token"], state["command"])["status"] == "already_applied"
    assert service.create_case(state["token"], state["create"])["status"] == "already_applied"
    second = state["second"]
    assert service.read_case(second["token"], second["case_id"])["case_version"] == second["version"]
    try:
        service.read_case(second["token"], snapshot["case_id"])
    except ServiceError as error:
        assert error.status == 404
    else:
        raise AssertionError("Isolation failed")
    assert service.read_case(state["token"], snapshot["case_id"]) == snapshot


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    args = parser.parse_args()
    try:
        verify(args.db, args.state)
    except Exception:
        sys.exit("restore_proof_failed")
    print("restore_isolation_durability_replay_ok")
