"""Hash-lock a separate approved Linux Certbot wheelhouse; no installation/network."""
import argparse
from pathlib import Path
import sys

from build_release import wheel_requirements
from preflight import check


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        check(builder=True)
        wheels = sorted(args.wheelhouse.glob("*.whl"))
        if any(path.is_symlink() for path in wheels):
            raise ValueError("Unsafe wheel input")
        locked = wheel_requirements(wheels, frozenset({"certbot"}))
        if not any(line.startswith("certbot==5.8.0 --hash=sha256:") for line in locked.decode().splitlines()):
            raise ValueError("Reviewed Certbot pin required")
        with args.output.open("xb") as stream:
            stream.write(locked)
    except Exception:
        sys.exit("certbot_lock_failed")
    print("certbot_wheels_locked")
