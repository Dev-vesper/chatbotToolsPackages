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


def _apply_group(old: list[str], new: list[str]) -> list[str]:
    blocks = [
        block
        for block in SequenceMatcher(None, old, new, autojunk=False).get_matching_blocks()
        if block.size
    ]
    candidates = [block for block in blocks if block.a != block.b]
    anchor = next(
        (block for block in reversed(candidates) if block.size >= 2), None
    )
    if anchor is None and candidates:
        last = candidates[-1]
        # A one-line shifted suffix is still a clear insertion anchor when an
        # earlier run of lines matches in place.
        if last.b + last.size == len(new) and any(
            block.size >= 2 and block.a == block.b for block in blocks
        ):
            anchor = last
    if anchor is None:
        return new

    start = anchor.a
    stop = anchor.a + anchor.size
    old_prefix = old[:start]
    old_suffix = old[stop:]
    new_prefix = new[:anchor.b]
    new_suffix = new[anchor.b + anchor.size :]

    common = 0
    limit = min(len(old_prefix), len(new_prefix))
    while common < limit and old_prefix[common] == new_prefix[common]:
        common += 1
    if common == len(old_prefix):
        prefix = new_prefix
    else:
        prefix = old_prefix + new_prefix[common:]

    # The AI inserted lines and renumbered the rest. Matching lines are
    # context, not replacements: insert the new lines around them and keep
    # unmatched old lines instead of deleting them.
    return [
        *prefix,
        *new[anchor.b : anchor.b + anchor.size],
        *new_suffix,
        *old_suffix,
    ]


def apply_edits(original: str, edits: tuple[EditLine, ...]) -> tuple[str, list[str]]:
    lines, newline, trailing_newline = _split_text(original)
    warnings: list[str] = []
    by_line: dict[int, EditLine] = {}
    for edit in edits:
        if edit.line_number < 1 or edit.line_number > len(lines):
            warnings.append(
                f"Line {edit.line_number} is out of range (file has {len(lines)} lines)"
            )
            continue
        by_line[edit.line_number] = edit

    ordered = [by_line[number] for number in sorted(by_line)]
    result: list[str] = []
    cursor = 0
    index = 0
    while index < len(ordered):
        group = [ordered[index]]
        index += 1
        while (
            index < len(ordered)
            and ordered[index].line_number == group[-1].line_number + 1
        ):
            group.append(ordered[index])
            index += 1

        start = group[0].line_number - 1
        end = group[-1].line_number
        old = lines[start:end]
        new = [edit.content for edit in group]
        result.extend(lines[cursor:start])
        result.extend(_apply_group(old, new))
        cursor = end
    result.extend(lines[cursor:])

    text = "\n".join(result)
    if trailing_newline:
        text += "\n"
    if newline == "\r\n":
        text = text.replace("\n", "\r\n")
    return text, warnings


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
