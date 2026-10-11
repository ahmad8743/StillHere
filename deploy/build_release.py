#!/usr/bin/env python3
"""Allowlisted deterministic release; supply a target Linux wheelhouse, never a venv."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile
import zipfile


def source_files(root):
    # Deliberately do not traverse the checkout, config, home, var or .references.
    files = []
    for base, suffixes in (("backend", {".py", ".json"}),
                           ("contracts", {".json"}),
                           ("tests", {".py"}),
                           ("deploy", {".py", ".sh", ".service", ".timer", ".conf", ".md", ".patch"})):
        if (root / base).is_symlink():
            raise ValueError("Source directories must not be symlinks")
        for path in (root / base).rglob("*"):
            if any(part.startswith(".") or part == "__pycache__" for part in path.relative_to(root).parts):
                continue
            if path.suffix in suffixes and path.is_file() and not path.is_symlink():
                if not path.resolve().is_relative_to(root.resolve()):
                    raise ValueError("Source path outside checkout")
                files.append(path)
    for name in ("backend/requirements-agent.txt", "deploy/Caddyfile", "deploy/Caddyfile.bootstrap", "deploy/runtime.conf.example",
                 "docs/parallel/deployment-final-handoff.md"):
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("Unsafe required source path")
        files.append(path)
    return sorted(set(files))


def wheel_requirements(wheels, required_names=frozenset({"strands-agents", "python-dotenv"})):
    rows = []
    names = set()
    for path in wheels:
        with zipfile.ZipFile(path) as archive:
            entries = [n for n in archive.namelist() if n.endswith(".dist-info/METADATA")]
            if len(entries) != 1:
                raise ValueError("Invalid wheel metadata")
            from email.parser import BytesParser
            metadata = BytesParser().parsebytes(archive.read(entries[0]))
        name, version = metadata["Name"], metadata["Version"]
        if not name or not version or not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or not re.fullmatch(r"[A-Za-z0-9_.+!-]+", version):
            raise ValueError("Invalid package identity")
        normalized = re.sub(r"[-_.]+", "-", name).lower()
        if normalized in names:
            raise ValueError("One wheel per distribution is required")
        names.add(normalized)
        rows.append(f"{name}=={version} --hash=sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}")
    if not required_names <= names:
        raise ValueError("Missing required agent wheels")
    return ("\n".join(sorted(rows)) + "\n").encode()


def build(root, destination, wheelhouse, source_revision):
    entries = {p.relative_to(root).as_posix(): p.read_bytes() for p in source_files(root)}
    wheels = sorted(wheelhouse.glob("*.whl"))
    if any(p.is_symlink() for p in wheels):
        raise ValueError("Wheel symlinks are not allowed")
    entries["requirements.lock"] = wheel_requirements(wheels)
    locked = {line.split(" --hash=", 1)[0].replace("_", "-").lower()
              for line in entries["requirements.lock"].decode().splitlines()}
    for line in entries["backend/requirements-agent.txt"].decode().splitlines():
        pin = line.split("#", 1)[0].strip()
        if pin and pin.replace("_", "-").lower() not in locked:
            raise ValueError("Wheelhouse does not match direct dependency pins")
    for path in wheels:
        entries["wheelhouse/" + path.name] = path.read_bytes()
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(entries.items())}
    entries["release.json"] = (json.dumps({"source_revision": source_revision, "target": "Ubuntu 24.04 / CPython 3.12 / Linux x86_64",
                                          "sha256": manifest}, sort_keys=True, indent=2) + "\n").encode()
    # Stable owners, timestamps, ordering and gzip header; identical bytes -> identical archive.
    with destination.open("xb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            with tarfile.open(fileobj=zipped, mode="w") as archive:
                for name, data in sorted(entries.items()):
                    info = tarfile.TarInfo(name)
                    info.size, info.mode, info.mtime = len(data), 0o644, 0
                    archive.addfile(info, io.BytesIO(data))
    return hashlib.sha256(destination.read_bytes()).hexdigest()


def main():
    # CLI release builds must run on the confirmed target platform. The build()
    # function remains callable for explicitly synthetic packaging tests.
    from preflight import check
    check(builder=True)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(build(args.root.resolve(), args.output, args.wheelhouse, args.source_revision))


if __name__ == "__main__":
    main()
