"""Dialog to pick a display for full-screen capture (thumbnail grid, async previews)."""

from __future__ import annotations

import mss
from PIL import Image
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QGuiApplication, QPixmap, QScreen
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from screen_gif_recorder.ui.picker_grid import (
    PICKER_GRID_STYLESHEET,
    PickerTileGrid,
    THUMB_H,
    THUMB_W,
    image_cover_crop,
)
from screen_gif_recorder.ui.region_selector import warm_up_displays
from screen_gif_recorder.utils.qt_image import pil_to_pixmap


def screen_label(screen: QScreen, index: int) -> str:
    """Human-readable label for a display in the picker list."""
    geo = screen.geometry()
    name = screen.name().strip() if screen.name() else f"Display {index + 1}"
    primary = (
        " · primary"
        if screen is QGuiApplication.primaryScreen()
        else ""
    )
    pos = (
        f"at ({geo.x()}, {geo.y()})"
        if geo.x() != 0 or geo.y() != 0
        else "at origin"
    )
    return f"{name}{primary}\n{geo.width()}×{geo.height()} pt {pos}"


def screen_tile_labels(screen: QScreen, index: int) -> tuple[str, str]:
    """Short title + subtitle for picker tiles."""
    geo = screen.geometry()
    name = screen.name().strip() if screen.name() else f"Display {index + 1}"
    primary = " · primary" if screen is QGuiApplication.primaryScreen() else ""
    pos = (
        f"at ({geo.x()}, {geo.y()})"
        if geo.x() != 0 or geo.y() != 0
        else "at origin"
    )
    return f"{name}{primary}", f"{geo.width()}×{geo.height()} pt {pos}"


def capture_display_thumbnail(
    x: int,
    y: int,
    width: int,
    height: int,
    *,
    max_width: int | None = None,
    max_height: int | None = None,
) -> QPixmap | None:
    """Screenshot a monitor region for the picker (runs off the UI thread)."""
    if max_width is None:
        max_width = THUMB_W
    if max_height is None:
        max_height = THUMB_H
    if width < 1 or height < 1:
        return None
    try:
        with mss.mss() as sct:
            shot = sct.grab(
                {"left": x, "top": y, "width": width, "height": height}
            )
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        img = image_cover_crop(img, max_width, max_height)
        return pil_to_pixmap(img)
    except Exception:
        return None


def placeholder_display_thumbnail(
    index: int,
    *,
    width: int | None = None,
    height: int | None = None,
    is_primary: bool = False,
) -> QPixmap:
    if width is None:
        width = THUMB_W
    if height is None:
        height = THUMB_H
    from PyQt6.QtGui import QColor, QFont, QPainter

    pix = QPixmap(width, height)
    pix.fill(QColor(26, 26, 31))
    painter = QPainter(pix)
    painter.setPen(QColor(113, 113, 122))
    painter.setFont(QFont("Helvetica", 32, QFont.Weight.Bold))
    painter.drawText(pix.rect(), int(Qt.AlignmentFlag.AlignCenter), str(index + 1))
    if is_primary:
        painter.setFont(QFont("Helvetica", 10, QFont.Weight.DemiBold))
        painter.drawText(
            pix.rect().adjusted(0, 0, -8, -8),
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom),
            "Primary",
        )
    painter.end()
    return pix


class _DisplayThumbnailWorker(QThread):
    thumbnail_ready = pyqtSignal(int, object)

    def __init__(self, layouts: list[tuple[int, int, int, int, int]]) -> None:
        super().__init__()
        # index, x, y, width, height
        self._layouts = layouts

    def run(self) -> None:
        for index, x, y, width, height in self._layouts:
            if self.isInterruptionRequested():
                return
            thumb = capture_display_thumbnail(x, y, width, height)
            if thumb is not None and not thumb.isNull():
                self.thumbnail_ready.emit(index, thumb)


