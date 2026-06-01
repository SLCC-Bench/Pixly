#!/usr/bin/env python3
"""Entry point for Screen to GIF Recorder."""

from __future__ import annotations

import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from screen_gif_recorder.ui.main_window import create_main_window


def main() -> int:
    # High-DPI on Retina displays
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("Pixly")
    app.setOrganizationName("Pixly")
    # Area selection hides the main window; keep running while overlay panels are open.
    app.setQuitOnLastWindowClosed(False)

    window = create_main_window()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
