from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.ignore import DEFAULT_IGNORE_PATTERNS
from ui.components import make_button


class IgnoreDialog(QDialog):
    def __init__(self, patterns: Sequence[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Ignore patterns")
        self.resize(660, 500)
        self.setMinimumSize(560, 380)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        title = QLabel("Ignore patterns")
        title.setObjectName("DialogTitle")
        description = QLabel(
            "One pattern per line using .gitignore syntax. "
            "Matching files and folders are hidden from the tree."
        )
        description.setObjectName("Muted")
        description.setWordWrap(True)

        self._editor = QPlainTextEdit()
        self._editor.setObjectName("PatternEditor")
        self._editor.setPlainText("\n".join(patterns))

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        reset = make_button("Reset to defaults", "ghost")
        cancel = make_button("Cancel")
        save = make_button("Save", "primary")
        save.setDefault(True)
        reset.clicked.connect(self._reset)
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self.accept)
        buttons.addWidget(reset)
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(save)

        layout.addWidget(title)
        layout.addWidget(description)
        layout.addWidget(self._editor, 1)
        layout.addLayout(buttons)

    def patterns(self) -> list[str]:
        return [line.rstrip() for line in self._editor.toPlainText().splitlines() if line.strip()]

    def _reset(self) -> None:
        self._editor.setPlainText("\n".join(DEFAULT_IGNORE_PATTERNS))