class ScreenPickerDialog(QDialog):
    """Choose a monitor — names appear immediately, previews load in the background."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Select display")
        self.setMinimumSize(720, 480)
        self.resize(800, 520)
        self._selected: QScreen | None = None
        self._screens: list[QScreen] = []
        self._thumb_worker: _DisplayThumbnailWorker | None = None
        self._load_generation = 0

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        hint = QLabel(
            "Choose the monitor to record. Displays are listed right away; "
            "previews load in the background."
        )
        hint.setWordWrap(True)
        hint.setObjectName("mutedLabel")
        layout.addWidget(hint)

        top_row = QHBoxLayout()
        self._status = QLabel("Scanning displays…")
        self._status.setObjectName("mutedLabel")
        top_row.addWidget(self._status, stretch=1)

        btn_refresh = QPushButton("Refresh")
        btn_refresh.setObjectName("secondaryBtn")
        btn_refresh.clicked.connect(self._reload)
        top_row.addWidget(btn_refresh)
        layout.addLayout(top_row)

        self._grid = PickerTileGrid()
        self._grid.tile_double_clicked.connect(lambda _i: self._accept_current())
        layout.addWidget(self._grid, stretch=1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept_current)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setStyleSheet(PICKER_GRID_STYLESHEET)

        QTimer.singleShot(0, self._discover)

    @property
    def selected_screen(self) -> QScreen | None:
        return self._selected

    def _cancel_thumb_worker(self) -> None:
        if self._thumb_worker is None:
            return
        if self._thumb_worker.isRunning():
            self._thumb_worker.requestInterruption()
            self._thumb_worker.wait(2000)
        self._thumb_worker = None

    def _reload(self) -> None:
        self._cancel_thumb_worker()
        self._load_generation += 1
        self._screens = []
        self._grid.clear()
        self._status.setText("Scanning displays…")
        QTimer.singleShot(0, self._discover)

    def _discover(self) -> None:
        generation = self._load_generation
        warm_up_displays()
        self._screens = list(QGuiApplication.screens())

        if generation != self._load_generation:
            return

        self._populate_grid()

        count = len(self._screens)
        if count == 0:
            self._status.setText("No displays detected.")
            return

        self._status.setText(
            f"{count} display{'s' if count != 1 else ''} — loading previews…"
        )
        self._start_thumbnail_worker(generation)

    def _populate_grid(self) -> None:
        self._grid.clear()
        primary = QGuiApplication.primaryScreen()

        if not self._screens:
            return

        primary_index = 0
        for index, screen in enumerate(self._screens):
            is_primary = screen is primary
            thumb = placeholder_display_thumbnail(
                index, is_primary=is_primary
            )
            title, subtitle = screen_tile_labels(screen, index)
            self._grid.add_tile(thumb, title, subtitle, screen)
            if is_primary:
                primary_index = index

        self._grid.select_index(primary_index)

    def _start_thumbnail_worker(self, generation: int) -> None:
        self._cancel_thumb_worker()

        layouts: list[tuple[int, int, int, int, int]] = []
        for index, screen in enumerate(self._screens):
            geo = screen.geometry()
            layouts.append((index, geo.x(), geo.y(), geo.width(), geo.height()))

        if not layouts:
            return

        worker = _DisplayThumbnailWorker(layouts)
        self._thumb_worker = worker

        def _on_thumb(screen_index: int, pix: object) -> None:
            if generation != self._load_generation:
                return
            if isinstance(pix, QPixmap):
                self._grid.update_thumbnail(screen_index, pix)

        def _on_done() -> None:
            if generation != self._load_generation:
                return
            n = len(self._screens)
            self._status.setText(f"{n} display{'s' if n != 1 else ''}")

        worker.thumbnail_ready.connect(_on_thumb)
        worker.finished.connect(_on_done)
        worker.start()

    def _accept_current(self) -> None:
        screen = self._grid.selected_data()
        if not isinstance(screen, QScreen):
            QMessageBox.warning(
                self, "No display", "No display is available to select."
            )
            return
        self._selected = screen
        self.accept()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._cancel_thumb_worker()
        super().closeEvent(event)

    def reject(self) -> None:  # noqa: N802
        self._cancel_thumb_worker()
        super().reject()
