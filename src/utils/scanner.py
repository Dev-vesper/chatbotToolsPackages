from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from core.models import ScanResult, SourceFile
from utils.gitignore import IgnoreMatcher

_SAMPLE_BYTES = 4096
_CANCEL_INTERVAL = 64


def _is_binary(path: Path) -> bool | None:
    try:
        with path.open("rb") as handle:
            chunk = handle.read(_SAMPLE_BYTES)
    except OSError:
        return None
    return b"\x00" in chunk


def scan_project(
    root: Path,
    matcher: IgnoreMatcher,
    cancel: Callable[[], bool] | None = None,
) -> ScanResult:
    root = Path(root)
    files: list[SourceFile] = []
    skipped = 0
    processed = 0
    pending: list[tuple[Path, str]] = [(root, "")]

    while pending:
        if cancel is not None and cancel():
            return ScanResult((), skipped, cancelled=True)

        directory, rel_dir = pending.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError:
            skipped += 1
            continue

        for entry in entries:
            processed += 1
            if processed % _CANCEL_INTERVAL == 0 and cancel is not None and cancel():
                return ScanResult((), skipped, cancelled=True)

            rel_path = f"{rel_dir}/{entry.name}" if rel_dir else entry.name
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if not matcher.is_ignored(rel_path, True):
                        pending.append((Path(entry.path), rel_path))
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                if matcher.is_ignored(rel_path, False):
                    continue

                size = entry.stat(follow_symlinks=False).st_size
                binary = _is_binary(Path(entry.path))
                if binary is None or binary:
                    skipped += 1
                    continue
                files.append(SourceFile(Path(entry.path), rel_path, size))
            except OSError:
                skipped += 1

    files.sort(key=lambda item: item.rel_path.lower())
    return ScanResult(tuple(files), skipped)
