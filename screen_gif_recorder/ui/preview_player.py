"""Playback preview with timeline scrubbing."""

from __future__ import annotations

from PIL import Image
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from screen_gif_recorder.utils.qt_image import pil_to_pixmap


def _format_duration(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}:{secs:05.2f}"


class RecordingPreview(QWidget):
    """Preview display + timeline; meant to live inside a panel card."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._frames: list[Image.Image] = []
        self._fps = 12.0
        self._index = 0
        self._playing = False
        self._scrubbing = False
        self._resume_after_scrub = False
        self._thumb_cache: dict[int, QPixmap] = {}
        self._controls_locked = False

        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        self._screen = QLabel("Recording preview")
        self._screen.setObjectName("previewLabel")
        self._screen.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._screen.setMinimumHeight(320)
        self._screen.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        chrome = QFrame()
        chrome.setObjectName("playerChrome")
        chrome_layout = QVBoxLayout(chrome)
        chrome_layout.setContentsMargins(0, 10, 0, 0)
        chrome_layout.setSpacing(8)

        self._time_current = QLabel("0:00.00")
        self._time_current.setObjectName("timeLabel")
        self._time_current.setFixedWidth(58)
        self._time_current.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self._timeline = QSlider(Qt.Orientation.Horizontal)
        self._timeline.setObjectName("timelineSlider")
        self._timeline.setEnabled(False)
        self._timeline.setMinimum(0)
        self._timeline.setFixedHeight(28)
        self._timeline.sliderPressed.connect(self._on_scrub_start)
        self._timeline.sliderReleased.connect(self._on_scrub_end)
        self._timeline.sliderMoved.connect(self._on_timeline_moved)
        self._timeline.valueChanged.connect(self._on_timeline_changed)

        self._time_total = QLabel("0:00.00")
        self._time_total.setObjectName("timeLabel")
        self._time_total.setFixedWidth(58)
        self._time_total.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        timeline_row = QHBoxLayout()
        timeline_row.setSpacing(8)
        timeline_row.addWidget(self._time_current)
        timeline_row.addWidget(self._timeline, stretch=1)
        timeline_row.addWidget(self._time_total)
        chrome_layout.addLayout(timeline_row)

        self._btn_step_back = QPushButton("−1")
        self._btn_step_back.setObjectName("iconBtn")
        self._btn_step_back.setToolTip("Previous frame")
        self._btn_step_back.setFixedSize(40, 34)
        self._btn_step_back.setEnabled(False)
        self._btn_step_back.clicked.connect(lambda: self._step_frame(-1))

        self._btn_play = QPushButton("Play")
        self._btn_play.setObjectName("playBtn")
        self._btn_play.setMinimumWidth(88)
        self._btn_play.setFixedHeight(34)
        self._btn_play.setEnabled(False)
        self._btn_play.clicked.connect(self._toggle_playback)

        self._btn_step_fwd = QPushButton("+1")
        self._btn_step_fwd.setObjectName("iconBtn")
        self._btn_step_fwd.setToolTip("Next frame")
        self._btn_step_fwd.setFixedSize(40, 34)
        self._btn_step_fwd.setEnabled(False)
        self._btn_step_fwd.clicked.connect(lambda: self._step_frame(1))

        self._btn_restart = QPushButton("Restart")
        self._btn_restart.setObjectName("secondaryBtn")
        self._btn_restart.setFixedHeight(34)
        self._btn_restart.setEnabled(False)
        self._btn_restart.clicked.connect(self._restart)

        self._frame_counter = QLabel("—")
        self._frame_counter.setObjectName("mutedLabel")
        self._frame_counter.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        transport_bar = QFrame()
        transport_bar.setObjectName("transportBar")
        transport = QHBoxLayout(transport_bar)
        transport.setContentsMargins(10, 8, 10, 8)
        transport.setSpacing(8)
        transport.addWidget(self._btn_step_back)
        transport.addWidget(self._btn_play)
        transport.addWidget(self._btn_step_fwd)
        transport.addWidget(self._btn_restart)
        transport.addStretch()
        transport.addWidget(self._frame_counter)
        chrome_layout.addWidget(transport_bar)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._screen, stretch=1)
        root.addWidget(chrome)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance_frame)

    @property
    def duration_seconds(self) -> float:
        if not self._frames:
            return 0.0
        return len(self._frames) / self._fps

    def clear(self) -> None:
        self.stop()
        self._frames = []
        self._thumb_cache.clear()
        self._index = 0
        self._timeline.setEnabled(False)
        self._timeline.setRange(0, 0)
        self._set_transport_enabled(False)
        self._btn_play.setText("Play")
        self._time_current.setText("0:00.00")
        self._time_total.setText("0:00.00")
        self._frame_counter.setText("—")
        self._screen.setPixmap(QPixmap())
        self._screen.setText("Recording preview")

    def set_message(self, text: str) -> None:
        self.stop()
        self._screen.setPixmap(QPixmap())
        self._screen.setText(text)

    def load_recording(self, frames: list[Image.Image], fps: float) -> None:
        self.stop()
        self._frames = frames
        self._fps = max(fps, 1.0)
        self._thumb_cache.clear()
        self._index = 0

        if not frames:
            self.clear()
            return

        self._timeline.blockSignals(True)
        self._timeline.setEnabled(True)
        self._timeline.setRange(0, max(0, len(frames) - 1))
        self._timeline.setValue(0)
        self._timeline.blockSignals(False)

        self._apply_controls_enabled()
        self._btn_play.setText("Play")
        self._update_time_labels()
        self._show_frame(0, update_slider=False)

    def stop(self) -> None:
        self._playing = False
        self._timer.stop()
        self._btn_play.setText("Play")

    def set_controls_locked(self, locked: bool) -> None:
        """Disable scrubbing and transport while export is in progress."""
        self._controls_locked = locked
        if locked:
            self.stop()
        self._apply_controls_enabled()

    def _apply_controls_enabled(self) -> None:
        has_frames = bool(self._frames)
        enabled = has_frames and not self._controls_locked
        self._set_transport_enabled(enabled)
        self._timeline.setEnabled(enabled and has_frames)

    def _set_transport_enabled(self, enabled: bool) -> None:
        self._btn_play.setEnabled(enabled)
        self._btn_restart.setEnabled(enabled)
        self._btn_step_back.setEnabled(enabled)
        self._btn_step_fwd.setEnabled(enabled)

    def _toggle_playback(self) -> None:
        if not self._frames:
            return
        if self._playing:
            self.stop()
            return
        if self._index >= len(self._frames) - 1:
            self._index = 0
            self._show_frame(0)
        self._playing = True
        self._btn_play.setText("Pause")
        self._timer.start(max(1, int(1000 / self._fps)))

    def _restart(self) -> None:
        if not self._frames:
            return
        was_playing = self._playing
        self.stop()
        self._index = 0
        self._show_frame(0)
        if was_playing:
            self._toggle_playback()

    def _step_frame(self, delta: int) -> None:
        if not self._frames:
            return
        self.stop()
        self._index = max(0, min(len(self._frames) - 1, self._index + delta))
        self._show_frame(self._index)

    def _advance_frame(self) -> None:
        if not self._frames or self._scrubbing:
            self.stop()
            return
        if self._index >= len(self._frames) - 1:
            self.stop()
            return
        self._show_frame(self._index + 1)

    def _on_scrub_start(self) -> None:
        if not self._frames:
            return
        self._scrubbing = True
        self._resume_after_scrub = self._playing
        self.stop()

    def _on_scrub_end(self) -> None:
        self._scrubbing = False
        if self._resume_after_scrub and self._frames:
            self._resume_after_scrub = False
            self._toggle_playback()

    def _on_timeline_moved(self, value: int) -> None:
        if self._scrubbing and self._frames:
            self._show_frame(value, update_slider=False)

    def _on_timeline_changed(self, value: int) -> None:
        if not self._frames:
            return
        if self._scrubbing or not self._playing:
            self._show_frame(value, update_slider=False)

    def _update_time_labels(self) -> None:
        total_sec = self.duration_seconds
        current_sec = self._index / self._fps if self._frames else 0.0
        self._time_current.setText(_format_duration(current_sec))
        self._time_total.setText(_format_duration(total_sec))
        if self._frames:
            self._frame_counter.setText(f"Frame {self._index + 1} / {len(self._frames)}")
        else:
            self._frame_counter.setText("—")

    def _show_frame(self, index: int, *, update_slider: bool = True) -> None:
        if not self._frames or index < 0 or index >= len(self._frames):
            return

        self._index = index
        self._screen.setText("")

        pix = self._thumb_cache.get(index)
        if pix is None:
            img = self._frames[index]
            preview = img.copy()
            target_w = max(self._screen.width(), 400)
            target_h = max(self._screen.height(), 240)
            preview.thumbnail((target_w, target_h), Image.Resampling.LANCZOS)
            pix = pil_to_pixmap(preview)
            scaled = pix.scaled(
                self._screen.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._thumb_cache[index] = scaled
            pix = scaled

        self._screen.setPixmap(pix)

        if update_slider:
            self._timeline.blockSignals(True)
            self._timeline.setValue(index)
            self._timeline.blockSignals(False)
        self._update_time_labels()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._thumb_cache and self._frames:
            self._thumb_cache.clear()
            self._show_frame(self._index, update_slider=False)
