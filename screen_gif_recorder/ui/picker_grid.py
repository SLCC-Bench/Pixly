"""Shared thumbnail tile grid for window/display pickers."""

from __future__ import annotations

from PIL import Image
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

THUMB_W = 200
THUMB_H = 112
TILE_W = THUMB_W + 12
TILE_H = THUMB_H + 52
GRID_COLUMNS = 3

PICKER_GRID_STYLESHEET = """
QScrollArea#pickerScroll {
    background-color: #09090b;
    border: 1px solid #27272a;
    border-radius: 10px;
}
QFrame#pickerTile {
    background-color: #131316;
    border: 1px solid #3f3f46;
    border-radius: 10px;
}
QFrame#pickerTile[selected="true"] {
    background-color: #1e3a5f;
    border-color: #3b82f6;
}
QFrame#pickerTile:hover {
    border-color: #52525b;
}
QLabel#pickerThumb {
    background-color: #09090b;
    border-radius: 6px;
}
QLabel#pickerTitle {
    color: #f4f4f5;
    font-size: 12px;
    font-weight: 600;
}
QLabel#pickerSubtitle {
    color: #a1a1aa;
    font-size: 11px;
}
"""


def image_cover_crop(img: Image.Image, width: int, height: int) -> Image.Image:
    """Scale to fill width×height, cropping overflow (no side letterboxing)."""
    if img.width < 1 or img.height < 1:
        return img
    scale = max(width / img.width, height / img.height)
    new_w = max(1, int(img.width * scale))
    new_h = max(1, int(img.height * scale))
    resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = (new_w - width) // 2
    top = (new_h - height) // 2
    return resized.crop((left, top, left + width, top + height))


def pixmap_cover(pix: QPixmap, width: int, height: int) -> QPixmap:
    if pix.isNull():
        return pix
    return pix.scaled(
        width,
        height,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )


class PickerTile(QFrame):
    """Single picker card: preview on top, title lines below."""

    clicked = pyqtSignal()
    double_clicked = pyqtSignal()

    def __init__(
        self,
        pixmap: QPixmap | None,
        title: str,
        subtitle: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("pickerTile")
        self.setProperty("selected", False)
        self.setFixedSize(TILE_W, TILE_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        self._thumb = QLabel()
        self._thumb.setObjectName("pickerThumb")
        self._thumb.setFixedSize(THUMB_W, THUMB_H)
        self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_thumb(pixmap)
        layout.addWidget(self._thumb, alignment=Qt.AlignmentFlag.AlignHCenter)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("pickerTitle")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        title_lbl.setWordWrap(True)
        title_lbl.setMaximumWidth(THUMB_W)
        layout.addWidget(title_lbl)

        if subtitle:
            sub_lbl = QLabel(subtitle)
            sub_lbl.setObjectName("pickerSubtitle")
            sub_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            sub_lbl.setWordWrap(True)
            sub_lbl.setMaximumWidth(THUMB_W)
            layout.addWidget(sub_lbl)

    def set_thumb(self, pixmap: QPixmap | None) -> None:
        if pixmap is not None and not pixmap.isNull():
            self._thumb.setPixmap(pixmap_cover(pixmap, THUMB_W, THUMB_H))
        else:
            self._thumb.clear()

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        style = self.style()
        style.unpolish(self)
        style.polish(self)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)


class PickerTileGrid(QWidget):
    """Scrollable grid of picker tiles (left-aligned, tight layout)."""

    tile_clicked = pyqtSignal(int)
    tile_double_clicked = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._selected_index = -1
        self._entries: list[tuple[PickerTile, object]] = []

        self._scroll = QScrollArea()
        self._scroll.setObjectName("pickerScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self._container = QWidget()
        self._grid = QGridLayout(self._container)
        self._grid.setContentsMargins(10, 10, 10, 10)
        self._grid.setHorizontalSpacing(10)
        self._grid.setVerticalSpacing(10)
        self._grid.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        self._scroll.setWidget(self._container)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._scroll)

        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

    def clear(self) -> None:
        self._selected_index = -1
        self._entries.clear()
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def add_tile(
        self,
        pixmap: QPixmap | None,
        title: str,
        subtitle: str,
        user_data: object,
    ) -> int:
        index = len(self._entries)
        tile = PickerTile(pixmap, title, subtitle)

        def _on_click(*, idx: int = index) -> None:
            self.select_index(idx)
            self.tile_clicked.emit(idx)

        def _on_double(*, idx: int = index) -> None:
            self.select_index(idx)
            self.tile_double_clicked.emit(idx)

        tile.clicked.connect(_on_click)
        tile.double_clicked.connect(_on_double)

        row, col = divmod(index, GRID_COLUMNS)
        self._grid.addWidget(tile, row, col, Qt.AlignmentFlag.AlignTop)
        self._entries.append((tile, user_data))
        return index

    def select_index(self, index: int) -> None:
        self._selected_index = index
        for i, (tile, _) in enumerate(self._entries):
            tile.set_selected(i == index)

    def selected_data(self) -> object | None:
        if 0 <= self._selected_index < len(self._entries):
            return self._entries[self._selected_index][1]
        return None

    def update_thumbnail(self, index: int, pixmap: QPixmap) -> None:
        if 0 <= index < len(self._entries):
            self._entries[index][0].set_thumb(pixmap)

    def update_thumbnail_for_data(
        self, match_data: object, pixmap: QPixmap, *, match
    ) -> None:
        for i, (_, data) in enumerate(self._entries):
            if match(data, match_data):
                self._entries[i][0].set_thumb(pixmap)
                break
