"""Bounded report-volume snapshots. Operator must stop all writers first."""

import argparse
import contextlib
import io
import shutil
import sqlite3
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import BinaryIO

MAX_BYTES = 32 * 1024 * 1024
MAX_FILES = 4096
MAX_ARCHIVE = MAX_BYTES + 16 * 1024 * 1024


def create(root: Path, output: BinaryIO) -> None:
    root = root.resolve()
    if any(p.is_symlink() for p in root.rglob("*")):
        raise ValueError("Snapshot refuses symlinks")
    paths = sorted(p for p in root.rglob("*") if not p.is_dir())
    if len(paths) > MAX_FILES or any(p.is_symlink() or not p.is_file() for p in paths):
        raise ValueError("Snapshot requires bounded regular files; symlinks are refused")
    databases = {p for p in paths if p.suffix in {".sqlite", ".sqlite3", ".db"}}
    sidecars = {Path(str(p) + suffix) for p in databases for suffix in ("-wal", "-shm", "-journal")}
    total = 0
    with (
        tempfile.TemporaryDirectory() as directory,
        tarfile.open(fileobj=output, mode="w|") as archive,
    ):
        for number, path in enumerate(paths):
            if path in sidecars:
                continue
            selected = path
            if path in databases:
                selected = Path(directory) / f"{number}.sqlite"
                with contextlib.closing(
                    sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)
                ) as source:
                    with contextlib.closing(sqlite3.connect(selected)) as target:
                        source.backup(target)
                        if target.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                            raise ValueError("SQLite snapshot integrity failed")
            total += selected.stat().st_size
            if total > MAX_BYTES:
                raise ValueError("Report snapshot exceeds 32 MiB local-demo limit")
            archive.add(selected, arcname=path.relative_to(root).as_posix(), recursive=False)


def restore(root: Path, source: BinaryIO) -> None:
    if any(root.iterdir()):
        raise ValueError("Restore requires a fresh empty report volume")
    # Buffer only the explicitly bounded archive so every member can be validated
    # before extracting any file. Never use tarfile.extract/extractall.
    data = source.read(MAX_ARCHIVE + 1)
    if len(data) > MAX_ARCHIVE:
        raise ValueError("Snapshot archive exceeds local-demo limit")
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        members = archive.getmembers()
        names = set()
        total = 0
        for member in members:
            path = Path(member.name)
            if (
                not member.isfile()
                or path.is_absolute()
                or ".." in path.parts
                or "\\" in member.name
                or not path.parts
                or member.name in names
            ):
                raise ValueError("Unsafe or duplicate snapshot member")
            names.add(member.name)
            total += member.size
        if len(members) > MAX_FILES or total > MAX_BYTES:
            raise ValueError("Snapshot contents exceed local-demo limit")
        for member in members:
            target = root / member.name
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            stream = archive.extractfile(member)
            assert stream is not None
            with target.open("xb") as destination:
                shutil.copyfileobj(stream, destination)
            target.chmod(0o600)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("create", "restore"))
    parser.add_argument("--root", type=Path, default=Path("/reports"))
    args = parser.parse_args()
    if args.action == "create":
        create(args.root, sys.stdout.buffer)
    else:
        restore(args.root, sys.stdin.buffer)


if __name__ == "__main__":
    main()
