from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QThreadPool, QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QWidget,
)

from core.ignore import DEFAULT_IGNORE_PATTERNS
from core.models import FileEntry, ScanResult, SourceFile
from tools.cer_1.src.file_tree import FileTreeWidget
from tools.cer_1.src.formatter import FormatOptions, FormatResult, format_files
from tools.cer_1.src.ignore_dialog import IgnoreDialog
from tools.cer_1.src.sources import ContentReader
from ui.components import Card, EmptyState, ToolPage, make_button
from utils.gitignore import IgnoreMatcher
from utils.scanner import scan_project
from utils.tasks import CancelToken, Task


def _run_scan(root: Path, patterns: tuple[str, ...], token: CancelToken) -> ScanResult:
    return scan_project(root, IgnoreMatcher(patterns), lambda: token.cancelled)


def _run_preview(
    sources: tuple[SourceFile, ...],
    reader: ContentReader,
    options: FormatOptions,
    token: CancelToken,
) -> FormatResult | None:
    entries: list[FileEntry] = []
    for source in sources:
        if token.cancelled:
            return None
        entry = reader.read(source)
        if entry is not None:
            entries.append(entry)
    if token.cancelled:
        return None
    return format_files(entries, options)


class Cer1Page(ToolPage):
    title = "CER-1"
    subtitle = (
        "Codebase Export & Reference — select files and build a line-numbered prompt "
        "for precise AI edits."
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project: Path | None = None
        self._files: tuple[SourceFile, ...] = ()
        self._patterns: list[str] = list(DEFAULT_IGNORE_PATTERNS)
        self._reader: ContentReader | None = None
        self._output = ""
        self._scanning = False
        self._rendering = False
        self._pending_checked: set[str] = set()

        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(2)
        self._tasks: set[Task] = set()
        self._scan_seq = 0
        self._preview_seq = 0
        self._scan_token = CancelToken()
        self._preview_token = CancelToken()

        self._build_ui()

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(250)
        self._preview_timer.timeout.connect(self._start_preview)

        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self._reset_flash)
        self._flash_button: QPushButton | None = None
        self._flash_text = ""

        self._clear_output(
            "No output yet",
            "Open a project and select files to build the prompt.",
        )
        self._update_actions()

    def _build_ui(self) -> None:
        project_bar = QHBoxLayout()
        project_bar.setSpacing(8)
        self._project_label = QLabel("No project selected")
        self._project_label.setObjectName("ProjectName")
        self._project_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._rescan_button = make_button("Rescan", "ghost")
        self._rescan_button.clicked.connect(self._rescan)
        open_button = make_button("Open Project…", "primary")
        open_button.clicked.connect(self._choose_project)
        project_bar.addWidget(self._project_label)
        project_bar.addStretch(1)
        project_bar.addWidget(self._rescan_button)
        project_bar.addWidget(open_button)
        self.body_layout.addLayout(project_bar)

        files_card = Card("Files")
        self._all_button = make_button("All", "ghost")
        self._none_button = make_button("None", "ghost")
        self._ignore_button = make_button("Ignore…")
        self._all_button.clicked.connect(lambda: self._tree.set_all(True))
        self._none_button.clicked.connect(lambda: self._tree.set_all(False))
        self._ignore_button.clicked.connect(self._edit_ignore)
        files_card.actions.addWidget(self._all_button)
        files_card.actions.addWidget(self._none_button)
        files_card.actions.addWidget(self._ignore_button)

        self._files_stat = QLabel("0 files")
        self._files_stat.setObjectName("Stat")
        self._tree = FileTreeWidget()
        self._tree.selection_changed.connect(self._schedule_preview)
        self._files_empty = EmptyState(
            "No project selected",
            "Open a folder to scan its files.",
        )
        self._files_stack = QStackedWidget()
        self._files_stack.addWidget(self._tree)
        self._files_stack.addWidget(self._files_empty)
        files_card.content.addWidget(self._files_stat)
        files_card.content.addWidget(self._files_stack, 1)

        preview_card = Card("Output")
        self._copy_button = make_button("Copy", "ghost")
        self._export_button = make_button("Export", "primary")
        self._copy_button.clicked.connect(self._copy)
        self._export_button.clicked.connect(self._export)
        preview_card.actions.addWidget(self._copy_button)
        preview_card.actions.addWidget(self._export_button)

        options_row = QHBoxLayout()
        options_row.setSpacing(14)
        self._edit_skill_check = QCheckBox("Edit Skill prompt")
        self._align_check = QCheckBox("Align line numbers")
        self._separators_check = QCheckBox("Separators")
        self._edit_skill_check.setChecked(True)
        self._separators_check.setChecked(True)
        for check in (self._edit_skill_check, self._align_check, self._separators_check):
            check.toggled.connect(self._schedule_preview)
            options_row.addWidget(check)
        options_row.addStretch(1)

        self._output_stat = QLabel("0 files · 0 lines · ~0 tokens")
        self._output_stat.setObjectName("Stat")
        self._preview = QPlainTextEdit()
        self._preview.setObjectName("Preview")
        self._preview.setReadOnly(True)
        self._preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._preview_empty = EmptyState(
            "Nothing selected",
            "Check files in the tree to build the output.",
        )
        self._preview_stack = QStackedWidget()
        self._preview_stack.addWidget(self._preview)
        self._preview_stack.addWidget(self._preview_empty)

        preview_card.content.addLayout(options_row)
        preview_card.content.addWidget(self._output_stat)
        preview_card.content.addWidget(self._preview_stack, 1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(files_card)
        splitter.addWidget(preview_card)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([430, 530])
        self.body_layout.addWidget(splitter, 1)

    def load_project(self, path: Path) -> None:
        self._project = Path(path)
        name = self._project.name or str(self._project)
        self._project_label.setText(name)
        self._project_label.setToolTip(str(self._project))
        self._reader = ContentReader()
        self._files = ()
        self._tree.set_files(())
        self._clear_output(
            "No output yet",
            "Select files in the tree to build the prompt.",
        )
        self._start_scan(preserve=set())

    def _choose_project(self) -> None:
        start = str(self._project) if self._project is not None else str(Path.home())
        directory = QFileDialog.getExistingDirectory(self, "Open project", start)
        if directory:
            self.load_project(Path(directory))

    def _edit_ignore(self) -> None:
        dialog = IgnoreDialog(self._patterns, self)
        if not dialog.exec():
            return
        patterns = dialog.patterns()
        if patterns == self._patterns:
            return
        self._patterns = patterns
        if self._project is not None:
            self._start_scan(preserve=set(self._tree.checked_rel_paths()))

    def _rescan(self) -> None:
        if self._project is not None:
            self._start_scan(preserve=set(self._tree.checked_rel_paths()))

    def _start_scan(self, preserve: set[str]) -> None:
        if self._project is None:
            return

        self._preview_timer.stop()
        self._preview_token.cancel()
        self._preview_seq += 1
        self._rendering = False

        self._scan_token.cancel()
        token = CancelToken()
        self._scan_token = token
        self._scan_seq += 1
        sequence = self._scan_seq
        self._pending_checked = preserve
        self._scanning = True
        self._files = ()
        self._tree.set_files(())
        self._clear_output(
            "Scanning project…",
            "Selected files will return after the scan.",
        )
        self._files_stat.setText("Scanning…")
        self._files_empty.set_text(
            "Scanning project…",
            "Reading files and applying ignore patterns.",
        )
        self._files_stack.setCurrentWidget(self._files_empty)
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
        self._tree.set_files(self._files, self._pending_checked)
        self._pending_checked = set()

        if self._files:
            stat = f"{len(self._files):,} files"
            if result.skipped:
                stat += f" · {result.skipped:,} skipped"
            self._files_stat.setText(stat)
            self._files_stack.setCurrentWidget(self._tree)
        else:
            self._files_stat.setText("0 files")
            self._files_empty.set_text(
                "No files found",
                "The ignore list hides everything in this folder.",
            )
            self._files_stack.setCurrentWidget(self._files_empty)

        self._update_actions()
        self._schedule_preview()

    def _on_scan_error(self, sequence: int, message: str) -> None:
        if sequence != self._scan_seq:
            return
        self._scanning = False
        self._files = ()
        self._tree.set_files(())
        self._files_stat.setText("Scan failed")
        self._files_empty.set_text("Could not scan project", message)
        self._files_stack.setCurrentWidget(self._files_empty)
        self._clear_output("No output yet", "Open another project or rescan.")
        self._update_actions()

    def _schedule_preview(self, *_: object) -> None:
        if self._scanning:
            return
        if self._project is not None and self._files:
            self._rendering = True
            if self._output:
                self._output_stat.setText("Rendering…")
            self._update_actions()
        self._preview_timer.start()

    def _start_preview(self) -> None:
        if self._project is None:
            self._rendering = False
            self._clear_output(
                "No output yet",
                "Open a project and select files to build the prompt.",
            )
            return

        sources = tuple(self._tree.checked_sources())
        if not sources:
            self._rendering = False
            self._preview_token.cancel()
            self._preview_seq += 1
            self._clear_output(
                "Nothing selected",
                "Check files in the tree to build the output.",
            )
            return

        options = FormatOptions(
            include_edit_skill=self._edit_skill_check.isChecked(),
            align_line_numbers=self._align_check.isChecked(),
            include_separators=self._separators_check.isChecked(),
        )
        if self._reader is None:
            self._reader = ContentReader()

        self._preview_token.cancel()
        token = CancelToken()
        self._preview_token = token
        self._preview_seq += 1
        sequence = self._preview_seq
        self._rendering = True
        self._output_stat.setText("Rendering…")
        self._update_actions()

        task = Task(_run_preview, sources, self._reader, options, token)
        self._track_task(
            task,
            lambda result: self._on_preview_done(sequence, result),
            lambda message: self._on_preview_error(sequence, message),
        )

    def _on_preview_done(self, sequence: int, result: FormatResult | None) -> None:
        if sequence != self._preview_seq:
            return
        self._rendering = False
        if result is None:
            self._update_actions()
            return
        if not result.text:
            self._clear_output(
                "No readable files",
                "The selected files could not be read.",
            )
            return
        self._output = result.text
        self._preview.setPlainText(result.text)
        self._preview_stack.setCurrentWidget(self._preview)
        self._output_stat.setText(
            f"{result.file_count:,} files · {result.line_count:,} lines · "
            f"~{result.token_estimate:,} tokens"
        )
        self._update_actions()

    def _on_preview_error(self, sequence: int, message: str) -> None:
        if sequence != self._preview_seq:
            return
        self._rendering = False
        self._clear_output("Could not build output", message)

    def _clear_output(self, title: str, message: str) -> None:
        self._rendering = False
        self._output = ""
        self._preview.clear()
        self._preview_empty.set_text(title, message)
        self._preview_stack.setCurrentWidget(self._preview_empty)
        self._output_stat.setText("0 files · 0 lines · ~0 tokens")
        self._update_actions()

    def _copy(self) -> None:
        if not self._output:
            return
        QApplication.clipboard().setText(self._output)
        self._flash(self._copy_button, "Copied")

    def _export(self) -> None:
        if not self._output or self._project is None:
            return
        default = self._project / f"{self._project.name or 'codebase'}_codebase.txt"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export codebase",
            str(default),
            "Text files (*.txt);;Markdown files (*.md);;All files (*)",
        )
        if not path:
            return
        try:
            Path(path).write_text(self._output, encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        self._flash(self._export_button, "Exported")

    def _update_actions(self) -> None:
        has_project = self._project is not None
        available = bool(self._files) and not self._scanning
        self._all_button.setEnabled(available)
        self._none_button.setEnabled(available)
        self._ignore_button.setEnabled(has_project)
        self._rescan_button.setEnabled(has_project and not self._scanning)
        ready = bool(self._output) and not self._rendering and not self._scanning
        self._copy_button.setEnabled(ready)
        self._export_button.setEnabled(ready)

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
        self._preview_token.cancel()
        self._preview_timer.stop()
        self._pool.waitForDone(2000)
