from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QThreadPool, QTimer, Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.hashline import compute_tag
from core.ignore import DEFAULT_IGNORE_PATTERNS
from core.models import FileDiff, ScanResult, SourceFile
from tools.cer_2.src.file_list import FileListWidget
from tools.cer_2.src.parser import parse_edits
from tools.cer_2.src.patch import apply_edits, build_file_diff, diff_to_text
from ui.components import Banner, Card, Chip, EmptyState, ToolPage, make_button
from ui.diff_view import DiffView
from ui.theme import repolish
from utils.fs import write_text_atomic
from utils.gitignore import IgnoreMatcher
from utils.scanner import scan_project
from utils.tasks import CancelToken, Task


def _plural(count: int, noun: str) -> str:
    return f"{count:,} {noun}" + ("" if count == 1 else "s")


def _run_scan(root: Path, patterns: tuple[str, ...], token: CancelToken) -> ScanResult:
    return scan_project(root, IgnoreMatcher(patterns), lambda: token.cancelled)


@dataclass(frozen=True, slots=True)
class PendingEdit:
    rel_path: str
    original: str
    new_text: str
    diff_text: str
    diff: FileDiff


class Cer2Page(ToolPage):
    title = "CER-2"
    subtitle = (
        "Codebase Edit Resolver — paste AI Hashline patches and apply them to "
        "your files with a before/after diff preview."
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project: Path | None = None
        self._files: tuple[SourceFile, ...] = ()
        self._by_path: dict[str, SourceFile] = {}
        self._skipped = 0
        self._patterns: list[str] = list(DEFAULT_IGNORE_PATTERNS)
        self._scanning = False
        self._pending: dict[str, PendingEdit] = {}
        self._parse_errors: list[str] = []
        self._apply_warnings: list[str] = []
        self._parsed_files = 0
        self._parsed_edits = 0

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

        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(lambda: self._set_status(""))

        self._reset_parse_chips()
        self._clear_preview(
            "Nothing to preview",
            "Open a project, then paste the AI's Hashline patches above.",
        )
        self._update_actions()

    def _build_ui(self) -> None:
        project_bar = QHBoxLayout()
        project_bar.setSpacing(10)
        project_info = QVBoxLayout()
        project_info.setSpacing(1)
        self._project_label = QLabel("No project selected")
        self._project_label.setObjectName("ProjectName")
        self._project_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._project_path = QLabel("Open a folder to begin")
        self._project_path.setObjectName("ProjectPath")
        self._project_path.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._project_path.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        project_info.addWidget(self._project_label)
        project_info.addWidget(self._project_path)
        project_bar.addLayout(project_info, 1)

        self._project_stat = Chip("0 files")
        self._project_stat.hide()
        self._rescan_button = make_button("Rescan", "ghost")
        self._rescan_button.clicked.connect(self._rescan)
        open_button = make_button("Open Project…", "primary")
        open_button.clicked.connect(self._choose_project)
        project_bar.addWidget(self._project_stat)
        project_bar.addWidget(self._rescan_button)
        project_bar.addWidget(open_button)
        self.body_layout.addLayout(project_bar)

        files_card = Card("Files")
        self._files_stat = QLabel("0 files")
        self._files_stat.setObjectName("Stat")
        self._file_list = FileListWidget()
        self._file_list.file_clicked.connect(self._scroll_to_file)
        self._files_empty = EmptyState(
            "No project selected",
            "Open a folder to scan its files.",
        )
        self._files_stack = QStackedWidget()
        self._files_stack.addWidget(self._file_list)
        self._files_stack.addWidget(self._files_empty)
        files_card.content.addWidget(self._files_stat)
        files_card.content.addWidget(self._files_stack, 1)

        input_card = Card("AI response")
        self._paste_button = make_button("Paste", "ghost")
        self._paste_button.clicked.connect(self._paste)
        self._clear_button = make_button("Clear", "ghost")
        self._clear_button.clicked.connect(self._clear_input)
        input_card.actions.addWidget(self._paste_button)
        input_card.actions.addWidget(self._clear_button)

        hint = QLabel(
            "Separate files with `[path#TAG]` headers, where `TAG` is the "
            "4-hex snapshot from the source prompt. Use `PUT N.=M:` / `CUT "
            "N.=M` with `+` body lines; `PUT <N:` / `PUT >N:` insert before "
            "or after."
        )
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        input_card.content.addWidget(hint)

        self._input = QPlainTextEdit()
        self._input.setObjectName("PatternEditor")
        self._input.setPlaceholderText(
            "[src/utils/scanner.py#A1B2]\n"
            "PUT 42.=42:\n"
            "+new code"
        )
        self._input.textChanged.connect(self._on_input_changed)
        input_card.content.addWidget(self._input, 1)

        parse_row = QHBoxLayout()
        parse_row.setSpacing(6)
        self._parsed_files_chip = Chip("0 files")
        self._parsed_edits_chip = Chip("0 edits")
        self._parsed_issue_chip = Chip("", "warn")
        self._parsed_issue_chip.hide()
        parse_row.addWidget(self._parsed_files_chip)
        parse_row.addWidget(self._parsed_edits_chip)
        parse_row.addWidget(self._parsed_issue_chip)
        parse_row.addStretch(1)
        input_card.content.addLayout(parse_row)

        diff_card = Card("Diff preview")
        self._copy_diff_button = make_button("Copy diff", "ghost")
        self._copy_diff_button.clicked.connect(self._copy_diff)
        diff_card.actions.addWidget(self._copy_diff_button)

        summary_row = QHBoxLayout()
        summary_row.setSpacing(6)
        self._diff_files_chip = Chip("0 files")
        self._diff_add_chip = Chip("+0")
        self._diff_del_chip = Chip("−0")
        self._diff_hint = QLabel("− before · + after · click a file to jump")
        self._diff_hint.setObjectName("Stat")
        self._diff_hint.hide()
        summary_row.addWidget(self._diff_files_chip)
        summary_row.addWidget(self._diff_add_chip)
        summary_row.addWidget(self._diff_del_chip)
        summary_row.addStretch(1)
        summary_row.addWidget(self._diff_hint)
        diff_card.content.addLayout(summary_row)

        self._banner = Banner()
        diff_card.content.addWidget(self._banner)

        self._diff_view = DiffView()
        self._diff_empty = EmptyState(
            "Nothing to preview",
            "Paste patches above to see a before/after diff.",
        )
        self._diff_stack = QStackedWidget()
        self._diff_stack.addWidget(self._diff_view)
        self._diff_stack.addWidget(self._diff_empty)
        diff_card.content.addWidget(self._diff_stack, 1)

        right_split = QSplitter(Qt.Orientation.Vertical)
        right_split.addWidget(input_card)
        right_split.addWidget(diff_card)
        right_split.setStretchFactor(0, 2)
        right_split.setStretchFactor(1, 3)
        right_split.setSizes([220, 480])

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(files_card)
        splitter.addWidget(right_split)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 5)
        splitter.setSizes([260, 740])
        self.body_layout.addWidget(splitter, 1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self._status = QLabel("")
        self._status.setObjectName("Status")
        self._status.setProperty("variant", "neutral")
        self._apply_button = make_button("Apply edits", "primary")
        self._apply_button.clicked.connect(self._apply)
        actions.addWidget(self._status)
        actions.addStretch(1)
        actions.addWidget(self._apply_button)
        self.body_layout.addLayout(actions)

    def load_project(self, path: Path) -> None:
        path = Path(path)
        project_changed = self._project != path
        self._project = path
        self._project_label.setText(path.name or str(path))
        self._project_label.setToolTip(str(path))
        self._project_path.setText(str(path))
        if project_changed:
            self._parse_timer.stop()
            self._input.blockSignals(True)
            self._input.clear()
            self._input.blockSignals(False)
            self._reset_parse_chips()
            self._set_status("")
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
        self._files = ()
        self._by_path = {}
        self._skipped = 0
        self._file_list.set_files(())
        self._project_stat.setText("Scanning…")
        self._project_stat.set_variant("neutral")
        self._project_stat.show()
        self._files_empty.set_text(
            "Scanning project…",
            "Reading files and applying ignore patterns.",
        )
        self._files_stack.setCurrentWidget(self._files_empty)
        self._clear_preview(
            "Scanning project…",
            "Edits will be checked again when the scan finishes.",
        )
        self._files_stat.setText("Scanning…")
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
        self._skipped = result.skipped
        self._file_list.set_files(self._files)
        if self._files:
            self._files_stack.setCurrentWidget(self._file_list)
            self._project_stat.setText(_plural(len(self._files), "file"))
            self._project_stat.setToolTip(
                f"{self._skipped:,} files skipped" if self._skipped else ""
            )
        else:
            self._files_stat.setText("0 files")
            self._files_empty.set_text(
                "No files found",
                "The ignore list hides everything in this folder.",
            )
            self._files_stack.setCurrentWidget(self._files_empty)
            self._project_stat.setText("0 files")
        self._refresh_pending()
        self._update_actions()

    def _on_scan_error(self, sequence: int, message: str) -> None:
        if sequence != self._scan_seq:
            return
        self._scanning = False
        self._files = ()
        self._by_path = {}
        self._file_list.set_files(())
        self._files_empty.set_text("Could not scan project", message)
        self._files_stack.setCurrentWidget(self._files_empty)
        self._project_stat.setText("Scan failed")
        self._project_stat.set_variant("warn")
        self._clear_preview("No preview", "Open another project or rescan.")
        self._refresh_pending()
        self._files_stat.setText("Scan failed")
        self._update_actions()

    def _on_input_changed(self) -> None:
        self._parse_timer.start()
        self._update_actions()

    def _refresh_pending(self) -> None:
        if self._scanning:
            return
        self._pending.clear()
        self._parse_errors = []
        self._apply_warnings = []
        self._parsed_files = 0
        self._parsed_edits = 0

        text = self._input.toPlainText()
        if text.strip():
            parsed = parse_edits(text)
            self._parse_errors.extend(parsed.errors)
            self._parsed_files = len(parsed.files)
            self._parsed_edits = parsed.edit_count
            for file_edits in parsed.files:
                if self._project is None:
                    continue
                source = self._by_path.get(file_edits.rel_path)
                if source is None:
                    self._apply_warnings.append(
                        f"Unknown file (not in project): {file_edits.rel_path}"
                    )
                    continue
                try:
                    original = source.path.read_text(
                        encoding="utf-8", errors="replace", newline=""
                    )
                except OSError as exc:
                    self._apply_warnings.append(f"{file_edits.rel_path}: {exc}")
                    continue

                if file_edits.tag:
                    current_tag = compute_tag(original)
                    if current_tag != file_edits.tag:
                        self._apply_warnings.append(
                            f"{file_edits.rel_path}: stale tag {file_edits.tag} "
                            f"(file is now {current_tag}). Re-read and retry."
                        )
                        continue
                else:
                    self._apply_warnings.append(
                        f"{file_edits.rel_path}: header has no #TAG; hashline "
                        "requires a tag for existing files."
                    )

                new_text, warnings = apply_edits(original, file_edits.edits)
                self._apply_warnings.extend(
                    f"{file_edits.rel_path}: {warning}" for warning in warnings
                )
                if new_text == original:
                    continue
                file_diff = build_file_diff(file_edits.rel_path, original, new_text)
                self._pending[file_edits.rel_path] = PendingEdit(
                    rel_path=file_edits.rel_path,
                    original=original,
                    new_text=new_text,
                    diff_text=diff_to_text(file_diff),
                    diff=file_diff,
                )

        self._refresh_parse_stats()
        self._refresh_preview()
        self._update_actions()

    def _refresh_parse_stats(self) -> None:
        self._parsed_files_chip.setText(_plural(self._parsed_files, "file"))
        self._parsed_edits_chip.setText(_plural(self._parsed_edits, "edit"))
        issues = len(self._parse_errors) + len(self._apply_warnings)
        if issues:
            self._parsed_issue_chip.setText(_plural(issues, "issue"))
            self._parsed_issue_chip.set_variant(
                "del" if self._parse_errors else "warn"
            )
            self._parsed_issue_chip.show()
        else:
            self._parsed_issue_chip.hide()

    def _issue_summary(self) -> tuple[str, str]:
        parts: list[str] = []
        variant = "warning"
        if self._parse_errors:
            variant = "error"
            shown = self._parse_errors[:5]
            text = "Unreadable edit lines:\n" + "\n".join(f"• {line}" for line in shown)
            if len(self._parse_errors) > len(shown):
                text += f"\n• and {len(self._parse_errors) - len(shown)} more"
            parts.append(text)
        if self._apply_warnings:
            shown = self._apply_warnings[:5]
            text = "Warnings:\n" + "\n".join(f"• {line}" for line in shown)
            if len(self._apply_warnings) > len(shown):
                text += f"\n• and {len(self._apply_warnings) - len(shown)} more"
            parts.append(text)
        return "\n\n".join(parts), variant

    def _refresh_preview(self) -> None:
        issue_text, issue_variant = self._issue_summary()
        if issue_text:
            self._banner.show_message(issue_text, issue_variant)
        else:
            self._banner.clear_message()

        pending = tuple(self._pending.values())
        additions = sum(edit.diff.additions for edit in pending)
        deletions = sum(edit.diff.deletions for edit in pending)
        self._set_diff_stats(len(pending), additions, deletions)
        self._update_file_stats()

        if pending:
            self._diff_view.set_diffs([edit.diff for edit in pending])
            self._diff_stack.setCurrentWidget(self._diff_view)
            self._diff_hint.show()
            return

        self._diff_view.clear_diffs()
        self._diff_hint.hide()
        if not self._input.toPlainText().strip():
            title, message = (
                "Nothing to preview",
                "Paste patches above to see a before/after diff.",
            )
        elif self._project is None:
            title, message = (
                "No project open",
                "Edits will resolve once a project is loaded.",
            )
        elif self._parsed_edits == 0:
            title, message = (
                "No edits found",
                "The response has no Hashline ops yet.",
            )
        elif issue_text:
            title, message = (
                "No applicable changes",
                "Fix the issues reported above to preview the edits.",
            )
        else:
            title, message = (
                "No changes",
                "These edits match the files on disk.",
            )
        self._diff_empty.set_text(title, message)
        self._diff_stack.setCurrentWidget(self._diff_empty)

    def _set_diff_stats(self, file_count: int, additions: int, deletions: int) -> None:
        self._diff_files_chip.setText(_plural(file_count, "file"))
        self._diff_add_chip.setText(f"+{additions:,}")
        self._diff_add_chip.set_variant("add" if additions else "neutral")
        self._diff_del_chip.setText(f"−{deletions:,}")
        self._diff_del_chip.set_variant("del" if deletions else "neutral")

    def _update_file_stats(self) -> None:
        stats = {
            edit.rel_path: (edit.diff.additions, edit.diff.deletions)
            for edit in self._pending.values()
        }
        self._file_list.set_stats(stats)
        if self._scanning:
            return
        summary = _plural(len(self._files), "file")
        if self._pending:
            summary += f" · {len(self._pending):,} edited"
        if self._skipped:
            summary += f" · {self._skipped:,} skipped"
        self._files_stat.setText(summary)

    def _scroll_to_file(self, rel_path: str) -> None:
        self._diff_view.scroll_to_file(rel_path)

    def _paste(self) -> None:
        text = QApplication.clipboard().text()
        if not text.strip():
            self._set_status("Clipboard is empty", "error")
            return
        if self._input.toPlainText().strip():
            self._input.appendPlainText(text)
        else:
            self._input.setPlainText(text)
        self._input.moveCursor(QTextCursor.MoveOperation.End)
        self._input.setFocus()
        self._set_status("Pasted from clipboard", "success")

    def _clear_input(self) -> None:
        self._parse_timer.stop()
        self._input.blockSignals(True)
        self._input.clear()
        self._input.blockSignals(False)
        self._reset_parse_chips()
        self._refresh_pending()
        self._set_status("Response cleared", "neutral")

    def _reset_parse_chips(self) -> None:
        self._parsed_files = 0
        self._parsed_edits = 0
        self._parsed_files_chip.setText("0 files")
        self._parsed_edits_chip.setText("0 edits")
        self._parsed_issue_chip.hide()

    def _apply(self) -> None:
        if not self._pending or self._scanning:
            return
        changed_on_disk: list[str] = []
        for rel_path, pending in self._pending.items():
            source = self._by_path.get(rel_path)
            if source is None:
                continue
            try:
                current = source.path.read_text(
                    encoding="utf-8", errors="replace", newline=""
                )
            except OSError:
                continue
            if current != pending.original:
                changed_on_disk.append(rel_path)

        message = f"Apply edits to {_plural(len(self._pending), 'file')}?"
        if changed_on_disk:
            message += (
                "\n\nWarning: these files changed on disk since the diff was built:\n"
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

        applied = 0
        errors: list[str] = []
        for rel_path, pending in list(self._pending.items()):
            source = self._by_path.get(rel_path)
            if source is None:
                errors.append(f"{rel_path}: file is no longer in the project")
                continue
            try:
                write_text_atomic(source.path, pending.new_text)
            except OSError as exc:
                errors.append(f"{rel_path}: {exc}")
            else:
                applied += 1

        self._refresh_pending()
        if errors:
            QMessageBox.critical(
                self,
                "Apply failed",
                "Some files could not be written:\n\n" + "\n".join(errors),
            )
            self._set_status(
                f"Applied {_plural(applied, 'file')} · {len(errors)} failed",
                "error",
            )
            return
        self._set_status(f"Applied edits to {_plural(applied, 'file')}", "success")

    def _copy_diff(self) -> None:
        if not self._pending:
            return
        text = "\n".join(edit.diff_text for edit in self._pending.values())
        QApplication.clipboard().setText(text)
        self._set_status("Diff copied to clipboard", "success")

    def _set_status(self, text: str, variant: str = "neutral") -> None:
        self._status.setText(text)
        if self._status.property("variant") != variant:
            self._status.setProperty("variant", variant)
            repolish(self._status)
        if text:
            self._status_timer.start(5000)
        else:
            self._status_timer.stop()

    def _clear_preview(self, title: str, message: str) -> None:
        self._pending.clear()
        self._diff_view.clear_diffs()
        self._diff_empty.set_text(title, message)
        self._diff_stack.setCurrentWidget(self._diff_empty)
        self._banner.clear_message()
        self._diff_hint.hide()
        self._set_diff_stats(0, 0, 0)
        self._update_file_stats()

    def _update_actions(self) -> None:
        has_project = self._project is not None
        busy = self._scanning
        self._rescan_button.setEnabled(has_project and not busy)
        self._apply_button.setEnabled(bool(self._pending) and not busy)
        self._copy_diff_button.setEnabled(bool(self._pending) and not busy)
        self._clear_button.setEnabled(
            bool(self._input.toPlainText())
            or bool(self._parse_errors)
            or bool(self._apply_warnings)
        )

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
        self._status_timer.stop()
        self._pool.waitForDone(2000)
