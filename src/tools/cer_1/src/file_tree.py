from __future__ import annotations

from collections.abc import Iterable, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)

from core.models import SourceFile

_ROLE_SOURCE = Qt.ItemDataRole.UserRole
_ROLE_IS_DIR = Qt.ItemDataRole.UserRole + 1

_CHECKED = Qt.CheckState.Checked
_UNCHECKED = Qt.CheckState.Unchecked
_PARTIAL = Qt.CheckState.PartiallyChecked


def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


class FileTreeWidget(QTreeWidget):
    selection_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setColumnCount(2)
        self.setHeaderLabels(["FILE", "SIZE"])
        header = self.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(False)
        self.setUniformRowHeights(True)
        self.setIndentation(14)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setExpandsOnDoubleClick(True)

        self._file_items: list[QTreeWidgetItem] = []
        self._updating = False
        self.itemChanged.connect(self._on_item_changed)

    def set_files(self, files: Sequence[SourceFile], checked: Iterable[str] = ()) -> None:
        checked_set = set(checked)
        self._updating = True
        self.setUpdatesEnabled(False)
        try:
            self.clear()
            self._file_items.clear()

            directories: dict[str, QTreeWidgetItem] = {}
            dir_paths = sorted(
                {"/".join(source.rel_path.split("/")[:-1]) for source in files if "/" in source.rel_path},
                key=str.lower,
            )
            for dir_path in dir_paths:
                parent = self.invisibleRootItem()
                prefix = ""
                for part in dir_path.split("/"):
                    prefix = part if not prefix else f"{prefix}/{part}"
                    item = directories.get(prefix)
                    if item is None:
                        item = QTreeWidgetItem(parent)
                        item.setText(0, part)
                        item.setToolTip(0, prefix)
                        item.setFlags(
                            Qt.ItemFlag.ItemIsEnabled
                            | Qt.ItemFlag.ItemIsSelectable
                            | Qt.ItemFlag.ItemIsUserCheckable
                            | Qt.ItemFlag.ItemIsAutoTristate
                        )
                        item.setCheckState(0, _UNCHECKED)
                        item.setData(0, _ROLE_IS_DIR, True)
                        directories[prefix] = item
                    parent = item

            for source in files:
                parts = source.rel_path.split("/")
                parent = self.invisibleRootItem()
                prefix = ""
                for part in parts[:-1]:
                    prefix = part if not prefix else f"{prefix}/{part}"
                    parent = directories.get(prefix, parent)

                item = QTreeWidgetItem(parent)
                item.setText(0, parts[-1])
                item.setText(1, _format_size(source.size))
                item.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                item.setToolTip(0, source.rel_path)
                item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsUserCheckable
                )
                item.setCheckState(0, _CHECKED if source.rel_path in checked_set else _UNCHECKED)
                item.setData(0, _ROLE_SOURCE, source)
                item.setData(0, _ROLE_IS_DIR, False)
                self._file_items.append(item)

            self._recompute_dir_states()
        finally:
            self.setUpdatesEnabled(True)
            self._updating = False

        self.expandToDepth(0)

    def checked_sources(self) -> list[SourceFile]:
        return [
            source
            for item in self._file_items
            if item.checkState(0) == _CHECKED and (source := item.data(0, _ROLE_SOURCE))
        ]

    def checked_rel_paths(self) -> list[str]:
        return [source.rel_path for source in self.checked_sources()]

    def set_all(self, checked: bool) -> None:
        if not self._file_items:
            return
        state = _CHECKED if checked else _UNCHECKED
        self._updating = True
        try:
            for item in self._file_items:
                item.setCheckState(0, state)
            self._recompute_dir_states()
        finally:
            self._updating = False
        self.selection_changed.emit()

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._updating or column != 0:
            return
        state = item.checkState(0)
        if item.data(0, _ROLE_IS_DIR) and state != _PARTIAL:
            self._updating = True
            try:
                self._set_descendants(item, state)
                self._recompute_dir_states()
            finally:
                self._updating = False
        self.selection_changed.emit()

    def _set_descendants(self, item: QTreeWidgetItem, state: Qt.CheckState) -> None:
        for index in range(item.childCount()):
            child = item.child(index)
            child.setCheckState(0, state)
            self._set_descendants(child, state)

    def _recompute_dir_states(self) -> None:
        updating = self._updating
        self._updating = True
        try:
            for index in range(self.topLevelItemCount()):
                self._recompute_item(self.topLevelItem(index))
        finally:
            self._updating = updating

    def _recompute_item(self, item: QTreeWidgetItem) -> None:
        if not item.data(0, _ROLE_IS_DIR):
            return
        states: list[Qt.CheckState] = []
        for index in range(item.childCount()):
            child = item.child(index)
            self._recompute_item(child)
            states.append(child.checkState(0))
        if not states or all(state == _UNCHECKED for state in states):
            state = _UNCHECKED
        elif all(state == _CHECKED for state in states):
            state = _CHECKED
        else:
            state = _PARTIAL
        item.setCheckState(0, state)
