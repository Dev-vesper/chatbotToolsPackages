from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class _Rule:
    regex: re.Pattern[str]
    negated: bool
    dir_only: bool
    anchored: bool


def _translate_glob(pattern: str) -> str:
    out: list[str] = []
    i = 0
    length = len(pattern)
    while i < length:
        char = pattern[i]
        if char == "*":
            end = i
            while end < length and pattern[end] == "*":
                end += 1
            if end - i >= 2:
                if end < length and pattern[end] == "/":
                    out.append("(?:.*/)?")
                    end += 1
                else:
                    out.append(".*")
            else:
                out.append("[^/]*")
            i = end
        elif char == "?":
            out.append("[^/]")
            i += 1
        elif char == "[":
            end = i + 1
            if end < length and pattern[end] in "!^":
                end += 1
            if end < length and pattern[end] == "]":
                end += 1
            while end < length and pattern[end] != "]":
                end += 1
            if end >= length:
                out.append(r"\[")
                i += 1
            else:
                content = pattern[i + 1 : end]
                if content.startswith("!"):
                    content = "^" + content[1:]
                out.append("[" + content + "]")
                i = end + 1
        elif char == "\\" and i + 1 < length:
            out.append(re.escape(pattern[i + 1]))
            i += 2
        else:
            out.append(re.escape(char))
            i += 1
    return "".join(out)


def _parse_rule(raw: str) -> _Rule | None:
    line = raw.strip()
    if not line:
        return None

    escaped_lead = line.startswith(("\\#", "\\!"))
    if escaped_lead:
        line = line[1:]
    elif line.startswith("#"):
        return None

    negated = not escaped_lead and line.startswith("!")
    if negated:
        line = line[1:]
    if not line:
        return None

    dir_only = line.endswith("/")
    if dir_only:
        line = line[:-1]
    if not line:
        return None

    anchored = line.startswith("/") or "/" in line
    if line.startswith("/"):
        line = line[1:]
    if not line:
        return None

    return _Rule(
        regex=re.compile("^" + _translate_glob(line) + "$"),
        negated=negated,
        dir_only=dir_only,
        anchored=anchored,
    )


class IgnoreMatcher:
    def __init__(self, patterns: Sequence[str]) -> None:
        self._rules = tuple(rule for raw in patterns if (rule := _parse_rule(raw)) is not None)

    def is_ignored(self, rel_path: str, is_dir: bool) -> bool:
        path = rel_path.strip("/")
        if not path:
            return False

        parts = path.split("/")
        prefixes = ["/".join(parts[: index + 1]) for index in range(len(parts))]
        dir_prefixes = prefixes if is_dir else prefixes[:-1]
        dir_parts = parts if is_dir else parts[:-1]

        ignored = False
        for rule in self._rules:
            if rule.anchored:
                targets = dir_prefixes if rule.dir_only else prefixes
            else:
                targets = dir_parts if rule.dir_only else parts
            if any(rule.regex.match(target) for target in targets):
                ignored = not rule.negated
        return ignored
