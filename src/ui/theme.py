from __future__ import annotations

from string import Template

from PySide6.QtGui import QColor, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication, QWidget

COLORS: dict[str, str] = {
    "bg": "#12100e",
    "sidebar": "#161311",
    "surface": "#1a1714",
    "surface_alt": "#211d19",
    "surface_hover": "#26211c",
    "border": "#2e2924",
    "border_strong": "#3a342d",
    "text": "#ece7e1",
    "text_muted": "#9b9186",
    "text_dim": "#6f675e",
    "selection": "#2f2a24",
    "primary_bg": "#ece7e1",
    "primary_hover": "#f7f3ed",
    "primary_pressed": "#ddd6cc",
    "primary_text": "#15120f",
    "preview_bg": "#0e0c0a",
    "scroll": "#3a342d",
    "add_bg": "#18221b",
    "add_border": "#2f4a39",
    "add_text": "#a9c8ae",
    "add_marker": "#7fb28c",
    "add_chip_bg": "#1b2a20",
    "add_chip_text": "#b7d7bd",
    "del_bg": "#251a18",
    "del_border": "#503630",
    "del_text": "#d5ada5",
    "del_marker": "#c68d82",
    "del_chip_bg": "#2b1d1a",
    "del_chip_text": "#e3bcb4",
    "warn_bg": "#282218",
    "warn_border": "#4c3f28",
    "warn_text": "#d8c59e",
}

_MONO_CANDIDATES = ("JetBrains Mono", "Fira Code", "Cascadia Code", "DejaVu Sans Mono")


def _mono_family() -> str:
    available = set(QFontDatabase.families())
    for family in _MONO_CANDIDATES:
        if family in available:
            return family
    return QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family()


