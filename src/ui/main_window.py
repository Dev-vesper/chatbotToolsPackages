from __future__ import annotations

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QStackedWidget, QWidget

from config import APP_NAME
from tools import TOOL_PAGES
from ui.components import Sidebar


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1240, 800)
        self.setMinimumSize(980, 620)

        self._stack = QStackedWidget()
        self._pages = [page_class() for page_class in TOOL_PAGES]
        for page in self._pages:
            self._stack.addWidget(page)

        sidebar = Sidebar([page.title for page in self._pages])
        sidebar.tool_selected.connect(self._stack.setCurrentIndex)

        root = QWidget()
        root.setObjectName("AppRoot")
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(sidebar)
        layout.addWidget(self._stack, 1)
        self.setCentralWidget(root)

    def closeEvent(self, event: QCloseEvent) -> None:
        for page in self._pages:
            shutdown = getattr(page, "shutdown", None)
            if callable(shutdown):
                shutdown()
        super().closeEvent(event)
