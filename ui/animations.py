"""Startup animation helpers."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QTimer


class StartupSequencer(QObject):
    """Emits cinematic startup status lines without blocking the UI."""

    def __init__(self, callback: Callable[[str], None]) -> None:
        super().__init__()
        self.callback = callback
        self.lines = ["Initializing systems...", "Loading AI core...", "Systems online."]
        self.index = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._next)

    def start(self) -> None:
        self.index = 0
        self.timer.start(850)

    def _next(self) -> None:
        if self.index >= len(self.lines):
            self.timer.stop()
            return
        self.callback(self.lines[self.index])
        self.index += 1
