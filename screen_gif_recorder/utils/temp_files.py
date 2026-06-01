"""Temporary workspace for frames and intermediate exports."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path


class TempWorkspace:
    """Context-managed temp directory for recording session artifacts."""

    def __init__(self) -> None:
        self._dir: tempfile.TemporaryDirectory[str] | None = None

    @property
    def path(self) -> Path:
        if self._dir is None:
            raise RuntimeError("Workspace not started")
        return Path(self._dir.name)

    def start(self) -> Path:
        self.cleanup()
        self._dir = tempfile.TemporaryDirectory(prefix="pixly_rec_")
        return self.path

    def cleanup(self) -> None:
        if self._dir is not None:
            self._dir.cleanup()
            self._dir = None

    def frame_path(self, index: int) -> Path:
        return self.path / f"frame_{index:06d}.png"
