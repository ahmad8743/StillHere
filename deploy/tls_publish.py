"""Server-only root hook: validate, publish an atomic TLS pair, safely reload Caddy.

Never run against developer keys. All subprocess diagnostics are discarded.
Certbot retains its own root-private logs; these are not chat artifacts.
"""
import argparse
import fcntl
import grp
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path("/etc/stillhere/tls")
LINEAGE = Path("/etc/letsencrypt/live/stillhere-ip")
IP = "172.238.189.78"


def run(command, **kwargs):
    return subprocess.run(command, check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, timeout=45, **kwargs).stdout


def switch(root, target):
    pending = root / ".current-next"
    pending.unlink(missing_ok=True)
    pending.symlink_to(target)
    os.replace(pending, root / "current")
    with open_directory(root) as directory:
        os.fsync(directory)


from contextlib import contextmanager


@contextmanager
def open_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        yield descriptor
    finally:
        os.close(descriptor)


def publish(initial=False):
    if os.geteuid() != 0 or os.environ.get("RENEWED_LINEAGE", str(LINEAGE)) != str(LINEAGE):
        raise ValueError("Root and fixed lineage required")
    ROOT.mkdir(mode=0o750, exist_ok=True)
    gid = grp.getgrnam("caddy").gr_gid
    os.chown(ROOT, 0, gid)
    os.chmod(ROOT, 0o750)
    # Same lock covers certificate switch + validation + reload/rollback.
    with (ROOT / ".publish.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        current = ROOT / "current"
        old = os.readlink(current) if current.is_symlink() else None
        if old is None and not initial:
            raise ValueError("Initial publication required")
        candidate = Path(tempfile.mkdtemp(prefix="pair-", dir=ROOT))
        os.chown(candidate, 0, gid)
        os.chmod(candidate, 0o750)
        try:
            for name in ("fullchain.pem", "privkey.pem"):
                destination = candidate / name
                shutil.copyfile(LINEAGE / name, destination)
                os.chown(destination, 0, gid)
                os.chmod(destination, 0o640)
                with destination.open("rb") as stream:
                    os.fsync(stream.fileno())
            cert, key = str(candidate / "fullchain.pem"), str(candidate / "privkey.pem")
            run(["openssl", "x509", "-in", cert, "-noout", "-checkend", "172800"])
            run(["openssl", "verify", "-purpose", "sslserver", "-verify_ip", IP, "-CApath", "/etc/ssl/certs", "-untrusted", cert, cert])
            if run(["openssl", "x509", "-in", cert, "-pubkey", "-noout"]) != run(["openssl", "pkey", "-in", key, "-pubout"]):
                raise ValueError("Certificate/key mismatch")
            with open_directory(candidate) as directory:
                os.fsync(directory)
            switch(ROOT, candidate.name)
            config = "/opt/stillhere/current/deploy/Caddyfile" if initial else "/etc/caddy/Caddyfile"
            try:
                run(["runuser", "-u", "caddy", "--", "caddy", "validate", "--config", config, "--adapter", "caddyfile"])
                if not initial:
                    run(["systemctl", "reload", "caddy"])
            except BaseException:
                if old is not None:
                    switch(ROOT, old)
                    # Best effort restoration of the previous known pair in memory.
                    if not initial:
                        try:
                            run(["systemctl", "reload", "caddy"])
                        except Exception:
                            pass
                else:
                    current.unlink(missing_ok=True)
                raise
        except BaseException:
            shutil.rmtree(candidate)
            raise
        # Remove superseded local copies after success. Certbot retains lineage
        # history privately; keep the current and immediate previous pair here.
        for path in ROOT.glob("pair-*"):
            if path.name not in (candidate.name, old) and path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initial", action="store_true")
    args = parser.parse_args()
    try:
        publish(args.initial)
    except Exception:
        sys.exit("tls_publish_failed")
    print("tls_publish_ok")
