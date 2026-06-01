"""Fullscreen countdown shown before recording starts."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from screen_gif_recorder.ui.region_selector import virtual_desktop_rect


class RecordingCountdownOverlay(QWidget):
    """Large on-screen 3…2…1 before capture begins."""

    finished = pyqtSignal()
    cancelled = pyqtSignal()

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 170);")
        self._remaining = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._label = QLabel("3")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont()
        font.setPointSize(96)
        font.setWeight(QFont.Weight.Bold)
        self._label.setFont(font)
        self._label.setStyleSheet("color: #ffffff; background: transparent;")
        layout.addWidget(self._label)

        hint = QLabel("Esc to cancel")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("color: #b0b0b8; font-size: 15px; background: transparent;")
        layout.addWidget(hint)

    def start(self, seconds: int = 3) -> None:
        self._remaining = seconds
        self._label.setText(str(seconds))
        self.setGeometry(virtual_desktop_rect())
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()
        self._timer.start(1000)

    def cancel(self) -> None:
        if not self._timer.isActive() and not self.isVisible():
            return
        self._timer.stop()
        self.cancelled.emit()
        self.close()

    def _tick(self) -> None:
        self._remaining -= 1
        if self._remaining <= 0:
            self._timer.stop()
            self.finished.emit()
            self.close()
            return
        self._label.setText(str(self._remaining))

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.cancel()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._timer.stop()
        super().closeEvent(event)
