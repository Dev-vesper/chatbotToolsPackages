from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from core.models import SourceFile
from utils.tasks import CancelToken


@dataclass(frozen=True, slots=True)
class Match:
    line_number: int
    text: str


@dataclass(frozen=True, slots=True)
class FileMatch:
    source: SourceFile
    content: str
    matches: tuple[Match, ...]


@dataclass(frozen=True, slots=True)
class SearchResult:
    files: tuple[FileMatch, ...]
    total_matches: int
    error: str | None = None
    cancelled: bool = False


def search_project(
    sources: Sequence[SourceFile],
    query: str,
    *,
    regex: bool = False,
    case_sensitive: bool = False,
    token: CancelToken | None = None,
) -> SearchResult:
    if not query:
        return SearchResult((), 0)

    matches_line: Callable[[str], bool]
    if regex:
        try:
            compiled = re.compile(query, 0 if case_sensitive else re.IGNORECASE)
        except re.error as exc:
            return SearchResult((), 0, error=f"Invalid regex: {exc}")

        def matches_line(text: str) -> bool:
            return compiled.search(text) is not None
    elif case_sensitive:
        def matches_line(text: str) -> bool:
            return query in text
    else:
        needle = query.lower()

        def matches_line(text: str) -> bool:
            return needle in text.lower()

    files: list[FileMatch] = []
    total = 0
    for source in sources:
        if token is not None and token.cancelled:
            return SearchResult((), 0, cancelled=True)
        try:
            content = source.path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        found = tuple(
            Match(line_number=index, text=line)
            for index, line in enumerate(content.splitlines(), 1)
            if matches_line(line)
        )
        if found:
            files.append(FileMatch(source=source, content=content, matches=found))
            total += len(found)

    return SearchResult(tuple(files), total)
