"""Verify extracted release bytes before offline installation; prints no payloads."""
import hashlib
import json
from pathlib import Path
import sys


def verify(root):
    manifest = json.loads((root / "release.json").read_text())["sha256"]
    for name, expected in manifest.items():
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("Unsafe release path")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Release checksum mismatch")
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    if actual != set(manifest) | {"release.json"}:
        raise ValueError("Unexpected release files")


if __name__ == "__main__":
    try:
        verify(Path(sys.argv[1]))
    except Exception:
        sys.exit("release_verification_failed")
    print("release_verified")
