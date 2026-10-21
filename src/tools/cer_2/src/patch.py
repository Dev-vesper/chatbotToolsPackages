from __future__ import annotations

import difflib

from tools.cer_2.src.parser import EditLine


def apply_edits(original: str, edits: tuple[EditLine, ...]) -> tuple[str, list[str]]:
    lines = original.split("\n")
    trailing_newline = len(lines) > 1 and lines[-1] == ""
    if trailing_newline:
        lines = lines[:-1]
    warnings: list[str] = []
    for edit in edits:
        index = edit.line_number - 1
        if index < 0 or index >= len(lines):
            warnings.append(
                f"Line {edit.line_number} is out of range (file has {len(lines)} lines)"
            )
            continue
        lines[index] = edit.content
    result = "\n".join(lines)
    if trailing_newline:
        result += "\n"
    return result, warnings


def build_diff(rel_path: str, original: str, new: str) -> str:
    return "\n".join(
        difflib.unified_diff(
            original.splitlines(),
            new.splitlines(),
            fromfile=f"a/{rel_path}",
            tofile=f"b/{rel_path}",
            lineterm="",
        )
    )
