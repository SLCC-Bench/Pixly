"""GIF export — shared palette, adaptive colors, full resolution."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PIL import Image

from screen_gif_recorder.export.compression import (
    quality_to_max_colors,
    should_thin_gif_frames,
)


def _select_frames(frames: list[Image.Image], quality: int) -> list[Image.Image]:
    """Only thin frames when quality is very low; default keeps every frame."""
    if not frames or not should_thin_gif_frames(quality):
        return frames
    if quality >= 20:
        return frames[::2] if len(frames) > 2 else frames
    return frames[::3] if len(frames) > 3 else frames


def _build_shared_palette(frames: list[Image.Image], max_colors: int) -> Image.Image:
    """Palette from several frames so screen UIs keep readable colors at fewer bytes."""
    if len(frames) == 1:
        return frames[0].convert("RGBA").convert(
            "P", palette=Image.Palette.ADAPTIVE, colors=max_colors
        )

    # Sample up to 5 frames spread through the clip
    n = len(frames)
    count = min(5, n)
    indices = [int(i * (n - 1) / max(count - 1, 1)) for i in range(count)]

    w, h = frames[0].size
    # Downscale samples for palette analysis only (faster; export stays full res)
    thumb_w = min(w, 320)
    thumb_h = max(1, int(h * thumb_w / max(w, 1)))
    strip = Image.new("RGB", (thumb_w * count, thumb_h))
    for i, idx in enumerate(indices):
        thumb = frames[idx].convert("RGB").resize(
            (thumb_w, thumb_h), Image.Resampling.BILINEAR
        )
        strip.paste(thumb, (i * thumb_w, 0))

    return strip.convert("P", palette=Image.Palette.ADAPTIVE, colors=max_colors)


def export_gif(
    frames: list[Image.Image],
    output_path: Path,
    *,
    fps: float = 12.0,
    quality: int = 70,
    max_colors: int | None = None,
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> Path:
    if not frames:
        raise ValueError("No frames to export")

    selected = _select_frames(frames, quality)
    total = len(selected)
    duration_ms = int(1000 / max(fps, 1.0))
    colors = max_colors if max_colors is not None else quality_to_max_colors(quality)
    colors = max(2, min(256, colors))

    if on_progress:
        on_progress(0, total)

    palette_img = _build_shared_palette(selected, colors)

    gif_frames: list[Image.Image] = []
    for i, frame in enumerate(selected):
        rgb = frame.convert("RGB")
        gif_frames.append(
            rgb.quantize(palette=palette_img, method=Image.Quantize.MEDIANCUT)
        )
        if on_progress and (i == 0 or (i + 1) % 5 == 0 or i + 1 == total):
            on_progress(i + 1, total)

    if on_progress:
        on_progress(total, total)

    first, *rest = gif_frames
    first.save(
        output_path,
        save_all=True,
        append_images=rest,
        optimize=True,
        duration=duration_ms,
        loop=0,
        disposal=2,
    )
    return output_path
