"""Hashline applier for CER-2.

Turns the anchored Insert/Delete/Cut/Paste primitives emitted by the parser
into a new file body. Cut registers are resolved in order; gap inserts land
before or after their anchor line; range replacements emit their body then
delete the original span. Diff helpers are unchanged from the pre-Hashline
version because the FileDiff contract is untouched.
"""

from __future__ import annotations

from difflib import SequenceMatcher

from core.models import DiffLine, FileDiff
from tools.cer_2.src.parser import Cut, Delete, Edit, Insert, Paste


_CONTEXT_LINES = 3


def _split_text(text: str) -> tuple[list[str], str, bool]:
    newline = "\r\n" if "\r\n" in text else "\n"
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    trailing_newline = len(lines) > 1 and lines[-1] == ""
    if trailing_newline:
        lines = lines[:-1]
    return lines, newline, trailing_newline


class _Clipboard:
    __slots__ = ("_named", "_anonymous")

    def __init__(self) -> None:
        self._named: dict[str, list[str]] = {}
        self._anonymous: list[str] = []

    def store(self, register: str | None, lines: list[str]) -> None:
        if register:
            self._named[register] = list(lines)
        else:
            self._anonymous = list(lines)

    def fetch(self, register: str | None) -> list[str] | None:
        if register:
            return self._named.get(register)
        return self._anonymous if self._anonymous else None


def apply_edits(original: str, edits: tuple[Edit, ...]) -> tuple[str, list[str]]:
    lines, newline, trailing_newline = _split_text(original)
    warnings: list[str] = []
    clipboard = _Clipboard()

    before_inserts: dict[int, list[str]] = {}
    after_inserts: dict[int, list[str]] = {}
    replacements: dict[int, list[str]] = {}
    deletes: set[int] = set()
    bof_inserts: list[str] = []
    eof_inserts: list[str] = []
    span_pastes: list[tuple[int, int, str | None]] = []

    for edit in edits:
        if isinstance(edit, Insert):
            if edit.position == "bof":
                bof_inserts.append(edit.text)
            elif edit.position == "eof":
                eof_inserts.append(edit.text)
            elif edit.position == "before":
                if edit.anchor is None:
                    continue
                if edit.replacement:
                    replacements.setdefault(edit.anchor, []).append(edit.text)
                else:
                    before_inserts.setdefault(edit.anchor, []).append(edit.text)
            elif edit.position == "after":
                if edit.anchor is None:
                    continue
                after_inserts.setdefault(edit.anchor, []).append(edit.text)
        elif isinstance(edit, Delete):
            deletes.add(edit.line)
        elif isinstance(edit, Cut):
            start = edit.start - 1
            end = edit.end
            if start < 0 or end > len(lines):
                warnings.append(
                    f"CUT range {edit.start}.={edit.end} is outside the file"
                )
                continue
            clipboard.store(edit.register, lines[start:end])
        elif isinstance(edit, Paste):
            if edit.position == "span" and edit.span is not None:
                span_pastes.append((edit.span[0], edit.span[1], edit.register))
            elif edit.position == "before" and edit.anchor is not None:
                captured = clipboard.fetch(edit.register)
                if captured is None:
                    warnings.append(
                        f"paste before line {edit.anchor}: register not populated"
                    )
                    continue
                before_inserts.setdefault(edit.anchor, []).extend(captured)
            elif edit.position == "after" and edit.anchor is not None:
                captured = clipboard.fetch(edit.register)
                if captured is None:
                    warnings.append(
                        f"paste after line {edit.anchor}: register not populated"
                    )
                    continue
                after_inserts.setdefault(edit.anchor, []).extend(captured)
            elif edit.position == "bof":
                captured = clipboard.fetch(edit.register)
                if captured is not None:
                    bof_inserts.extend(captured)
            elif edit.position == "eof":
                captured = clipboard.fetch(edit.register)
                if captured is not None:
                    eof_inserts.extend(captured)

    for start, end, register in span_pastes:
        captured = clipboard.fetch(register)
        if captured is None:
            warnings.append(
                f"paste over {start}.={end}: register not populated"
            )
            continue
        for n in range(start, end + 1):
            deletes.add(n)
        replacements.setdefault(start, []).extend(captured)

    result: list[str] = []
    result.extend(bof_inserts)
    for idx, line_text in enumerate(lines, 1):
        if idx in before_inserts:
            result.extend(before_inserts[idx])
        if idx in replacements:
            result.extend(replacements[idx])
        if idx not in deletes:
            result.append(line_text)
        if idx in after_inserts:
            result.extend(after_inserts[idx])
    result.extend(eof_inserts)

    text = "\n".join(result)
    if trailing_newline:
        text += "\n"
    if newline == "\r\n":
        text = text.replace("\n", "\r\n")
    return text, warnings


# ---- Diff building (unchanged contract) ----

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
