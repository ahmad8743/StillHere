"""Disposable public-source overlay for testing unapplied owner proposals only."""

import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


@contextmanager
def proposed_checkout(*, boundary=False, fixtures=False):
    with tempfile.TemporaryDirectory(prefix="stillhere-extension-proposal-") as directory:
        root = Path(directory)
        for name in ("backend", "contracts"):
            shutil.copytree(ROOT / name, root / name,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".env", ".env.*", "*credentials*"))
        (root / "tests").mkdir()
        (root / "tests/__init__.py").write_text("")
        for name in ("test_agent_extensions.py", "test_agent_extensions_sdk.py"):
            shutil.copyfile(ROOT / "tests" / name, root / "tests" / name)
        if fixtures:
            (root / "docs").mkdir()
            shutil.copyfile(ROOT / "docs/contracts-and-progress.md", root / "docs/contracts-and-progress.md")
            for name in ("test_case_service.py", "test_intake.py", "test_access.py"):
                shutil.copyfile(ROOT / "tests" / name, root / "tests" / name)
        patch_file = Path(__file__).parent / "integration_proposals/shared-wiring.patch"
        result = subprocess.run(["/usr/bin/patch", "--batch", "-p1", "-i", str(patch_file)],
                                cwd=root, capture_output=True, text=True)
        if result.returncode:
            raise AssertionError("Owner proposal no longer applies cleanly; review the shared boundary.")
        if boundary:
            result = subprocess.run(["/usr/bin/patch", "--batch", "-p1", "-i", str(patch_file.with_name("domain-dependencies.patch"))],
                                    cwd=root, capture_output=True, text=True)
            if result.returncode:
                raise AssertionError("Domain dependency proposal requires fresh owner review.")
        if fixtures:
            result = subprocess.run(["/usr/bin/patch", "--batch", "-p1", "-i", str(patch_file.with_name("shared-fixtures.patch"))],
                                    cwd=root, capture_output=True, text=True)
            if result.returncode:
                raise AssertionError("Shared fixture proposal requires fresh owner review.")
        yield root


def run_proposal_test(test, *, boundary=False):
    if os.environ.get("STILLHERE_ISOLATED_PROPOSAL") == "1":
        return False
    with proposed_checkout(boundary=boundary) as root:
        test_id = test.id() if test.id().startswith("tests.") else "tests." + test.id()
        result = subprocess.run([sys.executable, "-W", "error::ResourceWarning", "-m", "unittest", test_id, "-q"],
            cwd=root, capture_output=True, text=True,
            env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1", "STILLHERE_ISOLATED_PROPOSAL": "1"}, timeout=45)
        test.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    return True


NOW = "2026-10-11T06:00:00Z"


def create_case(service):
    token = service.create_session()["session_token"]
    snapshot = service.create_case(token, {"contract_version": "0.1", "event_id": "create",
                                          "time_zone": "America/Chicago"})["case_snapshot"]
    return token, snapshot


def command(snapshot, kind, payload, event="chat"):
    return {"contract_version": "0.1", "case_id": snapshot["case_id"], "event_id": event,
            "expected_case_version": snapshot["case_version"], "occurred_at": NOW,
            "channel": "chat", "type": kind, "payload": payload}


def queue_turn(service, token, snapshot, event="chat", **extra):
    request = command(snapshot, "conversation.message", {"message_id": "user_" + event,
                        "text": "Synthetic explicit report.", **extra}, event)
    result = service.execute(token, request)
    if result["status"] != "applied":
        raise AssertionError("Synthetic turn could not be queued.")
    claim = service.claim_agent_turn(token, snapshot["case_id"], event, 30)
    return claim, request


def context_for(service, token, snapshot, event="chat", **extra):
    import time
    from ..agent.tools import AgentContext
    claim, request = queue_turn(service, token, snapshot, event, **extra)
    return AgentContext(service, token, snapshot["case_id"], event, claim["run_id"],
                        claim["snapshot"]["case_version"], time.monotonic()+30, 32, 48000), request


def cash_source():
    return {"id": "cash", "type": "cash", "currency": "USD", "balance_cents": 30000,
            "accessible": True, "as_of": "2026-10-11T05:00:00Z", "restrictions": [], "reflected_event_ids": []}


def seed_finance(service, token, snapshot):
    result = service.execute(token, command(snapshot, "finance.update", {"operation": "set_money_source", "record": cash_source()}, "seed_cash"))
    if result["status"] != "applied":
        raise AssertionError("Synthetic finance fixture rejected.")
    return result["case_snapshot"]


def seed_plan(service, token, snapshot):
    for key, value in (("document_issuing_state", "CO"), ("credential_lost", True),
                       ("mobility", "no_car"), ("office_transport_available", False), ("internet_access", True)):
        result = service.execute(token, command(snapshot, "fact.correct", {"fact_key": key, "value": value, "observed_at": NOW}, "seed_"+key))
        if result["status"] != "applied":
            raise AssertionError("Synthetic planner fixture rejected.")
        snapshot = result["case_snapshot"]
    context, _ = context_for(service, token, snapshot, "seed_plan")
    result = service.revise_agent_plan(token, snapshot["case_id"], context.event_id, context.run_id,
                        {"program_id": "co_state_id_replacement"}, context.expected_version, context.deadline, 48000)
    if result["status"] != "applied":
        raise AssertionError("Synthetic plan fixture rejected.")
    return service.finish_agent_turn(token, snapshot["case_id"], context.event_id, context.run_id, "Synthetic plan saved.")


def application_arguments(snapshot):
    action = next(item for item in snapshot["plan"]["actions"] if item["path_id"] == "co_id_online_renewal")
    return {"application_id": "application_synthetic", "action_id": action["id"],
            "program_id": action["program_id"], "rule_version": action["rule_version"], "path_id": action["path_id"]}
