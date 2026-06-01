"""Background screen region capture at a target FPS."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable

import mss
from PIL import Image


@dataclass(frozen=True)
class CaptureRegion:
    """Screen region in the coordinate space expected by mss (logical on macOS)."""

    left: int
    top: int
    width: int
    height: int

    def as_mss_dict(self) -> dict[str, int]:
        return {
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height,
        }


@dataclass
class RecorderSettings:
    fps: float = 12.0
    scale: float = 1.0  # 1.0, 0.75, 0.5
    save_frames_to_disk: bool = False


class ScreenRecorder:
    """
    Captures frames from a fixed screen region on a worker thread.
    Emits PIL Images via on_frame callback; optional PNG spill to disk.
    """

    def __init__(
        self,
        region: CaptureRegion,
        settings: RecorderSettings,
        on_frame: Callable[[Image.Image, int], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        self._region = region
        self._settings = settings
        self._on_frame = on_frame
        self._on_error = on_error
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._frames: list[Image.Image] = []
        self._lock = threading.Lock()
        self._frame_count = 0

    @property
    def frames(self) -> list[Image.Image]:
        with self._lock:
            return list(self._frames)

    @property
    def frame_count(self) -> int:
        return self._frame_count

    @property
    def is_recording(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_recording:
            return
        self._stop.clear()
        with self._lock:
            self._frames.clear()
        self._frame_count = 0
        self._thread = threading.Thread(
            target=self._run, name="ScreenCapture", daemon=False
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=15.0)
        self._thread = None

    def _run(self) -> None:
        interval = 1.0 / max(self._settings.fps, 1.0)
        scale = max(0.1, min(1.0, self._settings.scale))

        try:
            with mss.mss() as sct:
                region = self._region.as_mss_dict()
                next_capture = time.perf_counter()

                while not self._stop.is_set():
                    now = time.perf_counter()
                    if now < next_capture:
                        time.sleep(min(next_capture - now, interval))
                        continue

                    shot = sct.grab(region)
                    img = Image.frombytes(
                        "RGB", shot.size, shot.bgra, "raw", "BGRX"
                    )

                    if scale < 0.999:
                        new_w = max(1, int(img.width * scale))
                        new_h = max(1, int(img.height * scale))
                        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

                    idx = self._frame_count
                    self._frame_count += 1

                    with self._lock:
                        self._frames.append(img.copy())

                    if self._on_frame:
                        self._on_frame(img, idx)

                    # One frame per tick — if we fell behind, skip missed slots
                    next_capture += interval
                    if time.perf_counter() - next_capture > interval * 2:
                        next_capture = time.perf_counter()

        except Exception as exc:
            if self._on_error:
                self._on_error(exc)
