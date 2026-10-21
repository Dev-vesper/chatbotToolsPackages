from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from tools.cer_3.src.searcher import FileMatch, Match

EDIT_SKILL = (
    "When editing files, work line by line and use the given line numbers to locate "
    'every change. Return only the edited lines in the same format, "<line number> <code>", '
    "with correct line numbers and the original indentation. "
    "Do not resend unchanged code or the entire file."
)


@dataclass(frozen=True, slots=True)
class FormatOptions:
    context_lines: int = 2
    include_edit_skill: bool = True
    full_files: bool = False


@dataclass(frozen=True, slots=True)
class FormatResult:
    text: str
    file_count: int
    line_count: int
    char_count: int

    @property
    def token_estimate(self) -> int:
        return self.char_count // 4


def format_results(
    matches: Sequence[FileMatch],
    options: FormatOptions,
) -> FormatResult:
    if not matches:
        return FormatResult("", 0, 0, 0)

    blocks: list[str] = []
    if options.include_edit_skill:
        blocks.append(f"EDIT SKILL\n{EDIT_SKILL}\n")
    blocks.append("CODEBASE:\n")

    line_total = 0
    for fm in matches:
        lines = fm.content.splitlines()
        if not lines:
            continue
        width = len(str(len(lines)))
        numbered = _numbered_lines(lines, fm.matches, options, width)
        if not numbered:
            continue
        line_total += len(numbered)
        block = "\n".join((f"## {fm.source.rel_path}", *numbered))
        blocks.append(block + "\n---\n")

    text = "\n".join(blocks).rstrip() + "\n"
    return FormatResult(text, len(matches), line_total, len(text))


def _numbered_lines(
    lines: list[str],
    matches: Sequence[Match],
    options: FormatOptions,
    width: int,
) -> list[str]:
    if options.full_files:
        return [f"{number:>{width}} {line}" for number, line in enumerate(lines, 1)]

    match_numbers = sorted({match.line_number for match in matches})
    ranges = _merge_ranges(match_numbers, options.context_lines, len(lines))
    output: list[str] = []
    for start, end in ranges:
        for number in range(start, end + 1):
            output.append(f"{number:>{width}} {lines[number - 1]}")
    return output


def _merge_ranges(
    numbers: list[int],
    context: int,
    total: int,
) -> list[tuple[int, int]]:
    if not numbers:
        return []
    ranges: list[list[int]] = []
    for number in numbers:
        start = max(1, number - context)
        end = min(total, number + context)
        if ranges and start <= ranges[-1][1] + 1:
            ranges[-1][1] = max(ranges[-1][1], end)
        else:
            ranges.append([start, end])
    return [(start, end) for start, end in ranges]
