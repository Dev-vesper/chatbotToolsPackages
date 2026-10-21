from __future__ import annotations

EDIT_SKILL = (
    "Use the line-numbered format only when editing files that already exist. "
    "When editing an existing file, work line by line and use the given line numbers "
    "to locate every change. Return only the edited lines in the same format, "
    '"<line number> <code>", with correct line numbers and the original indentation. '
    "Do not resend unchanged code or the entire file. "
    "When creating a new file, send the complete file content without line numbers, "
    "keeping the `## path` header."
)
