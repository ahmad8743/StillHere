"""Non-secret Linux target evidence; refuses unsupported OS/architecture/runtime."""
import argparse
import json
import platform
from pathlib import Path
import subprocess
import sys


def check(builder=False):
    os_info = platform.freedesktop_os_release()
    if (platform.system(), os_info.get("ID"), os_info.get("VERSION_ID"), platform.machine()) != ("Linux", "ubuntu", "24.04", "x86_64"):
        raise ValueError("Unsupported target; review assets before use")
    if sys.version_info[:2] != (3, 12):
        raise ValueError("CPython 3.12 required")
    evidence = {"os": "Ubuntu 24.04", "architecture": "x86_64", "python": platform.python_version()}
    if not builder:
        if not Path("/run/systemd/system").is_dir():
            raise ValueError("Native systemd required")
        for name, command in (("systemd", ["systemd-analyze", "--version"]),
                              ("caddy", ["caddy", "version"]),
                              ("certbot", ["/opt/certbot/bin/certbot", "--version"])):
            evidence[name] = subprocess.check_output(command, text=True, timeout=15, stderr=subprocess.DEVNULL).splitlines()[0]
        import re
        version = re.search(r"(\d+)\.(\d+)", evidence["certbot"])
        if version is None or tuple(map(int, version.groups())) < (5, 4):
            raise ValueError("Certbot webroot IP support requires 5.4+")
    return evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--builder", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(check(args.builder), sort_keys=True))
    except Exception:
        sys.exit("target_preflight_failed")
