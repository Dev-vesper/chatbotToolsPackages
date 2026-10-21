from __future__ import annotations

from threading import Lock

from core.models import FileEntry, SourceFile


class ContentReader:
    def __init__(self) -> None:
        self._cache: dict[str, tuple[int, int, str]] = {}
        self._lock = Lock()

    def read(self, source: SourceFile) -> FileEntry | None:
        key = str(source.path)
        try:
            stat = source.path.stat()
        except OSError:
            return None

        with self._lock:
            cached = self._cache.get(key)
        if cached is not None and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
            content = cached[2]
        else:
            try:
                data = source.path.read_bytes()
            except OSError:
                return None
            content = data.decode("utf-8", errors="replace")
            with self._lock:
                self._cache[key] = (stat.st_mtime_ns, stat.st_size, content)

        return FileEntry(source.path, source.rel_path, content)
