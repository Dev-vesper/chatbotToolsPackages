from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QThreadPool, QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QSplitter,
    QStackedWidget,
    QWidget,
)

from core.ignore import DEFAULT_IGNORE_PATTERNS
from core.models import ScanResult, SourceFile
from tools.cer_2.src.parser import parse_edits
from tools.cer_2.src.patch import apply_edits, build_diff
from ui.components import Card, EmptyState, ToolPage, make_button
from utils.gitignore import IgnoreMatcher
from utils.scanner import scan_project
from utils.tasks import CancelToken, Task


def _run_scan(root: Path, patterns: tuple[str, ...], token: CancelToken) -> ScanResult:
    return scan_project(root, IgnoreMatcher(patterns), lambda: token.cancelled)


class Cer2Page(ToolPage):
    title = "CER-2"
    subtitle = (
        "Codebase Edit Resolver — paste AI line edits and apply them to your "
        "files with a diff preview."
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project: Path | None = None
        self._files: tuple[SourceFile, ...] = ()
        self._by_path: dict[str, SourceFile] = {}
        self._patterns: list[str] = list(DEFAULT_IGNORE_PATTERNS)
        self._scanning = False
        self._pending: dict[str, tuple[str, str, str]] = {}
        self._parse_errors: list[str] = []
        self._apply_warnings: list[str] = []

        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._tasks: set[Task] = set()
        self._scan_seq = 0
        self._scan_token = CancelToken()

        self._build_ui()

        self._parse_timer = QTimer(self)
        self._parse_timer.setSingleShot(True)
        self._parse_timer.setInterval(200)
        self._parse_timer.timeout.connect(self._refresh_pending)

        self._clear_state("Open a project to load its files.")
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
        self._files_stat = QLabel("0 files")
        self._files_stat.setObjectName("Stat")
        self._file_view = QPlainTextEdit()
        self._file_view.setObjectName("Preview")
        self._file_view.setReadOnly(True)
        self._file_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._files_empty = EmptyState(
            "No project selected",
            "Open a folder to scan its files.",
        )
        self._files_stack = QStackedWidget()
        self._files_stack.addWidget(self._file_view)
        self._files_stack.addWidget(self._files_empty)
        files_card.content.addWidget(self._files_stat)
        files_card.content.addWidget(self._files_stack, 1)

        input_card = Card("AI response")
        hint = QLabel(
            "Paste the AI's edits. Separate files with `## path` headers, "
            "then one `<line number> <code>` per edited line."
        )
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        input_card.content.addWidget(hint)
        self._input = QPlainTextEdit()
        self._input.setObjectName("PatternEditor")
        self._input.setPlaceholderText("## src/utils/scanner.py\n42 new code")
        self._input.textChanged.connect(self._on_input_changed)
        input_card.content.addWidget(self._input, 1)

        preview_card = Card("Diff preview")
        self._copy_diff_button = make_button("Copy diff", "ghost")
        self._copy_diff_button.clicked.connect(self._copy_diff)
        preview_card.actions.addWidget(self._copy_diff_button)
        self._preview_stat = QLabel("")
        self._preview_stat.setObjectName("Stat")
        self._preview = QPlainTextEdit()
        self._preview.setObjectName("Preview")
        self._preview.setReadOnly(True)
        self._preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._preview_empty = EmptyState(
            "Nothing to preview",
            "Paste edits above to see a diff.",
        )
        self._preview_stack = QStackedWidget()
        self._preview_stack.addWidget(self._preview)
        self._preview_stack.addWidget(self._preview_empty)
        preview_card.content.addWidget(self._preview_stat)
        preview_card.content.addWidget(self._preview_stack, 1)

        right_split = QSplitter(Qt.Orientation.Vertical)
        right_split.addWidget(input_card)
        right_split.addWidget(preview_card)
        right_split.setStretchFactor(0, 1)
        right_split.setStretchFactor(1, 2)
        right_split.setSizes([240, 420])

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(files_card)
        splitter.addWidget(right_split)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 5)
        splitter.setSizes([280, 720])
        self.body_layout.addWidget(splitter, 1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self._status = QLabel("")
        self._status.setObjectName("Stat")
        self._discard_button = make_button("Discard", "ghost")
        self._discard_button.clicked.connect(self._discard)
        self._apply_button = make_button("Apply edits", "primary")
        self._apply_button.clicked.connect(self._apply)
        actions.addWidget(self._status)
        actions.addStretch(1)
        actions.addWidget(self._discard_button)
        actions.addWidget(self._apply_button)
        self.body_layout.addLayout(actions)

    def load_project(self, path: Path) -> None:
        self._project = Path(path)
        name = self._project.name or str(self._project)
        self._project_label.setText(name)
        self._project_label.setToolTip(str(self._project))
        self._files = ()
        self._by_path = {}
        self._file_view.clear()
        self._clear_state("Scanning project…")
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
        self._scan_token.cancel()
        token = CancelToken()
        self._scan_token = token
        self._scan_seq += 1
        sequence = self._scan_seq
        self._scanning = True
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
        self._by_path = {source.rel_path: source for source in self._files}
        if self._files:
            stat = f"{len(self._files):,} files"
            if result.skipped:
                stat += f" · {result.skipped:,} skipped"
            self._files_stat.setText(stat)
            self._file_view.setPlainText(
                "\n".join(source.rel_path for source in self._files)
            )
            self._files_stack.setCurrentWidget(self._file_view)
        else:
            self._files_stat.setText("0 files")
            self._files_empty.set_text(
                "No files found",
                "The ignore list hides everything in this folder.",
            )
            self._files_stack.setCurrentWidget(self._files_empty)
        self._refresh_pending()
        self._update_actions()

    def _on_scan_error(self, sequence: int, message: str) -> None:
        if sequence != self._scan_seq:
            return
        self._scanning = False
        self._files = ()
        self._by_path = {}
        self._files_stat.setText("Scan failed")
        self._files_empty.set_text("Could not scan project", message)
        self._files_stack.setCurrentWidget(self._files_empty)
        self._refresh_pending()
        self._update_actions()

    def _on_input_changed(self) -> None:
        self._parse_timer.start()

    def _refresh_pending(self) -> None:
        self._pending.clear()
        self._parse_errors = []
        self._apply_warnings = []
        text = self._input.toPlainText()
        if text.strip():
            parsed = parse_edits(text)
            self._parse_errors.extend(parsed.errors)
            for file_edits in parsed.files:
                source = self._by_path.get(file_edits.rel_path)
                if source is None:
                    self._apply_warnings.append(
                        f"Unknown file (not in project): {file_edits.rel_path}"
                    )
                    continue
                try:
                    original = source.path.read_text(encoding="utf-8", errors="replace")
                except OSError as exc:
                    self._apply_warnings.append(f"{file_edits.rel_path}: {exc}")
                    continue
                new_text, warnings = apply_edits(original, file_edits.edits)
                self._apply_warnings.extend(
                    f"{file_edits.rel_path}: {warning}" for warning in warnings
                )
                if new_text == original:
                    continue
                diff = build_diff(file_edits.rel_path, original, new_text)
                self._pending[file_edits.rel_path] = (original, new_text, diff)
        self._refresh_preview()
        self._update_actions()

    def _refresh_preview(self) -> None:
        if not self._pending and not self._parse_errors and not self._apply_warnings:
            self._preview.clear()
            self._preview_empty.set_text(
                "Nothing to preview",
                "Paste edits above to see a diff.",
            )
            self._preview_stack.setCurrentWidget(self._preview_empty)
            self._preview_stat.setText("")
            return
        parts = [diff for _o, _n, diff in self._pending.values() if diff]
        body = "\n".join(parts)
        if self._parse_errors:
            body += ("\n\n" if body else "") + "Parse errors:\n" + "\n".join(
                f"  - {error}" for error in self._parse_errors
            )
        if self._apply_warnings:
            body += ("\n\n" if body else "") + "Warnings:\n" + "\n".join(
                f"  - {warning}" for warning in self._apply_warnings
            )
        self._preview.setPlainText(body)
        self._preview_stack.setCurrentWidget(self._preview)
        if self._pending:
            changed = sum(
                1
                for _o, _n, diff in self._pending.values()
                for line in diff.splitlines()
                if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
            )
            self._preview_stat.setText(
                f"{len(self._pending):,} file(s) · {changed:,} changed line(s)"
            )
        else:
            self._preview_stat.setText("No applicable changes")

    def _discard(self) -> None:
        self._parse_timer.stop()
        self._input.blockSignals(True)
        self._input.clear()
        self._input.blockSignals(False)
        self._pending.clear()
        self._parse_errors = []
        self._apply_warnings = []
        self._refresh_preview()
        self._update_actions()
        self._status.setText("Discarded")

    def _apply(self) -> None:
        if not self._pending:
            return
        changed_on_disk: list[str] = []
        for rel_path, (original, _new, _diff) in self._pending.items():
            source = self._by_path.get(rel_path)
            if source is None:
                continue
            try:
                current = source.path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if current != original:
                changed_on_disk.append(rel_path)
        message = f"Apply edits to {len(self._pending)} file(s)?"
        if changed_on_disk:
            message += (
                "\n\nWarning: these files changed on disk since parsing:\n"
                + "\n".join(f"  - {path}" for path in changed_on_disk)
            )
        reply = QMessageBox.question(
            self,
            "Apply edits",
            message,
            QMessageBox.StandardButton.Apply | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Apply,
        )
        if reply != QMessageBox.StandardButton.Apply:
            return
        errors: list[str] = []
        for rel_path, (_original, new, _diff) in self._pending.items():
            source = self._by_path.get(rel_path)
            if source is None:
                continue
            try:
                source.path.write_text(new, encoding="utf-8")
            except OSError as exc:
                errors.append(f"{rel_path}: {exc}")
        if errors:
            QMessageBox.critical(
                self,
                "Apply failed",
                "Some files could not be written:\n\n" + "\n".join(errors),
            )
        else:
            self._status.setText(f"Applied edits to {len(self._pending):,} file(s)")
        self._pending.clear()
        self._parse_timer.stop()
        self._refresh_preview()
        self._update_actions()

    def _copy_diff(self) -> None:
        if not self._pending:
            return
        text = "\n".join(diff for _o, _n, diff in self._pending.values())
        QApplication.clipboard().setText(text)
        self._status.setText("Diff copied")

    def _clear_state(self, message: str) -> None:
        self._pending.clear()
        self._parse_errors = []
        self._apply_warnings = []
        self._status.setText("")
        self._preview.clear()
        self._preview_empty.set_text("Nothing to preview", message)
        self._preview_stack.setCurrentWidget(self._preview_empty)
        self._preview_stat.setText("")

    def _update_actions(self) -> None:
        has_project = self._project is not None
        self._rescan_button.setEnabled(has_project and not self._scanning)
        self._apply_button.setEnabled(bool(self._pending) and not self._scanning)
        self._discard_button.setEnabled(
            bool(self._pending)
            or bool(self._parse_errors)
            or bool(self._apply_warnings)
        )
        self._copy_diff_button.setEnabled(bool(self._pending))

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

    def shutdown(self) -> None:
        self._scan_token.cancel()
        self._parse_timer.stop()
        self._pool.waitForDone(2000)
