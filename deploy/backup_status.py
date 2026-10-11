"""Fixed-label backup age/capacity checks; no household data read or printed."""
import argparse
from pathlib import Path
import shutil
import sys
import time


def check(directory):
    snapshots = [p for p in directory.glob("*.sqlite3") if p.is_file() and not p.is_symlink()]
    if not snapshots or time.time() - max(p.stat().st_mtime for p in snapshots) > 2 * 3600:
        raise ValueError("Two hourly backups missed")
    capacity = shutil.disk_usage(directory)
    if capacity.free / capacity.total < 0.2:
        raise ValueError("Less than 20 percent free space")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("/var/backups/stillhere"))
    args = parser.parse_args()
    try:
        check(args.directory)
    except Exception:
        sys.exit("backup_age_or_capacity_failed")
    print("backup_age_capacity_ok")
