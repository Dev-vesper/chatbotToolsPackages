from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path


def write_text_atomic(path: Path, text: str) -> None:
    try:
        mode: int | None = stat.S_IMODE(path.stat().st_mode)
    except OSError:
        mode = None

    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        if mode is not None:
            try:
                os.chmod(temp_name, mode)
            except OSError:
                pass
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
