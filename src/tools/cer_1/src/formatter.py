from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from core.models import FileEntry
from core.skills import EDIT_SKILL


@dataclass(frozen=True, slots=True)
class FormatOptions:
    include_edit_skill: bool = True
    align_line_numbers: bool = False
    include_separators: bool = True


@dataclass(frozen=True, slots=True)
class FormatResult:
    text: str
    file_count: int
    line_count: int
    char_count: int

    @property
    def token_estimate(self) -> int:
        return self.char_count // 4


def format_files(entries: Sequence[FileEntry], options: FormatOptions) -> FormatResult:
    if not entries:
        return FormatResult("", 0, 0, 0)

    blocks: list[str] = []
    if options.include_edit_skill:
        blocks.append(f"EDIT SKILL\n{EDIT_SKILL}\n")

    blocks.append("CODEBASE:\n")

    line_total = 0
    for entry in entries:
        lines = entry.content.splitlines()
        line_total += len(lines)
        width = len(str(len(lines))) if options.align_line_numbers else 0
        numbered = [f"{number:>{width}} {line}" for number, line in enumerate(lines, 1)]
        block = "\n".join((f"## {entry.rel_path}", *numbered))
        if options.include_separators:
            block += "\n---"
        blocks.append(block + "\n")

    text = "\n".join(blocks).rstrip() + "\n"
    return FormatResult(text, len(entries), line_total, len(text))
