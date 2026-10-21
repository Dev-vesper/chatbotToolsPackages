from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QThreadPool, QTimer, Qt
from PySide6.QtGui import QBrush, QColor, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QWidget,
)

from core.ignore import DEFAULT_IGNORE_PATTERNS
from core.models import ScanResult, SourceFile
from tools.cer_3.src.formatter import FormatOptions, format_results
from tools.cer_3.src.results import SearchResultsWidget
from tools.cer_3.src.searcher import SearchResult, search_project
from ui.components import Card, EmptyState, ToolPage, make_button
from ui.theme import COLORS
from utils.gitignore import IgnoreMatcher
from utils.scanner import scan_project
from utils.tasks import CancelToken, Task


def _run_scan(root: Path, patterns: tuple[str, ...], token: CancelToken) -> ScanResult:
    return scan_project(root, IgnoreMatcher(patterns), lambda: token.cancelled)


def _run_search(
    files: tuple[SourceFile, ...],
    query: str,
    regex: bool,
    case_sensitive: bool,
    token: CancelToken,
) -> SearchResult:
    return search_project(
        files,
        query,
        regex=regex,
        case_sensitive=case_sensitive,
        token=token,
    )


class Cer3Page(ToolPage):
    title = "CER-3"
    subtitle = (
        "Codebase Search & Focus — find code by text or regex and export a focused "
        "prompt with only the relevant sections."
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project: Path | None = None
        self._files: tuple[SourceFile, ...] = ()
        self._results: SearchResult | None = None
        self._patterns: list[str] = list(DEFAULT_IGNORE_PATTERNS)
        self._scanning = False

        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(2)
        self._tasks: set[Task] = set()
        self._scan_seq = 0
        self._scan_token = CancelToken()
        self._search_seq = 0
        self._search_token = CancelToken()

        self._build_ui()

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._start_search)

        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self._reset_flash)
        self._flash_button: QPushButton | None = None
        self._flash_text = ""

        self._clear_preview(
            "Nothing to preview",
            "Search the project to see matches.",
        )
        self._update_actions()

    def _build_ui(self) -> None:
        project_bar = QHBoxLayout()
        project_bar.setSpacing(8)
        self._project_label = QLabel("No project selected")
        self._project_label.setObjectName("ProjectName")
        self._project_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._rescan_button = make_button("Rescan", "ghost")
        self._rescan_button.clicked.connect(self._rescan)
        open_button = make_button("Open Project…", "primary")
        open_button.clicked.connect(self._choose_project)
        project_bar.addWidget(self._project_label)
        project_bar.addStretch(1)
        project_bar.addWidget(self._rescan_button)
        project_bar.addWidget(open_button)
        self.body_layout.addLayout(project_bar)

        search_card = Card("Search")
        self._query = QLineEdit()
        self._query.setPlaceholderText("Search text or pattern…")
        self._query.textChanged.connect(self._on_query_changed)
        search_card.content.addWidget(self._query)

        options_row = QHBoxLayout()
        options_row.setSpacing(12)
        self._regex_check = QCheckBox("Regex")
        self._case_check = QCheckBox("Case sensitive")
        self._regex_check.toggled.connect(self._on_query_changed)
        self._case_check.toggled.connect(self._on_query_changed)
        options_row.addWidget(self._regex_check)
        options_row.addWidget(self._case_check)
        options_row.addStretch(1)
        self._results_stat = QLabel("")
        self._results_stat.setObjectName("Stat")
        options_row.addWidget(self._results_stat)
        search_card.content.addLayout(options_row)

        self._results_widget = SearchResultsWidget()
        self._results_widget.file_activated.connect(self._preview_file)
        self._results_widget.selection_changed.connect(self._update_actions)
        self._results_empty = EmptyState(
            "No results",
            "Type a query to search the project.",
        )
        self._results_stack = QStackedWidget()
        self._results_stack.addWidget(self._results_widget)
        self._results_stack.addWidget(self._results_empty)
        search_card.content.addWidget(self._results_stack, 1)

        preview_card = Card("Preview")
        self._preview_path = QLabel("")
        self._preview_path.setObjectName("ProjectPath")
        preview_card.content.addWidget(self._preview_path)
        self._preview = QPlainTextEdit()
        self._preview.setObjectName("Preview")
        self._preview.setReadOnly(True)
        self._preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        preview_card.content.addWidget(self._preview, 1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(search_card)
        splitter.addWidget(preview_card)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([380, 580])
        self.body_layout.addWidget(splitter, 1)

        actions = QHBoxLayout()
        actions.setSpacing(14)
        context_label = QLabel("Context:")
        context_label.setObjectName("Muted")
        self._context_spin = QSpinBox()
        self._context_spin.setRange(0, 20)
        self._context_spin.setValue(2)
        self._context_spin.setFixedWidth(60)
        self._full_files_check = QCheckBox("Full files")
        self._edit_skill_check = QCheckBox("Edit Skill prompt")
        self._edit_skill_check.setChecked(True)
        self._select_all_button = make_button("Select all", "ghost")
        self._select_all_button.clicked.connect(
            lambda: self._results_widget.set_all(True)
        )
        self._select_none_button = make_button("None", "ghost")
        self._select_none_button.clicked.connect(
            lambda: self._results_widget.set_all(False)
        )
        self._export_button = make_button("Export", "primary")
        self._export_button.clicked.connect(self._export)

        actions.addWidget(context_label)
        actions.addWidget(self._context_spin)
        actions.addWidget(self._full_files_check)
        actions.addWidget(self._edit_skill_check)
        actions.addStretch(1)
        actions.addWidget(self._select_all_button)
        actions.addWidget(self._select_none_button)
        actions.addWidget(self._export_button)
        self.body_layout.addLayout(actions)

    def load_project(self, path: Path) -> None:
        path = Path(path)
        project_changed = self._project != path
        self._project = path
        self._project_label.setText(path.name or str(path))
        self._project_label.setToolTip(str(path))
        if project_changed:
            self._search_timer.stop()
            self._query.blockSignals(True)
            self._query.clear()
            self._query.blockSignals(False)
            self._results = None
            self._results_widget.set_results(())
            self._results_stat.setText("")
            self._clear_preview(
                "Nothing to preview",
                "Search the project to see matches.",
            )
        self._start_scan()

    def _choose_project(self) -> None:
        start = str(self._project) if self._project is not None else str(Path.home())
        directory = QFileDialog.getExistingDirectory(self, "Open project", start)
        if directory:
            self.load_project(Path(directory))

    def _rescan(self) -> None:
        if self._project is not None:
            self._start_scan()

    def _start_scan(self) -> None:
        if self._project is None:
            return

        self._search_timer.stop()
        self._search_token.cancel()
        self._search_seq += 1

        self._scan_token.cancel()
        token = CancelToken()
        self._scan_token = token
        self._scan_seq += 1
        sequence = self._scan_seq
        self._scanning = True
        self._files = ()
        self._results = None
        self._results_widget.set_results(())
        self._results_stat.setText("Scanning…")
        self._results_empty.set_text(
            "Scanning project…",
            "Reading files and applying ignore patterns.",
        )
        self._results_stack.setCurrentWidget(self._results_empty)
        self._clear_preview(
            "Nothing to preview",
            "Search the project to see matches.",
        )
        self._update_actions()

        task = Task(_run_scan, self._project, tuple(self._patterns), token)
        self._track_task(
            task,
            lambda result: self._on_scan_done(sequence, result),
            lambda message: self._on_scan_error(sequence, message),
        )

    def _on_scan_done(self, sequence: int, result: ScanResult) -> None:
        if sequence != self._scan_seq:
            return
        self._scanning = False
        if result.cancelled:
            self._update_actions()
            return
        self._files = result.files
        self._results_stat.setText(f"{len(self._files):,} files")
        self._update_actions()
        self._schedule_search()

    def _on_scan_error(self, sequence: int, message: str) -> None:
        if sequence != self._scan_seq:
            return
        self._scanning = False
        self._files = ()
        self._results_stat.setText("Scan failed")
        self._results_empty.set_text("Could not scan project", message)
        self._results_stack.setCurrentWidget(self._results_empty)
        self._update_actions()

    def _on_query_changed(self, *_: object) -> None:
        self._schedule_search()

    def _schedule_search(self) -> None:
        if self._scanning:
            return
        self._search_token.cancel()
        if not self._query.text().strip():
            self._search_timer.stop()
            self._search_seq += 1
            self._results = None
            self._results_widget.set_results(())
            self._results_stat.setText(
                f"{len(self._files):,} files" if self._files else ""
            )
            self._results_empty.set_text(
                "No results",
                "Type a query to search the project.",
            )
            self._results_stack.setCurrentWidget(self._results_empty)
            self._clear_preview(
                "Nothing to preview",
                "Search the project to see matches.",
            )
            self._update_actions()
            return
        self._search_timer.start()

    def _start_search(self) -> None:
        if self._project is None:
            return
        if not self._files:
            self._results = None
            self._results_widget.set_results(())
            self._results_stat.setText("0 files")
            self._results_empty.set_text(
                "No files",
                "The project has no readable files.",
            )
            self._results_stack.setCurrentWidget(self._results_empty)
            self._clear_preview(
                "Nothing to preview",
                "The project has no readable files.",
            )
            self._update_actions()
            return

        self._search_token.cancel()
        token = CancelToken()
        self._search_token = token
        self._search_seq += 1
        sequence = self._search_seq
        self._results_stat.setText("Searching…")
        self._results_empty.set_text(
            "Searching project…",
            "Matching files against the query.",
        )
        self._results_stack.setCurrentWidget(self._results_empty)

        task = Task(
            _run_search,
            self._files,
            self._query.text(),
            self._regex_check.isChecked(),
            self._case_check.isChecked(),
            token,
        )
        self._track_task(
            task,
            lambda result: self._on_search_done(sequence, result),
            lambda message: self._on_search_error(sequence, message),
        )

    def _on_search_done(self, sequence: int, result: SearchResult) -> None:
        if sequence != self._search_seq:
            return
        if result.cancelled:
            return
        if result.error:
            self._results = None
            self._results_stat.setText("Search failed")
            self._results_empty.set_text("Search failed", result.error)
            self._results_stack.setCurrentWidget(self._results_empty)
            self._update_actions()
            return

        self._results = result
        self._results_widget.set_results(result.files)
        if result.files:
            self._results_stat.setText(
                f"{len(result.files):,} files · {result.total_matches:,} matches"
            )
            self._results_stack.setCurrentWidget(self._results_widget)
            self._preview_file(result.files[0].source.rel_path)
        else:
            self._results_stat.setText("0 matches")
            self._results_empty.set_text("No matches", "Try a different query.")
            self._results_stack.setCurrentWidget(self._results_empty)
            self._clear_preview("No matches", "Try a different query.")
        self._update_actions()

    def _on_search_error(self, sequence: int, message: str) -> None:
        if sequence != self._search_seq:
            return
        self._results = None
        self._results_stat.setText("Search failed")
        self._results_empty.set_text("Search failed", message)
        self._results_stack.setCurrentWidget(self._results_empty)
        self._update_actions()

    def _preview_file(self, rel_path: str) -> None:
        if self._results is None:
            return
        fm = next(
            (f for f in self._results.files if f.source.rel_path == rel_path),
            None,
        )
        if fm is None:
            return

        self._preview_path.setText(rel_path)
        self._preview_path.setToolTip(rel_path)
        self._preview.setPlainText(fm.content)

        document = self._preview.document()
        highlight = QBrush(QColor(COLORS["selection"]))
        extras: list[QTextEdit.ExtraSelection] = []
        for match in fm.matches:
            block = document.findBlockByNumber(match.line_number - 1)
            if not block.isValid():
                continue
            selection = QTextEdit.ExtraSelection()
            selection.cursor = QTextCursor(block)
            selection.format.setBackground(highlight)
            extras.append(selection)
        self._preview.setExtraSelections(extras)

        if fm.matches:
            first_block = document.findBlockByNumber(fm.matches[0].line_number - 1)
            if first_block.isValid():
                self._preview.setTextCursor(QTextCursor(first_block))
                self._preview.centerCursor()

    def _clear_preview(self, title: str, message: str) -> None:
        self._preview_path.setText("")
        self._preview_path.setToolTip("")
        self._preview.setExtraSelections([])
        self._preview.setPlainText("")
        self._preview.setPlaceholderText(f"{title} — {message}")

    def _export(self) -> None:
        if self._results is None or not self._results.files:
            return
        checked = set(self._results_widget.checked_paths())
        selected = [
            fm for fm in self._results.files if fm.source.rel_path in checked
        ]
        if not selected:
            self._flash(self._export_button, "Nothing selected")
            return

        options = FormatOptions(
            context_lines=self._context_spin.value(),
            include_edit_skill=self._edit_skill_check.isChecked(),
            full_files=self._full_files_check.isChecked(),
        )
        result = format_results(selected, options)
        if not result.text:
            return
        QApplication.clipboard().setText(result.text)
        self._flash(self._export_button, "Copied")

    def _update_actions(self) -> None:
        has_project = self._project is not None
        has_results = bool(self._results and self._results.files)
        has_checked = has_results and bool(self._results_widget.checked_paths())
        self._rescan_button.setEnabled(has_project and not self._scanning)
        self._query.setEnabled(has_project and not self._scanning)
        self._select_all_button.setEnabled(has_results)
        self._select_none_button.setEnabled(has_results)
        self._export_button.setEnabled(has_checked)

    def _track_task(
        self,
        task: Task,
        on_done: Callable[[object], None],
        on_error: Callable[[str], None],
    ) -> None:
        self._tasks.add(task)

        def handle_done(result: object) -> None:
            self._tasks.discard(task)
            on_done(result)

        def handle_error(message: str) -> None:
            self._tasks.discard(task)
            on_error(message)

        task.signals.done.connect(handle_done)
        task.signals.error.connect(handle_error)
        self._pool.start(task)

    def _flash(self, button: QPushButton, text: str) -> None:
        self._flash_timer.stop()
        if self._flash_button is not None:
            self._flash_button.setText(self._flash_text)
        self._flash_button = button
        self._flash_text = button.text()
        button.setText(text)
        self._flash_timer.start(1400)

    def _reset_flash(self) -> None:
        if self._flash_button is not None:
            self._flash_button.setText(self._flash_text)
        self._flash_button = None

    def shutdown(self) -> None:
        self._scan_token.cancel()
        self._search_token.cancel()
        self._search_timer.stop()
        self._flash_timer.stop()
        self._pool.waitForDone(2000)