def _build_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(COLORS["bg"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(COLORS["surface"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(COLORS["surface_alt"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(COLORS["surface_alt"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(COLORS["primary_bg"]))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(COLORS["surface_alt"]))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.Link, QColor(COLORS["text_muted"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(COLORS["selection"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(COLORS["text_dim"]))
    palette.setColor(QPalette.ColorRole.Light, QColor(COLORS["border_strong"]))
    palette.setColor(QPalette.ColorRole.Midlight, QColor(COLORS["border"]))
    palette.setColor(QPalette.ColorRole.Mid, QColor(COLORS["border"]))
    palette.setColor(QPalette.ColorRole.Dark, QColor(COLORS["bg"]))
    palette.setColor(QPalette.ColorRole.Shadow, QColor("#0b0a08"))

    disabled = QPalette.ColorGroup.Disabled
    palette.setColor(disabled, QPalette.ColorRole.WindowText, QColor(COLORS["text_dim"]))
    palette.setColor(disabled, QPalette.ColorRole.Text, QColor(COLORS["text_dim"]))
    palette.setColor(disabled, QPalette.ColorRole.ButtonText, QColor(COLORS["text_dim"]))
    palette.setColor(disabled, QPalette.ColorRole.Base, QColor(COLORS["surface"]))
    return palette


_QSS = Template(
    """
QWidget {
    color: $text;
    font-size: 13px;
}

QMainWindow, QDialog, QWidget#AppRoot {
    background-color: $bg;
}

QFrame#Sidebar {
    background-color: $sidebar;
    border-right: 1px solid $border;
}

QLabel {
    background-color: transparent;
}

QLabel#BrandMark {
    background-color: $primary_bg;
    color: $primary_text;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 700;
}

QLabel#BrandTitle {
    color: $text;
    font-size: 14px;
    font-weight: 600;
}

QLabel#BrandSub {
    color: $text_dim;
    font-size: 11px;
}

QLabel#NavLabel {
    color: $text_dim;
    font-size: 10px;
    font-weight: 600;
}

QListWidget#Nav {
    background-color: transparent;
    border: none;
    outline: 0;
}

QListWidget#Nav::item {
    color: $text_muted;
    border-radius: 6px;
    padding: 8px 10px;
    margin: 1px 0;
}

QListWidget#Nav::item:hover {
    background-color: $surface_alt;
    color: $text;
}

QListWidget#Nav::item:selected {
    background-color: $selection;
    color: $text;
}

QLabel#PageTitle {
    color: $text;
    font-size: 22px;
    font-weight: 600;
}

QLabel#PageSubtitle {
    color: $text_muted;
    font-size: 12px;
}

QLabel#SectionTitle {
    color: $text;
    font-size: 12px;
    font-weight: 600;
}

QLabel#ProjectName {
    color: $text;
    font-size: 13px;
    font-weight: 600;
}

QLabel#Muted {
    color: $text_muted;
    font-size: 12px;
}

QLabel#Stat {
    color: $text_dim;
    font-size: 11px;
}

QLabel#EmptyTitle {
    color: $text_muted;
    font-size: 13px;
    font-weight: 600;
}

QLabel#DialogTitle {
    color: $text;
    font-size: 16px;
    font-weight: 600;
}

QLabel#Badge {
    background-color: $surface_alt;
    color: $text_dim;
    border: 1px solid $border;
    border-radius: 4px;
    padding: 1px 6px;
    font-size: 10px;
    font-weight: 600;
}

QLabel#Chip {
    background-color: $surface_alt;
    color: $text_muted;
    border: 1px solid $border;
    border-radius: 8px;
    padding: 2px 8px;
    font-size: 10px;
    font-weight: 600;
}

QLabel#Chip[variant="add"] {
    background-color: $add_chip_bg;
    color: $add_chip_text;
    border-color: $add_border;
}

QLabel#Chip[variant="del"] {
    background-color: $del_chip_bg;
    color: $del_chip_text;
    border-color: $del_border;
}

QLabel#Chip[variant="warn"] {
    background-color: $warn_bg;
    color: $warn_text;
    border-color: $warn_border;
}

QFrame#Banner {
    border-radius: 6px;
}

QFrame#Banner[variant="warning"] {
    background-color: $warn_bg;
    border: 1px solid $warn_border;
}

QFrame#Banner[variant="error"] {
    background-color: $del_chip_bg;
    border: 1px solid $del_border;
}

QLabel#BannerText {
    color: $warn_text;
    font-size: 11px;
}

QLabel#BannerText[variant="error"] {
    color: $del_chip_text;
}

QLabel#Status {
    font-size: 11px;
}

QLabel#Status[variant="success"] {
    color: $add_chip_text;
}

QLabel#Status[variant="error"] {
    color: $del_chip_text;
}

QLabel#Status[variant="neutral"] {
    color: $text_muted;
}

QLabel#ProjectPath {
    color: $text_dim;
    font-size: 11px;
}

QFrame#Card {
    background-color: $surface;
    border: 1px solid $border;
    border-radius: 8px;
}

QFrame#Divider {
    background-color: $border;
    border: none;
}

QPushButton {
    background-color: $surface_alt;
    color: $text;
    border: 1px solid $border;
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 12px;
}

QPushButton:hover {
    background-color: $surface_hover;
    border-color: $border_strong;
}

QPushButton:pressed {
    background-color: $selection;
}

QPushButton:focus {
    border-color: $border_strong;
}

QPushButton:disabled {
    background-color: $surface;
    color: $text_dim;
    border-color: $border;
}

QPushButton[variant="primary"] {
    background-color: $primary_bg;
    color: $primary_text;
    border: 1px solid $primary_bg;
    font-weight: 600;
}

QPushButton[variant="primary"]:hover {
    background-color: $primary_hover;
    border-color: $primary_hover;
}

QPushButton[variant="primary"]:pressed {
    background-color: $primary_pressed;
    border-color: $primary_pressed;
}

QPushButton[variant="primary"]:disabled {
    background-color: $surface_alt;
    color: $text_dim;
    border-color: $border;
}

QPushButton[variant="ghost"] {
    background-color: transparent;
    color: $text_muted;
    border: 1px solid transparent;
    padding: 5px 8px;
}

QPushButton[variant="ghost"]:hover {
    background-color: $surface_alt;
    color: $text;
    border-color: transparent;
}

QPushButton[variant="ghost"]:pressed {
    background-color: $selection;
}

QLineEdit, QPlainTextEdit {
    background-color: $preview_bg;
    color: $text;
    border: 1px solid $border;
    border-radius: 6px;
    padding: 6px 9px;
    selection-background-color: $selection;
    selection-color: $text;
}

QLineEdit:focus, QPlainTextEdit:focus {
    border-color: $border_strong;
}

QLineEdit:disabled, QPlainTextEdit:disabled {
    color: $text_dim;
}

QPlainTextEdit#Preview {
    background-color: $preview_bg;
    border: 1px solid $border;
    border-radius: 6px;
    padding: 12px;
    font-family: "$mono";
    font-size: 12px;
}

QPlainTextEdit#PatternEditor {
    font-family: "$mono";
    font-size: 12px;
}

QPlainTextEdit#DiffView {
    background-color: $preview_bg;
    border: 1px solid $border;
    border-radius: 6px;
    padding: 6px 8px;
    font-family: "$mono";
    font-size: 12px;
}

QListWidget#FileList {
    background-color: transparent;
    border: none;
    outline: 0;
}

QTreeWidget {
    background-color: transparent;
    border: none;
    color: $text;
    font-size: 12px;
    outline: 0;
}

QTreeWidget::item {
    border-radius: 4px;
    padding: 2px 2px;
}

QTreeWidget::item:hover {
    background-color: $surface_alt;
}

QTreeWidget::item:selected {
    background-color: $selection;
    color: $text;
}

QTreeView::indicator, QCheckBox::indicator {
    background-color: $bg;
    border: 1px solid $border_strong;
    border-radius: 3px;
    width: 13px;
    height: 13px;
}

QTreeView::indicator:hover, QCheckBox::indicator:hover {
    border-color: $text_muted;
}

QTreeView::indicator:checked, QCheckBox::indicator:checked {
    background-color: $text;
    border-color: $text;
}

QTreeView::indicator:indeterminate, QCheckBox::indicator:indeterminate {
    background-color: $text_dim;
    border-color: $text_dim;
}

QHeaderView::section {
    background-color: transparent;
    color: $text_dim;
    border: none;
    border-bottom: 1px solid $border;
    padding: 5px 3px;
    font-size: 10px;
    font-weight: 600;
}

QSplitter::handle {
    background-color: transparent;
}

QSplitter::handle:hover {
    background-color: $border;
}

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background-color: $scroll;
    border-radius: 5px;
    min-height: 24px;
}

QScrollBar::handle:vertical:hover {
    background-color: $border_strong;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}

QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 0;
}

QScrollBar::handle:horizontal {
    background-color: $scroll;
    border-radius: 5px;
    min-width: 24px;
}

QScrollBar::handle:horizontal:hover {
    background-color: $border_strong;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: transparent;
}

QToolTip {
    background-color: $surface_alt;
    color: $text;
    border: 1px solid $border;
    padding: 4px 6px;
}
"""
)


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setPalette(_build_palette())
    app.setStyleSheet(_QSS.substitute({**COLORS, "mono": _mono_family()}))


def repolish(widget: QWidget) -> None:
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()
