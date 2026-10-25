"""Hashline parser for CER-2.

Parses AI responses in hashline format into structured file edits. Modelled on
oh-my-pi's Rust implementation (crates/pi-edit): a section tokenizer followed
by an op parser that lowers each op into anchored Insert/Delete/Cut/Paste
primitives.

Section shape::

    [path#TAG]
    PUT 3.=3:
    +new line three
    CUT 5.=7
    PUT <10:
    +before line ten

Block ops (`PUT N*:`, `CUT N*`) are accepted but degraded to the single anchor
line, since CER-2 has no syntax-aware block resolver. Multi-line changes must
use explicit ranges; the skill prompt already instructs the model to.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Union


MAX_RANGE_LINES = 100_000


# ---- Edit primitives ----

@dataclass(frozen=True, slots=True)
class Insert:
    anchor: int | None
    position: str  # 'before' | 'after' | 'bof' | 'eof'
    text: str
    replacement: bool = False  # True when part of a PUT range replace


@dataclass(frozen=True, slots=True)
class Delete:
    line: int


@dataclass(frozen=True, slots=True)
class Cut:
    start: int
    end: int
    register: str | None


@dataclass(frozen=True, slots=True)
class Paste:
    anchor: int | None
    position: str  # 'before' | 'after' | 'bof' | 'eof' | 'span'
    register: str | None
    span: tuple[int, int] | None = None


Edit = Union[Insert, Delete, Cut, Paste]


# ---- File-level ----

@dataclass(frozen=True, slots=True)
class FileOp:
    kind: str  # 'rem' | 'move'
    dest: str | None = None


@dataclass(frozen=True, slots=True)
class FileEdits:
    rel_path: str
    tag: str | None
    edits: tuple[Edit, ...]
    file_op: FileOp | None = None


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


# ---- Regexes ----

_HEADER_RE = re.compile(r"^\s*\[(?P<body>[^\[\]]+)\]\s*$")
_OP_PUT = re.compile(r"^PUT\s+(?P<target>[^\s:@]+)(?P<colon>:?)\s*(?P<rest>.*)$")
_OP_CUT = re.compile(r"^CUT\s+(?P<target>[^\s@]+)\s*(?P<rest>.*)$")
_OP_MV = re.compile(r"^MV\s+(?P<dest>.+)$")
_REG_RE = re.compile(r"^@([\w-]+)")
_RANGE_RE = re.compile(r"^(\d+)(?:[.=]+(\d+))?$")


# ---- Small parsers ----

def _split_register(rest: str) -> tuple[str | None, str]:
    rest = rest.lstrip()
    match = _REG_RE.match(rest)
    if not match:
        return None, rest
    return match.group(1), rest[match.end():]


def _parse_header(line: str) -> tuple[str, str | None] | None:
    match = _HEADER_RE.match(line)
    if not match:
        return None
    body = match.group("body").strip()
    if not body:
        return None
    if "#" in body:
        path, tag = body.rsplit("#", 1)
        if (
            len(tag) == 4
            and all(ch in "0123456789abcdefABCDEF" for ch in tag)
            and path
        ):
            return path, tag.upper()
    return body, None


def _parse_range_spec(spec: str) -> tuple[int, int, bool] | None:
    """Parse `N`, `N.=M`, `N.=N` or `N*`. Return `(start, end, is_block)`."""
    spec = spec.strip()
    if not spec:
        return None
    if spec.endswith("*"):
        digit_part = spec[:-1]
        if not digit_part.isdigit():
            return None
        line = int(digit_part)
        if line < 1:
            return None
        return line, line, True
    match = _RANGE_RE.match(spec)
    if not match:
        return None
    start = int(match.group(1))
    end = int(match.group(2)) if match.group(2) else start
    if start < 1 or end < 1 or end < start:
        return None
    if end - start + 1 > MAX_RANGE_LINES:
        return None
    return start, end, False


def _try_parse_op(line: str) -> dict | None:
    """Parse one op header row. Return a descriptor dict, or `None`."""
    if line == "REM":
        return {"kind": "rem"}
    if line == "MV":
        return None
    match = _OP_MV.match(line)
    if match:
        dest = match.group("dest").strip()
        if len(dest) >= 2 and dest[0] == dest[-1] and dest[0] in "\"'":
            dest = dest[1:-1]
        if not dest:
            return None
        return {"kind": "mv", "dest": dest}

    match = _OP_PUT.match(line)
    if match:
        target = match.group("target")
        colon = match.group("colon")
        rest = match.group("rest")
        register, _ = _split_register(rest)
        had_colon = bool(colon)

        if target.startswith("<"):
            tail = target[1:]
            if tail == "1":
                return {
                    "kind": "put_gap", "anchor": None, "position": "bof",
                    "register": register, "had_colon": had_colon,
                }
            if tail.isdigit():
                return {
                    "kind": "put_gap", "anchor": int(tail), "position": "before",
                    "register": register, "had_colon": had_colon,
                }
            return None

        if target.startswith(">"):
            tail = target[1:]
            if tail == "$":
                return {
                    "kind": "put_gap", "anchor": None, "position": "eof",
                    "register": register, "had_colon": had_colon,
                }
            star = tail.endswith("*")
            if star:
                tail = tail[:-1]
            if tail.isdigit():
                return {
                    "kind": "put_gap", "anchor": int(tail), "position": "after",
                    "register": register, "had_colon": had_colon,
                }
            return None

        rng = _parse_range_spec(target)
        if rng is None:
            return None
        start, end, is_block = rng
        if is_block:
            return {
                "kind": "put_block", "anchor": start,
                "register": register, "had_colon": had_colon,
            }
        return {
            "kind": "put_span", "range": (start, end),
            "register": register, "had_colon": had_colon,
        }

    match = _OP_CUT.match(line)
    if match:
        target = match.group("target")
        rest = match.group("rest")
        register, _ = _split_register(rest)
        rng = _parse_range_spec(target)
        if rng is None:
            return None
        start, end, is_block = rng
        if is_block:
            return {"kind": "cut_block", "anchor": start, "register": register}
        return {"kind": "cut", "range": (start, end), "register": register}

    return None


# ---- Section splitting ----

@dataclass(slots=True)
class _Section:
    path: str
    tag: str | None
    lines: list[tuple[int, str]]


def _split_sections(lines: list[str]) -> list[_Section]:
    sections: list[_Section] = []
    current_path: str | None = None
    current_tag: str | None = None
    current_lines: list[tuple[int, str]] = []

    def flush() -> None:
        nonlocal current_path, current_tag, current_lines
        if current_path is not None:
            sections.append(_Section(current_path, current_tag, current_lines))
        current_path = None
        current_tag = None
        current_lines = []

    for index, raw in enumerate(lines, 1):
        parsed = _parse_header(raw)
        if parsed is not None:
            flush()
            current_path, current_tag = parsed
            continue
        if current_path is not None:
            current_lines.append((index, raw))

    flush()
    return sections


# ---- Section execution ----

def _execute_section(
    section: _Section,
) -> tuple[list[Edit], FileOp | None, list[str]]:
    edits: list[Edit] = []
    file_op: FileOp | None = None
    errors: list[str] = []

    current_op: dict | None = None
    payloads: list[str] = []

    def emit() -> None:
        nonlocal file_op, current_op, payloads
        if current_op is None:
            payloads = []
            return
        op = current_op
        body = payloads[:]
        current_op = None
        payloads = []

        kind = op["kind"]
        line_num = op.get("line_num", 0)

        if kind == "rem":
            if edits:
                errors.append(
                    f"line {line_num}: REM cannot be combined with line edits"
                )
                return
            file_op = FileOp("rem")
            return
        if kind == "mv":
            if file_op is not None:
                errors.append(
                    f"line {line_num}: only one REM or MV per file section"
                )
                return
            file_op = FileOp("move", op["dest"])
            return
        if kind == "put_span":
            start, end = op["range"]
            register: str | None = op["register"]
            if register is not None:
                edits.append(Paste(start, "span", register, (start, end)))
                return
            if not body:
                for n in range(start, end + 1):
                    edits.append(Delete(n))
                return
            for text in body:
                edits.append(Insert(start, "before", text, replacement=True))
            for n in range(start, end + 1):
                edits.append(Delete(n))
            return
        if kind == "put_gap":
            anchor: int | None = op["anchor"]
            position: str = op["position"]
            register = op["register"]
            if register is not None:
                edits.append(Paste(anchor, position, register))
                return
            for text in body:
                edits.append(Insert(anchor, position, text))
            return
        if kind == "put_block":
            anchor = op["anchor"]
            register = op["register"]
            if register is not None:
                edits.append(Paste(anchor, "span", register, (anchor, anchor)))
                return
            if not body:
                edits.append(Delete(anchor))
                return
            for text in body:
                edits.append(Insert(anchor, "before", text, replacement=True))
            edits.append(Delete(anchor))
            return
        if kind == "cut":
            start, end = op["range"]
            register = op["register"]
            edits.append(Cut(start, end, register))
            for n in range(start, end + 1):
                edits.append(Delete(n))
            return
        if kind == "cut_block":
            anchor = op["anchor"]
            register = op["register"]
            edits.append(Cut(anchor, anchor, register))
            edits.append(Delete(anchor))
            return

    for line_num, raw in section.lines:
        if not raw.strip():
            if current_op is not None and payloads:
                payloads.append("")
            continue
        if raw.startswith("+"):
            if current_op is None:
                errors.append(
                    f"line {line_num}: payload line with no preceding op header"
                )
                continue
            payloads.append(raw[1:])
            continue

        stripped = raw.strip()
        if stripped == "---" or stripped.startswith("#"):
            continue

        op = _try_parse_op(stripped)
        if op is not None:
            op["line_num"] = line_num
            emit()
            current_op = op
            continue

        if current_op is not None and payloads:
            payloads.append(stripped)
            continue
        errors.append(f"line {line_num}: unrecognised row: {stripped!r}")

    emit()
    return edits, file_op, errors


# ---- Merge sections for the same path ----

def _merge_same_path(files: list[FileEdits]) -> list[FileEdits]:
    grouped: dict[str, list[FileEdits]] = {}
    order: list[str] = []
    for file_edits in files:
        if file_edits.rel_path not in grouped:
            grouped[file_edits.rel_path] = []
            order.append(file_edits.rel_path)
        grouped[file_edits.rel_path].append(file_edits)

    merged: list[FileEdits] = []
    for path in order:
        group = grouped[path]
        if len(group) == 1:
            merged.append(group[0])
            continue
        all_edits: list[Edit] = []
        tag: str | None = None
        file_op: FileOp | None = None
        for piece in group:
            all_edits.extend(piece.edits)
            tag = tag or piece.tag
            file_op = file_op or piece.file_op
        merged.append(FileEdits(path, tag, tuple(all_edits), file_op))
    return merged


# ---- Public API ----

def parse_edits(text: str) -> ParseResult:
    lines = text.splitlines()
    sections = _split_sections(lines)
    files: list[FileEdits] = []
    errors: list[str] = []

    for section in sections:
        edits, file_op, section_errors = _execute_section(section)
        errors.extend(section_errors)
        if edits or file_op is not None:
            files.append(
                FileEdits(
                    rel_path=section.path,
                    tag=section.tag,
                    edits=tuple(edits),
                    file_op=file_op,
                )
            )

    return ParseResult(tuple(_merge_same_path(files)), tuple(errors))
