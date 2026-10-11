"""Local liveness plus read-only storage check; no Bedrock calls or household output."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
from urllib.request import ProxyHandler, build_opener


def check(database, url="http://127.0.0.1:8000/health"):
    with build_opener(ProxyHandler({})).open(url, timeout=5) as response:
        body = json.loads(response.read(16384))
        if response.status != 200 or body.get("status") != "ok" or body.get("contract_version") != "0.1":
            raise ValueError("Invalid health response")
    connection = sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    try:
        if connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise ValueError("Invalid database")
        for table in ("sessions", "cases", "events"):
            connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone()
    finally:
        connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--url", default="http://127.0.0.1:8000/health")
    args = parser.parse_args()
    try:
        check(args.db, args.url)
    except Exception:
        sys.exit("health_failed")
    print("health_ok")
