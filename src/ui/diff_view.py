from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtGui import (
    QColor,
    QFont,
    QTextBlock,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import QPlainTextEdit, QWidget

from core.models import FileDiff
from ui.theme import COLORS


def _format(color: str, *, bold: bool = False) -> QTextCharFormat:
    fmt = QTextCharFormat()
    fmt.setForeground(QColor(COLORS[color]))
    if bold:
        fmt.setFontWeight(QFont.Weight.DemiBold)
    return fmt


class DiffView(QPlainTextEdit):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("DiffView")
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setUndoRedoEnabled(False)

        self._file_blocks: dict[str, QTextBlock] = {}

        self._header_path = _format("text", bold=True)
        self._header_add = _format("add_marker", bold=True)
        self._header_del = _format("del_marker", bold=True)
        self._hunk = _format("text_dim")
        self._number = _format("text_dim")
        self._del_number = _format("del_marker")
        self._add_number = _format("add_marker")
        self._context = _format("text_muted")
        self._del_marker = _format("del_marker", bold=True)
        self._add_marker = _format("add_marker", bold=True)
        self._del_text = _format("del_text")
        self._add_text = _format("add_text")

    def set_diffs(self, diffs: Sequence[FileDiff]) -> None:
        self._file_blocks.clear()
        self.clear()
        if not diffs:
            return

        document = self.document()
        document.setUndoRedoEnabled(False)
        cursor = QTextCursor(document)
        cursor.beginEditBlock()
        started = False

        def next_block(block_format: QTextBlockFormat | None = None) -> None:
            nonlocal started
            block_format = block_format or QTextBlockFormat()
            if started:
                cursor.insertBlock(block_format)
            else:
                cursor.setBlockFormat(block_format)
                started = True

        for diff_index, diff in enumerate(diffs):
            if diff_index:
                next_block()
                cursor.insertText("")

            header_format = QTextBlockFormat()
            header_format.setBackground(QColor(COLORS["surface_alt"]))
            header_format.setLeftMargin(4)
            header_format.setTopMargin(4)
            header_format.setBottomMargin(4)
            next_block(header_format)
            cursor.insertText(diff.rel_path, self._header_path)
            cursor.insertText("   ")
            cursor.insertText(f"+{diff.additions}", self._header_add)
            cursor.insertText("  ")
            cursor.insertText(f"\u2212{diff.deletions}", self._header_del)
            self._file_blocks[diff.rel_path] = cursor.block()

            numbers = [
                number
                for line in diff.lines
                for number in (line.old_number, line.new_number)
                if number is not None
            ]
            width = max(3, max((len(str(number)) for number in numbers), default=0))

            for line in diff.lines:
                if line.kind == "hunk":
                    hunk_format = QTextBlockFormat()
                    hunk_format.setTopMargin(6)
                    hunk_format.setBottomMargin(2)
                    next_block(hunk_format)
                    cursor.insertText(line.text, self._hunk)
                    continue

                block_format = QTextBlockFormat()
                if line.kind == "add":
                    block_format.setBackground(QColor(COLORS["add_bg"]))
                elif line.kind == "del":
                    block_format.setBackground(QColor(COLORS["del_bg"]))
                next_block(block_format)

                old_number = str(line.old_number) if line.old_number is not None else ""
                new_number = str(line.new_number) if line.new_number is not None else ""
                old_format = self._del_number if line.kind == "del" else self._number
                new_format = self._add_number if line.kind == "add" else self._number
                cursor.insertText(f"{old_number:>{width}} ", old_format)
                cursor.insertText(f"{new_number:>{width}} ", new_format)

                if line.kind == "add":
                    cursor.insertText("+ ", self._add_marker)
                    cursor.insertText(line.text, self._add_text)
                elif line.kind == "del":
                    cursor.insertText("- ", self._del_marker)
                    cursor.insertText(line.text, self._del_text)
                else:
                    cursor.insertText("  ", self._context)
                    cursor.insertText(line.text, self._context)

        cursor.endEditBlock()
        self.setTextCursor(QTextCursor(document))
        self.verticalScrollBar().setValue(0)

    def clear_diffs(self) -> None:
        self._file_blocks.clear()
        self.clear()

    def scroll_to_file(self, rel_path: str) -> None:
        block = self._file_blocks.get(rel_path)
        if block is None:
            return
        self.setTextCursor(QTextCursor(block))
        self.centerCursor()
