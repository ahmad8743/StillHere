"""Fail closed until integration supplies a standalone worker module and CLI contract."""
import os
import sys


def main():
    module = os.environ.get("STILLHERE_WORKER_MODULE", "")
    # This unit only registers the reviewed simulation candidate; an arbitrary
    # module could accidentally start an API or model worker with different authority.
    if module != "backend.stillhere.worker":
        sys.exit("worker_entry_point_not_integrated")
    os.execv(sys.executable, [sys.executable, "-m", module, "--db", "/var/lib/stillhere/cases.sqlite3"])


if __name__ == "__main__":
    main()
