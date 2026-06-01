"""Dialog to pick an on-screen window (macOS) with thumbnail previews."""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from screen_gif_recorder.ui.picker_grid import (
    PICKER_GRID_STYLESHEET,
    PickerTileGrid,
    THUMB_H,
    THUMB_W,
)
from screen_gif_recorder.utils.macos_windows import (
    WindowInfo,
    capture_window_thumbnail,
    list_on_screen_windows,
    macos_window_api_available,
    placeholder_window_thumbnail,
)


class _WindowListWorker(QThread):
    finished = pyqtSignal(list)

    def __init__(self, *, browsers_only: bool) -> None:
        super().__init__()
        self._browsers_only = browsers_only

    def run(self) -> None:
        windows = list_on_screen_windows(
            browsers_only=self._browsers_only,
            enrich_indices=False,
        )
        self.finished.emit(windows)


class _ThumbnailWorker(QThread):
    thumbnail_ready = pyqtSignal(int, object)

    def __init__(self, windows: list[WindowInfo]) -> None:
        super().__init__()
        self._windows = windows

    def run(self) -> None:
        for win in self._windows:
            if self.isInterruptionRequested():
                return
            if not win.window_id:
                continue
            thumb = capture_window_thumbnail(
                win.window_id,
                max_width=THUMB_W,
                max_height=THUMB_H,
            )
            if thumb is not None and not thumb.isNull():
                self.thumbnail_ready.emit(win.window_id, thumb)


class WindowPickerDialog(QDialog):
    """Pick an on-screen window — tiles appear immediately, thumbnails fill in async."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Select window to record")
        self.setMinimumSize(720, 520)
        self.resize(800, 560)
        self._selected: WindowInfo | None = None
        self._all_windows: list[WindowInfo] = []
        self._tile_index_by_window_id: dict[int, int] = {}
        self._list_worker: _WindowListWorker | None = None
        self._thumb_worker: _ThumbnailWorker | None = None
        self._load_generation = 0

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        hint = QLabel(
            "Choose a window to record. Names appear right away; previews load in the background. "
            "Keep the window visible on its display during the countdown."
        )
        hint.setWordWrap(True)
        hint.setObjectName("mutedLabel")
        layout.addWidget(hint)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter by title or app…")
        self._search.textChanged.connect(self._apply_filter)
        filter_row.addWidget(self._search, stretch=1)

        self._browser_only = QCheckBox("Browsers only")
        self._browser_only.setChecked(True)
        self._browser_only.toggled.connect(self._reload)
        filter_row.addWidget(self._browser_only)

        self._btn_refresh = QPushButton("Refresh")
        self._btn_refresh.setObjectName("secondaryBtn")
        self._btn_refresh.clicked.connect(self._reload)
        filter_row.addWidget(self._btn_refresh)
        layout.addLayout(filter_row)

        self._status = QLabel("Scanning windows…")
        self._status.setObjectName("mutedLabel")
        layout.addWidget(self._status)

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

        self._reload()

    @property
    def selected_window(self) -> WindowInfo | None:
        return self._selected

    def _cancel_workers(self) -> None:
        for worker in (self._list_worker, self._thumb_worker):
            if worker is None:
                continue
            if worker.isRunning():
                worker.requestInterruption()
                worker.wait(2000)
        self._list_worker = None
        self._thumb_worker = None

    def _reload(self) -> None:
        if not macos_window_api_available():
            QMessageBox.warning(self, "Not available", "Window selection is macOS only.")
            return

        self._cancel_workers()
        self._load_generation += 1
        generation = self._load_generation

        self._all_windows = []
        self._tile_index_by_window_id.clear()
        self._grid.clear()
        self._status.setText("Scanning windows…")
        self._btn_refresh.setEnabled(False)

        worker = _WindowListWorker(browsers_only=self._browser_only.isChecked())
        self._list_worker = worker
        worker.finished.connect(
            lambda wins: self._on_windows_loaded(wins, generation)
        )
        worker.start()

    def _on_windows_loaded(self, windows: list, generation: int) -> None:
        if generation != self._load_generation:
            return

        self._btn_refresh.setEnabled(True)
        self._all_windows = windows
        self._apply_filter()

        count = len(self._all_windows)
        if count == 0:
            self._status.setText("No windows found — open an app and click Refresh.")
            return

        self._status.setText(f"{count} window{'s' if count != 1 else ''} — loading previews…")

    def _start_thumbnail_worker(self, generation: int) -> None:
        query = self._search.text().strip().lower()
        visible = [
            w
            for w in self._all_windows
            if not query or query in w.display_name.lower()
        ]
        if not visible:
            return

        worker = _ThumbnailWorker(visible)
        self._thumb_worker = worker

        def _on_thumb(window_id: int, pix: object) -> None:
            if generation != self._load_generation:
                return
            if isinstance(pix, QPixmap):
                tile_index = self._tile_index_by_window_id.get(window_id)
                if tile_index is not None:
                    self._grid.update_thumbnail(tile_index, pix)

        def _on_done() -> None:
            if generation != self._load_generation:
                return
            n = len(visible)
            self._status.setText(f"{n} window{'s' if n != 1 else ''}")

        worker.thumbnail_ready.connect(_on_thumb)
        worker.finished.connect(_on_done)
        worker.start()

    def _apply_filter(self) -> None:
        if self._thumb_worker is not None and self._thumb_worker.isRunning():
            self._thumb_worker.requestInterruption()
            self._thumb_worker.wait(500)
        self._thumb_worker = None

        query = self._search.text().strip().lower()
        self._grid.clear()
        self._tile_index_by_window_id.clear()

        matches = [
            win
            for win in self._all_windows
            if not query or query in win.display_name.lower()
        ]

        if not matches:
            self._status.setText(
                "No matching windows — open a window and click Refresh."
            )
            return

        for win in matches:
            title = win.title.strip() or "(untitled)"
            thumb = placeholder_window_thumbnail(
                win.owner, width=THUMB_W, height=THUMB_H
            )
            tile_index = self._grid.add_tile(thumb, title, win.owner, win)
            if win.window_id:
                self._tile_index_by_window_id[win.window_id] = tile_index

        if matches:
            self._grid.select_index(0)

        if self._all_windows:
            self._start_thumbnail_worker(self._load_generation)

    def _accept_current(self) -> None:
        win = self._grid.selected_data()
        if not isinstance(win, WindowInfo):
            return
        self._selected = win
        self.accept()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._cancel_workers()
        super().closeEvent(event)

    def reject(self) -> None:  # noqa: N802
        self._cancel_workers()
        super().reject()
