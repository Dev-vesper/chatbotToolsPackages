"""Shared Hashline helpers.

The tag binds a file version. It is produced once by an exporter (CER-1/CER-3)
and echoed back verbatim by the model; the applier (CER-2) recomputes it from
the file on disk and rejects the patch if they diverge.
"""

from __future__ import annotations

import hashlib


def compute_tag(content: str) -> str:
    """Return the 4-hex uppercase tag for a file's content.

    Line endings are normalised first so CRLF and LF files that are otherwise
    identical produce the same tag. The hash is not a security primitive; it
    only catches staleness between the model's read and the write.
    """
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.blake2s(normalized.encode("utf-8"), digest_size=2).hexdigest().upper()
