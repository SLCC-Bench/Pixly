"""Map Qt screen coordinates to mss capture regions (platform-specific)."""

from __future__ import annotations

import platform

from PyQt6.QtGui import QScreen

from screen_gif_recorder.capture.screen_recorder import CaptureRegion
from screen_gif_recorder.ui.region_selector import LogicalRegion


def mss_uses_logical_coordinates() -> bool:
    """
    On macOS, mss monitor dicts and grab regions use Cocoa points (logical),
    not backing-store pixels. Multiplying by DPR captures a 2× buffer with
    only the top-left quarter containing real pixels.
    """
    return platform.system() == "Darwin"


def logical_to_capture_region(region: LogicalRegion, screen: QScreen | None) -> CaptureRegion:
    """Convert a Qt logical region to the coordinate space mss expects."""
    if mss_uses_logical_coordinates():
        return CaptureRegion(
            left=region.x,
            top=region.y,
            width=region.width,
            height=region.height,
        )

    dpr = screen.devicePixelRatio() if screen else 1.0
    left, top, w, h = region.to_physical(dpr)
    return CaptureRegion(left=left, top=top, width=w, height=h)


def region_description(region: LogicalRegion, screen: QScreen | None) -> str:
    """Human-readable region line for the UI."""
    if mss_uses_logical_coordinates():
        dpr = screen.devicePixelRatio() if screen else 1.0
        return (
            f"Region: {region.width}×{region.height} pt "
            f"(Retina {int(region.width * dpr)}×{int(region.height * dpr)} px)"
        )
    dpr = screen.devicePixelRatio() if screen else 1.0
    w, h = int(region.width * dpr), int(region.height * dpr)
    return f"Region: {region.width}×{region.height} pt → {w}×{h} px (DPR {dpr:.1f})"
