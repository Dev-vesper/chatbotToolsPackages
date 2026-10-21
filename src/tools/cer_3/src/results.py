from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)

from tools.cer_3.src.searcher import FileMatch

_ROLE_PATH = int(Qt.ItemDataRole.UserRole)
_CHECKED = Qt.CheckState.Checked


class SearchResultsWidget(QTreeWidget):
    file_activated = Signal(str)
    selection_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setColumnCount(2)
        self.setHeaderLabels(["FILE", "MATCHES"])
        header = self.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(False)
        self.setUniformRowHeights(True)
        self.setIndentation(0)
        self.setRootIsDecorated(False)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setExpandsOnDoubleClick(False)

        self._updating = False
        self.itemChanged.connect(self._on_item_changed)
        self.itemClicked.connect(self._on_item_clicked)

    def set_results(self, files: Sequence[FileMatch]) -> None:
        self._updating = True
        try:
            self.clear()
            for fm in files:
                item = QTreeWidgetItem(self)
                item.setText(0, fm.source.rel_path)
                item.setText(1, f"{len(fm.matches):,}")
                item.setData(0, _ROLE_PATH, fm.source.rel_path)
                item.setToolTip(0, fm.source.rel_path)
                item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsUserCheckable
                )
                item.setCheckState(0, _CHECKED)
        finally:
            self._updating = False
        self.selection_changed.emit()

    def checked_paths(self) -> list[str]:
        paths: list[str] = []
        for index in range(self.topLevelItemCount()):
            item = self.topLevelItem(index)
            if item.checkState(0) == _CHECKED:
                path = item.data(0, _ROLE_PATH)
                if path:
                    paths.append(str(path))
        return paths

    def set_all(self, checked: bool) -> None:
        if self.topLevelItemCount() == 0:
            return
        state = _CHECKED if checked else Qt.CheckState.Unchecked
        self._updating = True
        try:
            for index in range(self.topLevelItemCount()):
                self.topLevelItem(index).setCheckState(0, state)
        finally:
            self._updating = False
        self.selection_changed.emit()

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._updating or column != 0:
            return
        self.selection_changed.emit()

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        path = item.data(0, _ROLE_PATH)
        if path:
            self.file_activated.emit(str(path))
