from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal


class CancelToken:
    __slots__ = ("_cancelled",)

    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled


class TaskSignals(QObject):
    done = Signal(object)
    error = Signal(str)


class Task(QRunnable):
    def __init__(self, fn: Callable[..., Any], *args: object) -> None:
        super().__init__()
        self._fn = fn
        self._args = args
        self.signals = TaskSignals()
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            result = self._fn(*self._args)
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI
            self.signals.error.emit(f"{type(exc).__name__}: {exc}")
            return
        self.signals.done.emit(result)
