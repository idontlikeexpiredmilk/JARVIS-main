"""Application entry point for the JARVIS desktop assistant."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


def main() -> int:
    # Chromebook/Crostini displays often report fractional DPI scale factors
    # (e.g. 1.25x, 1.5x). Left at Qt's default rounding policy, this can cause
    # widgets/backgrounds to be laid out at one scale and painted at another,
    # which shows up as visual glitches (stray black regions, unexpected
    # zoom-looking jumps when the window moves between displays/scales).
    # PassThrough keeps the real (possibly fractional) scale factor instead of
    # rounding it, which renders consistently on these displays.
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
