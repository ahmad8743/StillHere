"""Inspect ownership/modes only; never read credentials or process environments."""
import grp
import os
from pathlib import Path
import pwd
import stat
import sys


def require(path, owner, group, mode):
    info = path.stat()
    if (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) != (pwd.getpwnam(owner).pw_uid, grp.getgrnam(group).gr_gid, mode):
        raise ValueError("Unsafe ownership/mode")


def check():
    for path in ("/var/lib/stillhere", "/var/backups/stillhere"):
        require(Path(path), "stillhere", "stillhere", 0o700)
    require(Path("/etc/stillhere"), "root", "root", 0o755)
    require(Path("/etc/stillhere/runtime.conf"), "root", "stillhere", 0o640)
    require(Path("/etc/caddy/Caddyfile"), "root", "caddy", 0o640)
    require(Path("/etc/stillhere/tls"), "root", "caddy", 0o750)
    pair = Path("/etc/stillhere/tls/current").resolve(strict=True)
    if pair.parent != Path("/etc/stillhere/tls"):
        raise ValueError("TLS pair outside private directory")
    require(pair, "root", "caddy", 0o750)
    for name in ("fullchain.pem", "privkey.pem"):
        require(pair / name, "root", "caddy", 0o640)
    # Deliberately do not stat/read developer or AWS credential files.
    release = Path("/opt/stillhere/current").resolve(strict=True)
    if release.parent != Path("/opt/stillhere/releases"):
        raise ValueError("Invalid immutable release link")
    for path in (release, *release.rglob("*")):
        if path.is_symlink():
            if path == release / ".venv/lib64" and path.resolve() == release / ".venv/lib":
                continue
            # Normal venv Python interpreter symlinks only.
            if path.parent != release / ".venv/bin" or not path.name.startswith("python"):
                raise ValueError("Unexpected release symlink")
            continue
        info = path.stat()
        if info.st_uid != 0 or info.st_gid != 0 or info.st_mode & 0o022:
            raise ValueError("Release writable by service")
    for path in Path("/var/lib/stillhere").iterdir():
        if path.is_symlink():
            raise ValueError("State must not be symlinked")
        require(path, "stillhere", "stillhere", 0o700 if path.is_dir() else 0o600)


if __name__ == "__main__":
    try:
        check()
    except Exception:
        sys.exit("ownership_verification_failed")
    print("ownership_verified")
