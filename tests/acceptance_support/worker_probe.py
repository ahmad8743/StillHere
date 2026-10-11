"""Disposable process fault seam: pause a REAL worker transaction before commit.

Never loads configuration or writes case SQL. The marker is test synchronization,
not a recovery record. Parent kills this process and verifies SQLite rollback.
"""

import argparse
from pathlib import Path
import threading

from backend.stillhere.service import CaseService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--marker", required=True)
    args = parser.parse_args()

    class InterruptedCaseService(CaseService):
        def _commit_derived(self, connection, snapshot, before, event_id, transition, now):
            if transition["type"] == "check_in.process_due":
                # Private state/effects have been written on the live connection,
                # but the enclosing CaseService transaction has not committed.
                Path(args.marker).write_text("transaction_open\n")
                threading.Event().wait(30)
                raise RuntimeError("Acceptance parent must kill before commit")
            return super()._commit_derived(connection, snapshot, before, event_id, transition, now)

    InterruptedCaseService(args.db).process_due_check_ins()


if __name__ == "__main__":
    main()
