# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

- Install dependencies: `.venv/bin/pip install "PySide6==6.8.3"`
- Run the app: `.venv/bin/python src/main.py`
- Syntax-check the tree: `.venv/bin/python -m compileall -q src`

There is no test suite, linter, or packaging configuration yet.

PySide6 must stay on 6.8.x for this machine: 6.9+ builds abort on import because the Core 2 Duo lacks SSE4.2/POPCNT. The README pins 6.8.3.

## Architecture

`src/` is the import root. Start the app with `python src/main.py`, not `python -m src.main`; shared imports are absolute from `src`: `ui.*`, `tools.*`, `core.*`, `utils.*`, `config`.

- `src/main.py` creates the `QApplication`, applies the theme, and shows `ui.main_window.MainWindow`.
- `src/ui/` is the shell and shared design system. `theme.py` is the only place colors/fonts/QSS may be defined; it also exposes `repolish()` for widgets whose `variant` property changes after construction. `components.py` holds primitives shared by every tool: `ToolPage` (title/subtitle header + `body_layout`), `Sidebar`, `Card`, `EmptyState`, `Chip`, `Banner`, and button factories. `diff_view.py` renders structured `FileDiff` data with colored add/remove blocks and before/after line numbers. Reusable UI belongs here, not inside a tool.
- `src/tools/__init__.py` is the registry: `TOOL_PAGES` lists tool page classes, and `MainWindow` builds the sidebar and `QStackedWidget` from each page's `title`/`subtitle`. Keep the registry in sync when adding tools.
- `src/core/` holds Qt-free data and contracts: `models.FileEntry`, `models.SourceFile`, `models.ScanResult`, `models.DiffLine`, `models.FileDiff`, `ignore.DEFAULT_IGNORE_PATTERNS`, `hashline.compute_tag` (the 4-hex `[path#TAG]` snapshot shared by the CER-1/CER-3 exporters and the CER-2 applier), and the shared `skills.HASHLINE_SKILL` prompt used by CER-1, CER-2, and CER-3.
- `src/utils/` holds shared, Qt-free-or-Qt-generic helpers used across tools: `gitignore.IgnoreMatcher`, `scanner.scan_project`, `tasks.Task`/`CancelToken` background-work wrappers, and `fs.write_text_atomic`. Promote reusable code here instead of copying it into a tool package.
- `src/tools/cer_1/` is the codebase export tool. `src/page.py` orchestrates scanning/selection/preview; `file_tree.py`, `ignore_dialog.py`, `formatter.py`, and `sources.py` are tool-specific. Scanning and preview generation run on a `QThreadPool`; ignore patterns follow `.gitignore` semantics and prune the tree. Background tasks must be cancelled through `CancelToken` on rescans/project changes, and `Cer1Page.shutdown()` is called by `MainWindow.closeEvent`.
- `src/tools/cer_2/` is the codebase edit resolver, applying the Hashline patch grammar. `src/parser.py` parses `[path#TAG]` sections and lowers `PUT N.=M:`, `PUT <N:`, `PUT >N:`, `PUT N*:`, `CUT N.=M`, `CUT N*`, `REM`, and `MV` into anchored `Insert`/`Delete`/`Cut`/`Paste` primitives (modelled on `crates/pi-edit`); `src/patch.py` resolves `@name` registers and materialises the edits onto the file's lines, preserving newline style, then builds `FileDiff`. Block ops (`PUT N*:`, `CUT N*`) degrade to the single anchor line because CER-2 has no syntax-aware resolver, so the skill prompt prefers explicit ranges. `src/page.py` verifies each header `TAG` against `hashline.compute_tag(current)` and refuses to preview stale patches. `src/file_list.py` renders per-file add/delete counts; `src/page.py` orchestrates scan, debounced live diff preview, click-to-jump, and apply. Writes use `write_text_atomic`; applied files drop from the pending set while failed ones are retained. Switching projects clears the pasted response, and `Cer2Page.shutdown()` is called by `MainWindow.closeEvent`.
- `src/tools/cer_3/` is the codebase search & focus tool. `src/searcher.py` runs plain-text or regex searches across scanned files (Qt-free, cancellable via `CancelToken`); `src/results.py` renders the checked match list; `src/formatter.py` builds a focused prompt with only matched sections (configurable context) or whole files; `src/page.py` orchestrates scanning, debounced search, click-to-preview with highlighted matches, and clipboard export. `Cer3Page.shutdown()` is called by `MainWindow.closeEvent`.
## Required tool package layout

Complex or large tools are self-contained packages with a fixed layout; small reusable functionality is promoted to `src/utils/` (non-UI) or `src/ui/` (shared widgets) instead of becoming a package.

```
src/tools/<tool_name>/
  __init__.py      # exports PAGE_CLASS, the ToolPage subclass
  src/             # all tool sources; e.g. src/tools/cer_1/src/page.py
  assets/          # optional tool-local assets
```

When adding a tool, make the package self-contained, keep the layout identical for every tool, and import shared code via absolute paths. Icons may be fetched from a CDN and vendored locally together with their license.

## Design conventions

- Warm monochrome dark theme (near-black neutral brown plus off-white). Muted, desaturated red/green are the only allowed accents, used semantically for diffs, warnings, and success/error status; avoid other colorful accents, gradients, and heavy shadows.
- Minimal UI copy in English; restrained, consistent spacing.
- No duplicated widget-building code: extend the shared components rather than restyling widgets ad hoc.
