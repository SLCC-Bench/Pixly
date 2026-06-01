"""Map UI quality (0–100) to encoder settings — full resolution, smaller files."""

from __future__ import annotations


def quality_to_crf(quality: int) -> int:
    """
    H.264 CRF: lower = better quality, larger file.
    quality 100 → CRF 20, quality 50 → CRF 26, quality 0 → CRF 32.
    """
    q = max(0, min(100, quality))
    return int(round(32 - (q / 100.0) * 12))


def quality_to_max_colors(quality: int) -> int:
    """GIF palette size — fewer colors = smaller file at same pixel dimensions."""
    q = max(0, min(100, quality))
    return max(64, int(round(64 + (q / 100.0) * 192)))


def should_thin_gif_frames(quality: int) -> bool:
    """Only drop frames at very low quality (resolution unchanged)."""
    return quality < 35
