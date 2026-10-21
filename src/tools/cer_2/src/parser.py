from __future__ import annotations

import re
from dataclasses import dataclass

_HEADER_RE = re.compile(r"^\s*##\s+(?P<path>\S.*?)\s*$")
_EDIT_RE = re.compile(r"^\s*(?P<number>\d+)(?:[ \t](?P<code>.*))?$")


@dataclass(frozen=True, slots=True)
class EditLine:
    line_number: int
    content: str


@dataclass(frozen=True, slots=True)
class FileEdits:
    rel_path: str
    edits: tuple[EditLine, ...]


@dataclass(frozen=True, slots=True)
class ParseResult:
    files: tuple[FileEdits, ...]
    errors: tuple[str, ...]

    @property
    def edit_count(self) -> int:
        return sum(len(file.edits) for file in self.files)

    @property
    def is_empty(self) -> bool:
        return not self.files


def parse_edits(text: str) -> ParseResult:
    files: list[FileEdits] = []
    errors: list[str] = []
    current_path: str | None = None
    current_edits: list[EditLine] = []

    def flush() -> None:
        nonlocal current_path, current_edits
        if current_path is not None:
            files.append(FileEdits(current_path, tuple(current_edits)))
        current_path = None
        current_edits = []

    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped == "---":
            continue
        header = _HEADER_RE.match(raw)
        if header:
            flush()
            current_path = header.group("path").strip()
            continue
        edit = _EDIT_RE.match(raw)
        if edit:
            if current_path is None:
                errors.append(f"Edit line outside a file block: {raw!r}")
                continue
            current_edits.append(
                EditLine(int(edit.group("number")), edit.group("code") or "")
            )
    flush()
    return ParseResult(tuple(files), tuple(errors))
