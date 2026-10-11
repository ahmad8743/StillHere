"""Consistent SQLite backup and restore into an empty directory, never over a live DB."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import sys
import time


def read_only(path):
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)


def copy_database(source, destination, timeout=120):
    descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    deadline = time.monotonic() + timeout

    def progress(status, remaining, total):
        if time.monotonic() >= deadline:
            raise TimeoutError("Backup time limit")

    try:
        with closing(read_only(source)) as src, closing(sqlite3.connect(destination)) as dst:
            src.backup(dst, pages=128, progress=progress, sleep=0.1)
            # Each output is a standalone database, not dependent on source WAL files.
            dst.execute("PRAGMA journal_mode=DELETE")
            if dst.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise ValueError("Invalid backup")
            if dst.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise ValueError("Invalid references")
            for table in ("sessions", "cases", "events"):
                dst.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone()
        with destination.open("rb") as output:
            os.fsync(output.fileno())
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def backup(source, directory):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ.sqlite3")
    temporary = directory / ("." + name + ".partial")
    copy_database(source, temporary)
    os.replace(temporary, directory / name)
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return directory / name


def restore(source, directory):
    # Exclusive mkdir refuses even an existing empty target. Operators must stop all
    # writers, restore to a NEW sibling, then switch directories while services stop.
    directory.mkdir(mode=0o700)
    try:
        copy_database(source, directory / "cases.sqlite3")
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        descriptor = os.open(directory.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except BaseException:
        (directory / "cases.sqlite3").unlink(missing_ok=True)
        directory.rmdir()
        raise


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("backup", "restore"))
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.operation == "backup":
            backup(args.source, args.directory)
        else:
            restore(args.source, args.directory)
    except Exception:
        sys.exit("database_copy_failed")
    print("database_copy_ok")
