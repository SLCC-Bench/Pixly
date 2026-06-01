"""Convert PIL images to Qt pixmaps without stride artifacts or ImageQt crashes."""

from __future__ import annotations

from PIL import Image
from PyQt6.QtGui import QImage, QPixmap


def pil_to_pixmap(image: Image.Image) -> QPixmap:
    """
    PIL → QPixmap with 4-byte-aligned rows.

    Raw QImage(width*3) skews when width*3 % 4 != 0 (e.g. 1710 px wide).
    ImageQt can segfault on large images when the PIL buffer is freed early.
    """
    rgb = image.convert("RGB")
    width, height = rgb.size
    src = rgb.tobytes("raw", "RGB")
    stride = ((width * 3 + 3) // 4) * 4
    buf = bytearray(stride * height)
    row_bytes = width * 3
    for y in range(height):
        offset = y * row_bytes
        buf[y * stride : y * stride + row_bytes] = src[offset : offset + row_bytes]

    # .copy() so Qt owns pixels (safe after `buf` is garbage-collected)
    qimg = QImage(bytes(buf), width, height, stride, QImage.Format.Format_RGB888).copy()
    return QPixmap.fromImage(qimg)
