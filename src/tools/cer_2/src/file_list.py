from __future__ import annotations

from collections.abc import Mapping, Sequence

from PySide6.QtCore import QModelIndex, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QListWidget,
    QListWidgetItem,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QWidget,
)

from core.models import SourceFile
from ui.theme import COLORS

_PATH_ROLE = int(Qt.ItemDataRole.UserRole) + 1
_ADD_ROLE = int(Qt.ItemDataRole.UserRole) + 2
_DEL_ROLE = int(Qt.ItemDataRole.UserRole) + 3


class _FileDelegate(QStyledItemDelegate):
    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(0, 27)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = option.rect.adjusted(2, 1, -2, -1)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected or hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(
                QColor(COLORS["selection"] if selected else COLORS["surface_alt"])
            )
            painter.drawRoundedRect(rect, 5, 5)

        rel_path = str(index.data(_PATH_ROLE) or "")
        additions = int(index.data(_ADD_ROLE) or 0)
        deletions = int(index.data(_DEL_ROLE) or 0)
        changed = bool(additions or deletions)

        if changed:
            bar = QRect(rect.left() + 4, rect.top() + 5, 2, rect.height() - 10)
            painter.setPen(Qt.PenStyle.NoPen)
            if additions and deletions:
                half = bar.height() // 2
                painter.setBrush(QColor(COLORS["add_marker"]))
                painter.drawRect(QRect(bar.left(), bar.top(), bar.width(), half))
                painter.setBrush(QColor(COLORS["del_marker"]))
                painter.drawRect(
                    QRect(bar.left(), bar.top() + half, bar.width(), bar.height() - half)
                )
            else:
                painter.setBrush(
                    QColor(COLORS["add_marker"] if additions else COLORS["del_marker"])
                )
                painter.drawRoundedRect(bar, 1, 1)

        small = QFont(option.font)
        if small.pointSizeF() > 0:
            small.setPointSizeF(max(8.0, small.pointSizeF() - 1))
        else:
            small.setPixelSize(max(9, small.pixelSize() - 1))
        small.setWeight(QFont.Weight.DemiBold)
        painter.setFont(small)
        metrics = QFontMetrics(small)

        right = rect.right() - 9
        for text, color in (
            (f"\u2212{deletions}" if deletions else "", COLORS["del_marker"]),
            (f"+{additions}" if additions else "", COLORS["add_marker"]),
        ):
            if not text:
                continue
            width = metrics.horizontalAdvance(text)
            painter.setPen(QColor(color))
            painter.drawText(
                QRect(right - width, rect.top(), width, rect.height()),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                text,
            )
            right -= width + 7

        painter.setFont(option.font)
        painter.setPen(QColor(COLORS["text"] if changed else COLORS["text_muted"]))
        text_rect = QRect(rect.left() + 13, rect.top(), max(0, right - rect.left() - 16), rect.height())
        elided = QFontMetrics(option.font).elidedText(
            rel_path, Qt.TextElideMode.ElideMiddle, text_rect.width()
        )
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, elided)
        painter.restore()


class FileListWidget(QListWidget):
    file_clicked = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("FileList")
        self.setItemDelegate(_FileDelegate(self))
        self.setUniformItemSizes(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self._items: dict[str, QListWidgetItem] = {}
        self.itemClicked.connect(self._emit_path)

    def set_files(self, files: Sequence[SourceFile]) -> None:
        self.clear()
        self._items.clear()
        for source in files:
            item = QListWidgetItem()
            item.setData(_PATH_ROLE, source.rel_path)
            item.setData(_ADD_ROLE, 0)
            item.setData(_DEL_ROLE, 0)
            item.setToolTip(source.rel_path)
            self.addItem(item)
            self._items[source.rel_path] = item

    def set_stats(self, stats: Mapping[str, tuple[int, int]]) -> None:
        for rel_path, item in self._items.items():
            additions, deletions = stats.get(rel_path, (0, 0))
            if item.data(_ADD_ROLE) != additions:
                item.setData(_ADD_ROLE, additions)
            if item.data(_DEL_ROLE) != deletions:
                item.setData(_DEL_ROLE, deletions)
        self.viewport().update()

    def _emit_path(self, item: QListWidgetItem) -> None:
        rel_path = item.data(_PATH_ROLE)
        if rel_path:
            self.file_clicked.emit(str(rel_path))
