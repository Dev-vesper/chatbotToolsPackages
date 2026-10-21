from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from config import APP_NAME, VERSION
from ui.theme import repolish


def make_button(text: str, variant: str = "default", parent: QWidget | None = None) -> QPushButton:
    button = QPushButton(text, parent)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    if variant != "default":
        button.setProperty("variant", variant)
    return button


class ToolPage(QWidget):
    title = ""
    subtitle = ""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(18)

        header = QVBoxLayout()
        header.setSpacing(4)
        title = QLabel(self.title)
        title.setObjectName("PageTitle")
        subtitle = QLabel(self.subtitle)
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        header.addWidget(title)
        header.addWidget(subtitle)
        root.addLayout(header)

        self.body_layout = QVBoxLayout()
        self.body_layout.setSpacing(14)
        root.addLayout(self.body_layout, 1)


class Sidebar(QFrame):
    tool_selected = Signal(int)

    def __init__(self, tool_titles: Sequence[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(224)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 20, 16, 16)
        layout.setSpacing(14)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        mark = QLabel("CT")
        mark.setObjectName("BrandMark")
        mark.setFixedSize(28, 28)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)

        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        name = QLabel(APP_NAME)
        name.setObjectName("BrandTitle")
        tagline = QLabel("Prompt toolkit")
        tagline.setObjectName("BrandSub")
        brand_text.addWidget(name)
        brand_text.addWidget(tagline)

        brand.addWidget(mark)
        brand.addLayout(brand_text, 1)
        layout.addLayout(brand)

        nav_label = QLabel("TOOLS")
        nav_label.setObjectName("NavLabel")
        layout.addWidget(nav_label)

        self._nav = QListWidget()
        self._nav.setObjectName("Nav")
        self._nav.setCursor(Qt.CursorShape.PointingHandCursor)
        self._nav.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for title in tool_titles:
            self._nav.addItem(QListWidgetItem(title))
        self._nav.currentRowChanged.connect(self.tool_selected.emit)
        self._nav.setCurrentRow(0)
        layout.addWidget(self._nav)
        layout.addStretch(1)

        version = QLabel(f"v{VERSION}")
        version.setObjectName("Muted")
        layout.addWidget(version)


class Card(QFrame):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(6)
        heading = QLabel(title)
        heading.setObjectName("SectionTitle")
        header.addWidget(heading)
        header.addStretch(1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(4)
        header.addLayout(self.actions)
        layout.addLayout(header)

        divider = QFrame()
        divider.setObjectName("Divider")
        divider.setFixedHeight(1)
        layout.addWidget(divider)

        self.content = QVBoxLayout()
        self.content.setSpacing(10)
        layout.addLayout(self.content, 1)


class EmptyState(QWidget):
    def __init__(self, title: str, message: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(6)
        layout.addStretch(1)

        heading = QLabel(title)
        heading.setObjectName("EmptyTitle")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body = QLabel(message)
        body.setObjectName("Muted")
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.setWordWrap(True)

        layout.addWidget(heading)
        layout.addWidget(body)
        layout.addStretch(1)

        self._heading = heading
        self._body = body

    def set_text(self, title: str, message: str) -> None:
        self._heading.setText(title)
        self._body.setText(message)


class Chip(QLabel):
    def __init__(
        self,
        text: str = "",
        variant: str = "neutral",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.setObjectName("Chip")
        self.setProperty("variant", variant)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

    def set_variant(self, variant: str) -> None:
        if self.property("variant") == variant:
            return
        self.setProperty("variant", variant)
        repolish(self)


class Banner(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Banner")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(0)
        self._text = QLabel()
        self._text.setObjectName("BannerText")
        self._text.setWordWrap(True)
        layout.addWidget(self._text)
        self.hide()

    def show_message(self, text: str, variant: str = "warning") -> None:
        if self.property("variant") != variant:
            self.setProperty("variant", variant)
            self._text.setProperty("variant", variant)
            repolish(self)
            repolish(self._text)
        self._text.setText(text)
        self.show()

    def clear_message(self) -> None:
        self._text.clear()
        self.hide()
