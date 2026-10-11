"""Local administrator provisioning. Operator tokens are written privately, never logged."""

import argparse
import json
import os
from pathlib import Path

from .service import CaseService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--case", action="append", dest="cases", required=True)
    parser.add_argument("--operator-id")
    parser.add_argument("--token-file", type=Path, required=True)
    args = parser.parse_args()
    # Reserve the private output before provisioning so an existing file is safe.
    descriptor = os.open(args.token_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        result = CaseService(args.db).provision_operator(args.cases, operator_id=args.operator_id)
        with os.fdopen(descriptor, "w") as output:
            descriptor = None
            output.write(result.pop("session_token") + "\n")
        print(json.dumps(result, sort_keys=True))
    finally:
        if descriptor is not None:
            os.close(descriptor)


if __name__ == "__main__":
    main()
