from __future__ import annotations

EDIT_SKILL = (
    "Use the line-numbered format only when editing files that already exist. "
    "Use one `## path` header per file and one `<line number> <code>` per line. "
    "Line numbers refer to the current version of the file; after an edit is applied, "
    "read the file again and never reuse earlier numbers. "
    "For replacements, send only the changed lines with their current numbers and "
    "original indentation; do not resend unchanged code. "
    "To insert lines, number the new lines at the insertion point, then include at "
    "least two following unchanged lines numbered as if the insertion were applied; "
    "keep those anchor lines identical so the tool can place the insertion. "
    "To clear a line, send its number with no code. "
    "Omitting a line does not delete it. "
    "When creating a new file, send the complete content without line numbers under "
    "the same header."
)
