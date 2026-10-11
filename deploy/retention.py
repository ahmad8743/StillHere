"""Operator-only local retention, gated by a trusted off-host restore receipt.

Receipt: {"restore_verified": true, "verified_at": RFC3339 UTC,
          "sha256": {"TIMESTAMP.sqlite3": "SHA256"}}.
Only listed identical files can be removed; preserves latest 48 hours and newest.
Run as stillhere after stopping the backup timer/service. Default is dry-run.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import time


def prune(directory, receipt, apply=False):
    proof = json.loads(receipt.read_text())
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(proof["verified_at"].replace("Z", "+00:00"))).total_seconds()
    if proof.get("restore_verified") is not True or not 0 <= age <= 7 * 86400:
        raise ValueError("Recent trusted recovery rehearsal required")
    files = sorted(p for p in directory.glob("*.sqlite3") if p.is_file() and not p.is_symlink())
    deleted = 0
    for path in files[:-1]:
        if not re.fullmatch(r"\d{8}T\d{12}Z\.sqlite3", path.name) or time.time() - path.stat().st_mtime <= 48 * 3600:
            continue
        if proof.get("sha256", {}).get(path.name) != hashlib.sha256(path.read_bytes()).hexdigest():
            continue
        if apply:
            path.unlink()
        deleted += 1
    return deleted


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        print("retention_eligible_count=" + str(prune(args.directory, args.receipt, args.apply)))
    except Exception:
        sys.exit("retention_failed")
