"""Reproduce existing-suite evidence separately from independent acceptance gates."""

import argparse
import json
from pathlib import Path
import unittest


def leaves(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from leaves(item)
        else:
            yield item


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-http", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    discovered = list(leaves(unittest.defaultTestLoader.discover("tests", top_level_dir=".")))
    selected, excluded = [], []
    for test in discovered:
        identifier = test.id()
        if identifier.startswith("tests.test_mvp_acceptance_parallel.") or (not args.include_http and identifier.startswith("tests.test_http.")):
            excluded.append(identifier)
        else:
            selected.append(test)
    result = unittest.TextTestRunner(verbosity=1).run(unittest.TestSuite(selected))
    report = {"discovered": len(discovered), "selected": len(selected), "excluded": excluded,
              "failures": [test.id() for test, _ in result.failures], "errors": [test.id() for test, _ in result.errors],
              "skips": [test.id() for test, _ in result.skipped], "full_mvp_readiness": "not_established"}
    if args.report:
        args.report.write_text(json.dumps(report, indent=2)+"\n")
    return 0 if result.wasSuccessful() and not result.skipped else 1


if __name__ == "__main__":
    raise SystemExit(main())
