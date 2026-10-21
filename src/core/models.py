from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class FileEntry:
    path: Path
    rel_path: str
    content: str

    @property
    def line_count(self) -> int:
        return len(self.content.splitlines())
