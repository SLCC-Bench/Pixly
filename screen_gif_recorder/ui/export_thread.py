"""QThread-based export (avoids QObject worker lifetime bugs)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from PyQt6.QtCore import QThread, pyqtSignal

from screen_gif_recorder.capture.audio_recorder import AudioCaptureResult
from screen_gif_recorder.export.gif_exporter import export_gif
from screen_gif_recorder.export.mp4_exporter import export_mp4


class ExportThread(QThread):
    progress = pyqtSignal(int, int)
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(
        self,
        frames: list[Image.Image],
        output_path: Path,
        export_format: str,
        fps: float,
        quality: int,
        audio: AudioCaptureResult | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._frames = frames
        self._output_path = output_path
        self._export_format = export_format
        self._fps = fps
        self._quality = quality
        self._audio = audio

    def run(self) -> None:
        try:

            def report(current: int, tot: int) -> None:
                self.progress.emit(current, tot)

            if self._export_format == "gif":
                export_gif(
                    self._frames,
                    self._output_path,
                    fps=self._fps,
                    quality=self._quality,
                    on_progress=report,
                )
            else:
                export_mp4(
                    self._frames,
                    self._output_path,
                    fps=self._fps,
                    quality=self._quality,
                    audio=self._audio,
                    on_progress=report,
                )

            self.finished_ok.emit(str(self._output_path))
        except Exception as exc:
            self.failed.emit(str(exc))
