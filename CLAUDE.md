# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

- Install dependencies: `.venv/bin/pip install "PySide6==6.8.3"`
- Run the app: `.venv/bin/python src/main.py`
- Syntax-check the tree: `.venv/bin/python -m compileall -q src`

There is no test suite, linter, or packaging configuration yet.

PySide6 must stay on 6.8.x for this machine: 6.9+ builds abort on import because the Core 2 Duo lacks SSE4.2/POPCNT. The README pins 6.8.3.

## Architecture

`src/` is the import root. Start the app with `python src/main.py`, not `python -m src.main`; shared imports are absolute from `src`: `ui.*`, `tools.*`, `core.*`, `config`.

- `src/main.py` creates the `QApplication`, applies the theme, and shows `ui.main_window.MainWindow`.
- `src/ui/` is the shell and shared design system. `theme.py` is the only place colors/fonts/QSS may be defined. `components.py` holds primitives shared by every tool: `ToolPage` (title/subtitle header + `body_layout`), `Sidebar`, `Card`, `EmptyState`, and button factories. Reusable UI belongs here, not inside a tool.
- `src/tools/__init__.py` is the registry: `TOOL_PAGES` lists tool page classes, and `MainWindow` builds the sidebar and `QStackedWidget` from each page's `title`/`subtitle`. Keep the registry in sync when adding tools.
- `src/core/` holds Qt-free data and contracts. `models.FileEntry` is the future scanner/formatter input; `ignore.DEFAULT_IGNORE_PATTERNS` seeds the ignore dialog.
- `TOOL_PAGES` is currently empty: no tool packages exist yet. The app starts with an empty sidebar and stack.

## Required tool package layout

Complex or large tools are self-contained packages with a fixed layout; small reusable functionality is promoted to `src/utils/` (non-UI) or `src/ui/` (shared widgets) instead of becoming a package.

```
src/tools/<tool_name>/
  __init__.py      # exports PAGE_CLASS, the ToolPage subclass
  src/             # all tool sources; e.g. src/tools/pickercodebase/src/page.py
  assets/          # optional tool-local assets
```

When adding a tool, make the package self-contained, keep the layout identical for every tool, and import shared code via absolute paths. Icons may be fetched from a CDN and vendored locally together with their license.

## Design conventions

- Warm monochrome dark theme (near-black neutral brown plus off-white); no colorful accents, gradients, or heavy shadows.
- Minimal UI copy in English; restrained, consistent spacing.
- No duplicated widget-building code: extend the shared components rather than restyling widgets ad hoc.
