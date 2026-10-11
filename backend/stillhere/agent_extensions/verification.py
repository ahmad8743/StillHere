"""Reproduce review-only assembly regressions without touching shared sources."""

import argparse
import shutil
import subprocess
import sys

from .testing import ROOT, proposed_checkout

MODULES = ("test_agent_extensions", "test_agent_extensions_sdk", "test_agent", "test_strands_agent",
           "test_applications", "test_outputs", "test_check_ins", "test_finance", "test_finance_updates",
           "test_finance_scenarios", "test_finance_schema", "test_case_service", "test_intake", "test_access")
HELPERS = ("test_incidents", "test_resources", "test_program_rules", "test_live_fetch_example",
           "test_planner_bounded", "test_knowledge", "test_domain_boundaries")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline review-only extension verification in disposable public-source copies")
    parser.add_argument("--proposed-regressions", action="store_true", required=True,
                        help="Apply all three code/fixture proposals only in a disposable checkout")
    parser.parse_args(argv)
    with proposed_checkout(boundary=True, fixtures=True) as root:
        for name in MODULES + HELPERS:
            if name not in ("test_case_service", "test_intake", "test_access"):
                shutil.copyfile(ROOT / "tests" / (name + ".py"), root / "tests" / (name + ".py"))
        # The boundary owner's separate patch-review test applies its own overlapping
        # proposals. Run its pure domain tests here; do not apply both replacements.
        targets = ["tests." + name for name in MODULES] + ["tests.test_domain_boundaries.DomainBoundaryTests"]
        result = subprocess.run([sys.executable, "-W", "error::ResourceWarning", "-m", "unittest", *targets, "-q"],
            cwd=root, env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1", "STILLHERE_ISOLATED_PROPOSAL": "1"}, timeout=60)
        return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
