# Chatbot Tools

Minimal PySide6 toolkit for preparing efficient prompts for AI chats.

## Tools

- **CER-1 — Codebase Export & Reference**: scan a project, hide ignored files, select a subset, and copy a line-numbered prompt for AI edits.
- **CER-2 — Codebase Edit Resolver**: paste line-numbered AI edits, review a colored before/after diff, and apply them to the project.

Tool packages live under `src/tools/<name>/src`; shared UI, utilities, and data models live in `src/ui`, `src/utils`, and `src/core`.

## Run

```bash
python3 -m venv .venv
.venv/bin/pip install "PySide6==6.8.3"
.venv/bin/python src/main.py
```

PySide6 6.8.3 is pinned for CPUs without SSE4.2/POPCNT.
