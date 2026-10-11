"""Independent simulated check-in worker. No model or credential configuration."""

import argparse
import json
import signal
import threading

from .service import CaseService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--interval", type=float, default=15)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if not 0.1 <= args.interval <= 3600:
        parser.error("interval must be between 0.1 and 3600 seconds")
    stopped = threading.Event()
    for number in (signal.SIGINT, signal.SIGTERM):
        signal.signal(number, lambda *_: stopped.set())
    service = CaseService(args.db)
    while not stopped.is_set():
        result = service.process_due_check_ins()
        if args.once:
            print(json.dumps(result, sort_keys=True))
            return
        stopped.wait(args.interval)


if __name__ == "__main__":
    main()
