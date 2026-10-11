"""Run independent acceptance evidence groups and retain safe machine-readable results.

Default runs ALL groups, including unmet gates and real HTTP. Nonzero means
acceptance is not established. No skips/expected failures count as verification.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import unittest

GROUPS = {
    "transactions": ("FamilyJourneyTests", "TransactionTests", "FinanceIntegrityTests", "CheckInOperatorTests", "OutputAndBudgetTests", "SourceAcceptanceTests"),
    "proposals": ("ProposalBoundaryTests",),
    "gates": ("RequiredIntegrationGates",),
    "offline-handler": ("OfflineHandlerTests",),
    "http": ("RealHTTPTests",),
}


class EvidenceResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.records.append({"test": test.id(), "status": "verified"})

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.records.append({"test": test.id(), "status": "blocking", "exception_type": err[0].__name__})

    def addError(self, test, err):
        super().addError(test, err)
        blocked = isinstance(err[1], PermissionError) and ".RealHTTPTests." in test.id()
        self.records.append({"test": test.id(), "status": "blocked_http" if blocked else "blocking", "exception_type": err[0].__name__})


def source_digest():
    """Only explicit source/schema paths; never enumerate configuration/secrets."""
    root = Path(__file__).resolve().parents[2]
    paths = ("backend/stillhere/service.py", "backend/stillhere/integration.py", "backend/stillhere/commands.py",
             "backend/stillhere/server.py", "backend/stillhere/agent/runtime.py", "backend/stillhere/agent/config.py",
             "backend/stillhere/agent/tools.py", "backend/stillhere/agent/provider.py", "backend/stillhere/worker.py",
             "backend/stillhere/planner/service.py", "backend/stillhere/planner/plans.py",
             "backend/stillhere/planner/dependencies.py", "backend/stillhere/planner/costs.py",
             "backend/stillhere/applications/domain.py", "backend/stillhere/finance/forecast.py",
             "backend/stillhere/finance/updates.py", "backend/stillhere/finance/scenarios.py",
             "backend/stillhere/outputs/dashboard.py", "backend/stillhere/outputs/replies.py",
             "backend/stillhere/boundaries/costs.py", "backend/stillhere/boundaries/applications.py",
             "backend/stillhere/boundaries/planning.py", "backend/stillhere/boundaries/trusted.py",
             "backend/stillhere/agent_extensions/adapters.py", "backend/stillhere/agent_extensions/replies.py",
             "backend/stillhere/agent_extensions/registry.py", "contracts/case-service.schema.json")
    return {path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in paths}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", action="append", choices=tuple(GROUPS), help="Explicit subset; default all")
    parser.add_argument("--report", type=Path, help="Save synthetic status/hash report; no case/session data")
    args = parser.parse_args(argv)
    groups = args.group or list(GROUPS)
    before = source_digest()
    loader = unittest.defaultTestLoader
    suite = unittest.TestSuite(loader.loadTestsFromName("tests.test_mvp_acceptance_parallel."+name)
                              for group in groups for name in GROUPS[group])
    result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(suite)
    after = source_digest()
    evidence = {"recorded_at": datetime.now(timezone.utc).isoformat(), "selected_groups": groups, "tests_run": result.testsRun,
                "failures": len(result.failures), "errors": len(result.errors),
                "passed": sum(item["status"] == "verified" for item in result.records),
                "blocking_checks": sum(item["status"] == "blocking" for item in result.records),
                "blocked_http_checks": sum(item["status"] == "blocked_http" for item in result.records),
                "skips": len(result.skipped), "source_digests_before": before,
                "source_digests_after": after, "checkout_changed_during_run": before != after,
                "slice_evidence_only": True, "full_mvp_readiness": "not_established",
                "live_verification": "pending_user_run", "results": result.records}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(evidence, indent=2)+"\n")
    return 0 if result.wasSuccessful() and not result.skipped and before == after else 1


if __name__ == "__main__":
    raise SystemExit(main())
