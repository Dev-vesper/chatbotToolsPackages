from __future__ import annotations

from difflib import SequenceMatcher

from core.models import DiffLine, FileDiff
from tools.cer_2.src.parser import EditLine

_CONTEXT_LINES = 3


def _split_text(text: str) -> tuple[list[str], str, bool]:
    newline = "\r\n" if "\r\n" in text else "\n"
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    trailing_newline = len(lines) > 1 and lines[-1] == ""
    if trailing_newline:
        lines = lines[:-1]
    return lines, newline, trailing_newline


def apply_edits(original: str, edits: tuple[EditLine, ...]) -> tuple[str, list[str]]:
    lines, newline, trailing_newline = _split_text(original)
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
    if newline == "\r\n":
        result = result.replace("\n", "\r\n")
    return result, warnings


def _format_range(start: int, stop: int) -> str:
    beginning = start + 1
    length = stop - start
    if length == 1:
        return str(beginning)
    if length == 0:
        beginning -= 1
    return f"{beginning},{length}"


def build_file_diff(rel_path: str, original: str, new: str) -> FileDiff:
    old_lines = original.splitlines()
    new_lines = new.splitlines()
    matcher = SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    lines: list[DiffLine] = []
    additions = 0
    deletions = 0

    for group in matcher.get_grouped_opcodes(_CONTEXT_LINES):
        first, last = group[0], group[-1]
        lines.append(
            DiffLine(
                "hunk",
                f"@@ -{_format_range(first[1], last[2])} "
                f"+{_format_range(first[3], last[4])} @@",
            )
        )
        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                for offset in range(i2 - i1):
                    lines.append(
                        DiffLine(
                            "context",
                            old_lines[i1 + offset],
                            i1 + offset + 1,
                            j1 + offset + 1,
                        )
                    )
                continue
            if tag in ("replace", "delete"):
                for offset in range(i2 - i1):
                    lines.append(
                        DiffLine("del", old_lines[i1 + offset], i1 + offset + 1, None)
                    )
                    deletions += 1
            if tag in ("replace", "insert"):
                for offset in range(j2 - j1):
                    lines.append(
                        DiffLine("add", new_lines[j1 + offset], None, j1 + offset + 1)
                    )
                    additions += 1

    return FileDiff(rel_path, tuple(lines), additions, deletions)


def diff_to_text(diff: FileDiff) -> str:
    output = [f"--- a/{diff.rel_path}", f"+++ b/{diff.rel_path}"]
    for line in diff.lines:
        if line.kind == "hunk":
            output.append(line.text)
        elif line.kind == "add":
            output.append(f"+{line.text}")
        elif line.kind == "del":
            output.append(f"-{line.text}")
        else:
            output.append(f" {line.text}")
    return "\n".join(output)
