"""Background workers so the UI thread stays responsive."""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from PyQt6.QtCore import QObject, pyqtSignal

from screen_gif_recorder.export.gif_exporter import export_gif
from screen_gif_recorder.export.mp4_exporter import export_mp4


class ExportWorker(QObject):
    finished = pyqtSignal(str)  # output path
    failed = pyqtSignal(str)
    progress = pyqtSignal(int, int)  # current, total

    def __init__(
        self,
        frames: list[Image.Image],
        output_path: Path,
        export_format: str,
        fps: float,
        quality: int,
    ) -> None:
        super().__init__()
        self._frames = frames
        self._output_path = output_path
        self._export_format = export_format
        self._fps = fps
        self._quality = quality

    def run(self) -> None:
        total = len(self._frames)
        try:
            self.progress.emit(0, total)
            if self._export_format == "gif":
                export_gif(
                    self._frames,
                    self._output_path,
                    fps=self._fps,
                    quality=self._quality,
                )
            else:
                export_mp4(
                    self._frames,
                    self._output_path,
                    fps=self._fps,
                    on_progress=lambda cur, tot: self.progress.emit(cur, tot),
                )
            self.finished.emit(str(self._output_path))
        except Exception as exc:
            self.failed.emit(str(exc))
