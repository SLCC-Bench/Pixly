"""Full-screen overlay for click-drag region selection (macOS-safe, multi-monitor)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

import mss
from PIL import Image
from PyQt6.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QGuiApplication, QPainter, QPen, QPixmap, QScreen
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QPushButton, QWidget

from screen_gif_recorder.utils.qt_image import pil_to_pixmap


@dataclass(frozen=True)
class LogicalRegion:
    """Selected rectangle in Qt global logical coordinates (points)."""

    x: int
    y: int
    width: int
    height: int

    def to_physical(self, dpr: float) -> tuple[int, int, int, int]:
        """Convert to physical pixels for mss capture (Retina-aware)."""
        return (
            int(self.x * dpr),
            int(self.y * dpr),
            max(1, int(self.width * dpr)),
            max(1, int(self.height * dpr)),
        )


def virtual_desktop_rect() -> QRect:
    """Union of all monitors in global coordinates (use geometry(), not virtualGeometry)."""
    rect = QRect()
    for screen in QGuiApplication.screens():
        rect = rect.united(screen.geometry())
    return rect


def warm_up_displays() -> None:
    """Force Qt to query each display before hiding windows (avoids first-use layout glitches)."""
    for screen in QGuiApplication.screens():
        _ = screen.geometry()
        _ = screen.name()
    QGuiApplication.processEvents()


def region_for_screen(screen: QScreen) -> LogicalRegion:
    geo = screen.geometry()
    return LogicalRegion(
        x=geo.x(),
        y=geo.y(),
        width=geo.width(),
        height=geo.height(),
    )


class _Phase(Enum):
    DRAG = auto()
    CONFIRM = auto()


class _Handle(Enum):
    NONE = auto()
    MOVE = auto()
    TOP_LEFT = auto()
    TOP = auto()
    TOP_RIGHT = auto()
    RIGHT = auto()
    BOTTOM_RIGHT = auto()
    BOTTOM = auto()
    BOTTOM_LEFT = auto()
    LEFT = auto()


_DIM = QColor(0, 0, 0, 150)
_BORDER = QColor(0, 180, 255)
_HANDLE_FILL = QColor(255, 255, 255)
_MIN_SIZE = 8
_HANDLE_HIT = 9
_HANDLE_DRAW = 7

# Live translucent overlays are click-through on macOS; use frozen desktop slices instead.
_LIVE_DIM_OVERLAY = False


@dataclass
class _SharedState:
    phase: _Phase = _Phase.DRAG
    origin_global: QPoint | None = None
    current_global: QPoint | None = None
    pending_global: QRect | None = None
    moving: bool = False
    move_offset: QPoint | None = None
    resize_handle: _Handle = _Handle.NONE
    resize_anchor_global: QRect | None = None
    pointer_global: QPoint | None = None
    tracking_pointer: bool = False
    panels: list["_RegionPanel"] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.panels is None:
            self.panels = []

    def reset_drag(self) -> None:
        self.origin_global = None
        self.current_global = None

    def reset_confirm_adjust(self) -> None:
        self.moving = False
        self.move_offset = None
        self.resize_handle = _Handle.NONE
        self.resize_anchor_global = None

    def active_global_rect(self) -> QRect | None:
        if self.phase == _Phase.CONFIRM and self.pending_global is not None:
            return self.pending_global
        if self.origin_global is not None and self.current_global is not None:
            return QRect(self.origin_global, self.current_global).normalized()
        return None

    def sync_pending_region(self) -> LogicalRegion | None:
        rect = self.pending_global
        if rect is None:
            return None
        return LogicalRegion(
            x=rect.x(),
            y=rect.y(),
            width=rect.width(),
            height=rect.height(),
        )

    def repaint_all(self) -> None:
        for panel in self.panels:
            panel.update()


def _clamp_global_rect(rect: QRect, bounds: QRect) -> QRect:
    w, h = rect.width(), rect.height()
    x = max(bounds.left(), min(rect.x(), bounds.right() - w + 1))
    y = max(bounds.top(), min(rect.y(), bounds.bottom() - h + 1))
    return QRect(x, y, w, h)


def _enforce_min_size(rect: QRect) -> QRect:
    r = rect.normalized()
    if r.width() < _MIN_SIZE:
        r.setRight(r.left() + _MIN_SIZE - 1)
    if r.height() < _MIN_SIZE:
        r.setBottom(r.top() + _MIN_SIZE - 1)
    return r


def _handle_points_global(rect: QRect) -> dict[_Handle, QPoint]:
    cx = (rect.left() + rect.right()) // 2
    cy = (rect.top() + rect.bottom()) // 2
    return {
        _Handle.TOP_LEFT: rect.topLeft(),
        _Handle.TOP: QPoint(cx, rect.top()),
        _Handle.TOP_RIGHT: rect.topRight(),
        _Handle.RIGHT: QPoint(rect.right(), cy),
        _Handle.BOTTOM_RIGHT: rect.bottomRight(),
        _Handle.BOTTOM: QPoint(cx, rect.bottom()),
        _Handle.BOTTOM_LEFT: rect.bottomLeft(),
        _Handle.LEFT: QPoint(rect.left(), cy),
    }


def _hit_test_global(pos: QPoint, rect: QRect) -> _Handle:
    hit = _HANDLE_HIT
    for handle in (
        _Handle.TOP_LEFT,
        _Handle.TOP_RIGHT,
        _Handle.BOTTOM_RIGHT,
        _Handle.BOTTOM_LEFT,
    ):
        pt = _handle_points_global(rect)[handle]
        if abs(pos.x() - pt.x()) <= hit and abs(pos.y() - pt.y()) <= hit:
            return handle

    l, t, r, b = rect.left(), rect.top(), rect.right(), rect.bottom()
    cx, cy = (l + r) // 2, (t + b) // 2
    if abs(pos.y() - t) <= hit and l + hit < pos.x() < r - hit:
        return _Handle.TOP
    if abs(pos.y() - b) <= hit and l + hit < pos.x() < r - hit:
        return _Handle.BOTTOM
    if abs(pos.x() - l) <= hit and t + hit < pos.y() < b - hit:
        return _Handle.LEFT
    if abs(pos.x() - r) <= hit and t + hit < pos.y() < b - hit:
        return _Handle.RIGHT
    if rect.contains(pos):
        return _Handle.MOVE
    return _Handle.NONE


def _resize_global_rect(handle: _Handle, anchor: QRect, pos: QPoint, bounds: QRect) -> QRect:
    l, t, r, b = anchor.left(), anchor.top(), anchor.right(), anchor.bottom()
    x, y = pos.x(), pos.y()

    if handle == _Handle.TOP_LEFT:
        rect = QRect(QPoint(x, y), QPoint(r, b))
    elif handle == _Handle.TOP_RIGHT:
        rect = QRect(QPoint(l, y), QPoint(x, b))
    elif handle == _Handle.BOTTOM_RIGHT:
        rect = QRect(QPoint(l, t), QPoint(x, y))
    elif handle == _Handle.BOTTOM_LEFT:
        rect = QRect(QPoint(x, t), QPoint(r, y))
    elif handle == _Handle.TOP:
        rect = QRect(l, y, anchor.width(), b - y + 1)
    elif handle == _Handle.BOTTOM:
        rect = QRect(l, t, anchor.width(), y - t + 1)
    elif handle == _Handle.LEFT:
        rect = QRect(x, t, r - x + 1, anchor.height())
    elif handle == _Handle.RIGHT:
        rect = QRect(l, t, x - l + 1, anchor.height())
    else:
        return anchor

    return _clamp_global_rect(_enforce_min_size(rect.normalized()), bounds)


def _cursor_for_handle(handle: _Handle) -> Qt.CursorShape:
    return {
        _Handle.TOP_LEFT: Qt.CursorShape.SizeFDiagCursor,
        _Handle.BOTTOM_RIGHT: Qt.CursorShape.SizeFDiagCursor,
        _Handle.TOP_RIGHT: Qt.CursorShape.SizeBDiagCursor,
        _Handle.BOTTOM_LEFT: Qt.CursorShape.SizeBDiagCursor,
        _Handle.TOP: Qt.CursorShape.SizeVerCursor,
        _Handle.BOTTOM: Qt.CursorShape.SizeVerCursor,
        _Handle.LEFT: Qt.CursorShape.SizeHorCursor,
        _Handle.RIGHT: Qt.CursorShape.SizeHorCursor,
        _Handle.MOVE: Qt.CursorShape.OpenHandCursor,
    }.get(handle, Qt.CursorShape.CrossCursor)


class _OverlayKeyFilter(QObject):
    """Global Esc / Enter while the selector is active (mouse uses grabMouse on panels)."""

    def __init__(self, owner: "RegionSelectorOverlay") -> None:
        super().__init__()
        self._owner = owner

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        if self._owner._finished or event.type() != QEvent.Type.KeyPress:
            return False

        from PyQt6.QtGui import QKeyEvent

        if not isinstance(event, QKeyEvent):
            return False

        state = self._owner._state
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if state.phase == _Phase.CONFIRM:
                self._owner._accept_selection()
            return True
        if event.key() == Qt.Key.Key_Escape:
            self._owner._finish(cancel=True)
            return True
        return False


class _RegionPanel(QWidget):
    """One overlay per physical display — macOS only delivers events per screen."""

    def __init__(
        self,
        state: _SharedState,
        screen: QScreen,
        desktop_bg: QPixmap | None,
        owner: "RegionSelectorOverlay",
    ) -> None:
        super().__init__(None)
        self._state = state
        self._screen = screen
        self._desktop_bg = desktop_bg
        self._owner = owner
        self._global_origin = screen.geometry().topLeft()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Window,
        )
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        if hasattr(Qt.WidgetAttribute, "WA_MacAlwaysShowToolWindow"):
            self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow, True)

        if _LIVE_DIM_OVERLAY:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            if hasattr(Qt.WidgetAttribute, "WA_NoSystemBackground"):
                self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
            self.setAutoFillBackground(False)

        self.setGeometry(screen.geometry())

    def sync_screen_geometry(self) -> None:
        geo = self._screen.geometry()
        self._global_origin = geo.topLeft()
        self.setGeometry(geo)

    def set_desktop_background(self, pixmap: QPixmap | None) -> None:
        self._desktop_bg = pixmap
        self.update()

    def _local_from_global(self, global_pos: QPoint) -> QPoint:
        return global_pos - self._global_origin

    def _global_from_event(self, event) -> QPoint:
        return event.globalPosition().toPoint()

    def _paint_dim_around(self, painter: QPainter, sel_local: QRect) -> None:
        full = self.rect()
        painter.fillRect(0, 0, full.width(), sel_local.top(), _DIM)
        painter.fillRect(
            0,
            sel_local.bottom(),
            full.width(),
            full.height() - sel_local.bottom(),
            _DIM,
        )
        painter.fillRect(0, sel_local.top(), sel_local.left(), sel_local.height(), _DIM)
        painter.fillRect(
            sel_local.right() + 1,
            sel_local.top(),
            full.width() - sel_local.right() - 1,
            sel_local.height(),
            _DIM,
        )

    def _selection_local(self) -> QRect | None:
        grect = self._state.active_global_rect()
        if grect is None:
            return None
        local = grect.translated(-self._global_origin.x(), -self._global_origin.y())
        return local.intersected(self.rect())

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if not _LIVE_DIM_OVERLAY:
            if self._desktop_bg is not None and not self._desktop_bg.isNull():
                painter.drawPixmap(0, 0, self._desktop_bg)
            else:
                painter.fillRect(self.rect(), QColor(40, 40, 45))

        sel = self._selection_local()
        gsel = self._state.active_global_rect()

        has_bg = (
            not _LIVE_DIM_OVERLAY
            and self._desktop_bg is not None
            and not self._desktop_bg.isNull()
        )

        if gsel is not None and gsel.width() >= 2 and gsel.height() >= 2 and sel is not None:
            if sel.width() >= 2 and sel.height() >= 2:
                self._paint_dim_around(painter, sel)
                pen = QPen(_BORDER, 2)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(sel)
                if self._state.phase == _Phase.CONFIRM:
                    painter.setPen(QColor(255, 255, 255))
                    painter.drawText(
                        sel.adjusted(8, 8, 0, 0),
                        Qt.AlignmentFlag.AlignLeft,
                        f"{gsel.width()} × {gsel.height()}",
                    )
                    self._paint_handles(painter, sel)
        elif has_bg:
            painter.fillRect(self.rect(), _DIM)
        else:
            painter.fillRect(self.rect(), QColor(40, 40, 45))
            painter.fillRect(self.rect(), _DIM)

        painter.setPen(QColor(255, 255, 255))
        msg = (
            "Click and drag to select  •  Esc to cancel"
            if self._state.phase == _Phase.DRAG
            else "Drag handles to resize  •  Drag inside to move  •  Enter = confirm  •  Esc = cancel"
        )
        painter.drawText(
            self.rect().adjusted(0, 20, 0, 0),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            msg,
        )
        painter.end()

    def _paint_handles(self, painter: QPainter, rect: QRect) -> None:
        half = _HANDLE_DRAW // 2
        painter.setBrush(_HANDLE_FILL)
        painter.setPen(QPen(_BORDER, 1))
        cx = (rect.left() + rect.right()) // 2
        cy = (rect.top() + rect.bottom()) // 2
        points = [
            rect.topLeft(),
            QPoint(cx, rect.top()),
            rect.topRight(),
            QPoint(rect.right(), cy),
            rect.bottomRight(),
            QPoint(cx, rect.bottom()),
            rect.bottomLeft(),
            QPoint(rect.left(), cy),
        ]
        for pt in points:
            painter.drawRect(
                pt.x() - half,
                pt.y() - half,
                _HANDLE_DRAW,
                _HANDLE_DRAW,
            )

    def _release_grab(self) -> None:
        if self.mouseGrabber() is self:
            self.releaseMouse()

    def _update_cursor(self, global_pos: QPoint) -> None:
        if self._state.moving:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if self._state.resize_handle not in (_Handle.NONE, _Handle.MOVE):
            self.setCursor(_cursor_for_handle(self._state.resize_handle))
            return
        if self._state.phase == _Phase.CONFIRM and self._state.pending_global is not None:
            self.setCursor(
                _cursor_for_handle(_hit_test_global(global_pos, self._state.pending_global))
            )
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.RightButton:
            self._owner._finish(cancel=True)
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return

        gp = self._global_from_event(event)
        self._state.pointer_global = gp
        bounds = virtual_desktop_rect()

        if self._state.phase == _Phase.CONFIRM and self._state.pending_global is not None:
            handle = _hit_test_global(gp, self._state.pending_global)
            if handle in (
                _Handle.TOP_LEFT,
                _Handle.TOP,
                _Handle.TOP_RIGHT,
                _Handle.RIGHT,
                _Handle.BOTTOM_RIGHT,
                _Handle.BOTTOM,
                _Handle.BOTTOM_LEFT,
                _Handle.LEFT,
            ):
                self._state.resize_handle = handle
                self._state.resize_anchor_global = QRect(self._state.pending_global)
                self._state.tracking_pointer = True
                self.grabMouse()
                self._update_cursor(gp)
                return
            if handle == _Handle.MOVE:
                self._state.moving = True
                self._state.move_offset = gp - self._state.pending_global.topLeft()
                self._state.tracking_pointer = True
                self.grabMouse()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                return
            return

        self._state.phase = _Phase.DRAG
        self._state.origin_global = gp
        self._state.current_global = gp
        self._state.tracking_pointer = True
        self.grabMouse()
        self.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        self._state.repaint_all()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        gp = self._global_from_event(event)
        self._state.pointer_global = gp
        if self._state.tracking_pointer:
            self._owner._on_pointer_move()
        else:
            self._update_cursor(gp)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if not self._state.tracking_pointer:
            return
        self._state.pointer_global = self._global_from_event(event)
        self._release_grab()
        self._owner._on_pointer_release()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if self._state.phase == _Phase.CONFIRM and event.button() == Qt.MouseButton.LeftButton:
            self._owner._accept_selection()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._state.phase == _Phase.CONFIRM:
                self._owner._accept_selection()
            return
        if event.key() == Qt.Key.Key_Escape:
            self._owner._finish(cancel=True)


class RegionSelectorOverlay(QObject):
    """
    Drag a rectangle, then confirm.
    Uses one window per display so every monitor is selectable on macOS.
    """

    region_selected = pyqtSignal(object)
    cancelled = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._state = _SharedState()
        self._panels: list[_RegionPanel] = []
        self._confirm_bar: QWidget | None = None
        self._desktop_slices: dict[int, QPixmap | None] = {}
        self._key_filter = _OverlayKeyFilter(self)
        self._finished = False
        self._filter_installed = False

    def _install_key_filter(self) -> None:
        app = QApplication.instance()
        if app is not None and not self._filter_installed:
            app.installEventFilter(self._key_filter)
            self._filter_installed = True

    def _remove_key_filter(self) -> None:
        app = QApplication.instance()
        if app is not None and self._filter_installed:
            app.removeEventFilter(self._key_filter)
            self._filter_installed = False
        self._state.tracking_pointer = False

    def _capture_desktop_slices(self) -> dict[int, QPixmap | None]:
        desktop = virtual_desktop_rect()
        slices: dict[int, QPixmap | None] = {id(s): None for s in QGuiApplication.screens()}

        if desktop.width() < 1 or desktop.height() < 1:
            return slices

        try:
            with mss.mss() as sct:
                # monitors[0] is the combined virtual screen on macOS multi-display setups.
                mon = sct.monitors[0]
                shot = sct.grab(mon)
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            full = pil_to_pixmap(img)
            origin_x = int(mon["left"])
            origin_y = int(mon["top"])
            if full.width() != mon["width"] or full.height() != mon["height"]:
                full = full.scaled(
                    mon["width"],
                    mon["height"],
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            for screen in QGuiApplication.screens():
                geo = screen.geometry()
                ox = geo.x() - origin_x
                oy = geo.y() - origin_y
                slices[id(screen)] = full.copy(ox, oy, geo.width(), geo.height())
        except Exception:
            pass
        return slices

    def _hide_panels_for_capture(self) -> None:
        for panel in self._panels:
            panel.hide()
        QGuiApplication.processEvents()

    def _show_panels_after_capture(self) -> None:
        for panel in self._panels:
            panel.show()
            panel.raise_()
        if self._panels:
            self._panels[0].activateWindow()
            self._panels[0].setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        self._ensure_on_top()

    def _build_panels(self, *, visible: bool) -> None:
        """Create one panel per display; optionally show them."""
        self._panels.clear()
        self._state.panels.clear()

        for screen in QGuiApplication.screens():
            panel = _RegionPanel(
                self._state,
                screen,
                self._desktop_slices.get(id(screen)),
                self,
            )
            if not visible:
                panel.setWindowOpacity(0.0)
            self._panels.append(panel)
            self._state.panels.append(panel)

        for panel in self._panels:
            panel.show()
            panel.raise_()

    def prepare_invisible_panels(self) -> None:
        """
        Show fully transparent overlays on every display before the host window
        moves aside — prevents macOS from jumping to another monitor/Space.
        """
        if self._finished:
            return

        warm_up_displays()
        self._state = _SharedState()
        self._desktop_slices = {}
        self._install_key_filter()
        self._build_panels(visible=False)
        QGuiApplication.processEvents()

    def reveal_with_desktop(self) -> None:
        """Capture the real desktop, then show the dimmed snapshot on each panel."""
        if self._finished or not self._panels:
            return

        warm_up_displays()
        for panel in self._panels:
            panel.sync_screen_geometry()

        if _LIVE_DIM_OVERLAY:
            for panel in self._panels:
                panel.setWindowOpacity(1.0)
            self._show_panels_after_capture()
            return

        self._hide_panels_for_capture()
        self._desktop_slices = self._capture_desktop_slices()
        for panel in self._panels:
            panel.set_desktop_background(self._desktop_slices.get(id(panel._screen)))
            panel.setWindowOpacity(1.0)
        self._show_panels_after_capture()

    def present(self) -> None:
        """Single-step present (used when host is already off-screen)."""
        if self._finished:
            return

        warm_up_displays()
        self._state = _SharedState()
        self._desktop_slices = (
            {} if _LIVE_DIM_OVERLAY else self._capture_desktop_slices()
        )
        self._install_key_filter()
        self._build_panels(visible=True)

        if self._panels:
            self._panels[0].activateWindow()
            self._panels[0].setFocus(Qt.FocusReason.ActiveWindowFocusReason)

        QGuiApplication.processEvents()
        QTimer.singleShot(0, self._ensure_on_top)
        QTimer.singleShot(50, self._ensure_on_top)

    def _ensure_on_top(self) -> None:
        if self._finished:
            return
        for panel in self._panels:
            panel.raise_()
            panel.activateWindow()
        if self._panels:
            self._panels[0].setFocus()

    def _on_pointer_move(self) -> None:
        gp = self._state.pointer_global
        if gp is None:
            return
        bounds = virtual_desktop_rect()

        if self._state.resize_handle not in (_Handle.NONE, _Handle.MOVE):
            if self._state.resize_anchor_global is not None:
                self._state.pending_global = _resize_global_rect(
                    self._state.resize_handle,
                    self._state.resize_anchor_global,
                    gp,
                    bounds,
                )
            self._state.repaint_all()
            return

        if self._state.moving and self._state.pending_global is not None:
            if self._state.move_offset is not None:
                new_top_left = gp - self._state.move_offset
                moved = QRect(new_top_left, self._state.pending_global.size())
                self._state.pending_global = _clamp_global_rect(moved, bounds)
            self._state.repaint_all()
            return

        if self._state.phase == _Phase.DRAG and self._state.origin_global is not None:
            self._state.current_global = gp
            self._state.repaint_all()

    def _on_pointer_release(self) -> None:
        self._state.tracking_pointer = False
        gp = self._state.pointer_global

        if self._state.moving:
            self._state.moving = False
            self._state.move_offset = None
            if gp is not None:
                for panel in self._panels:
                    panel._update_cursor(gp)
            return

        if self._state.resize_handle not in (_Handle.NONE, _Handle.MOVE):
            self._state.resize_handle = _Handle.NONE
            self._state.resize_anchor_global = None
            if gp is not None:
                for panel in self._panels:
                    panel._update_cursor(gp)
            return

        if self._state.phase != _Phase.DRAG or self._state.origin_global is None:
            return

        if gp is None:
            return

        rect = QRect(self._state.origin_global, gp).normalized()
        self._state.reset_drag()

        if rect.width() < _MIN_SIZE or rect.height() < _MIN_SIZE:
            self._state.repaint_all()
            return

        bounds = virtual_desktop_rect()
        self._state.pending_global = _clamp_global_rect(rect, bounds)
        self._state.phase = _Phase.CONFIRM
        self._show_confirm_bar()
        if gp is not None:
            for panel in self._panels:
                panel._update_cursor(gp)
        self._state.repaint_all()

    def _show_confirm_bar(self) -> None:
        self._hide_confirm_bar()
        if not self._panels or self._state.pending_global is None:
            return

        bar = QWidget(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        bar.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        bar.setStyleSheet("background-color: rgb(30, 30, 34); border-radius: 10px;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 10, 12, 10)

        btn_use = QPushButton("Use this region")
        btn_redraw = QPushButton("Redraw")
        btn_cancel = QPushButton("Cancel")
        for btn in (btn_use, btn_redraw, btn_cancel):
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_use.setStyleSheet(
            "QPushButton { background: #0a84ff; color: white; border: none; "
            "border-radius: 6px; padding: 8px 14px; font-weight: 600; }"
        )
        for btn in (btn_redraw, btn_cancel):
            btn.setStyleSheet(
                "QPushButton { background: #3d4048; color: white; border: none; "
                "border-radius: 6px; padding: 8px 14px; }"
            )

        btn_use.clicked.connect(self._accept_selection)
        btn_redraw.clicked.connect(self._redraw)
        btn_cancel.clicked.connect(lambda: self._finish(cancel=True))

        layout.addWidget(btn_use)
        layout.addWidget(btn_redraw)
        layout.addWidget(btn_cancel)

        bar.adjustSize()
        sel = self._state.pending_global
        cx = sel.center().x()
        cy = sel.top() + 52
        bar.move(max(0, cx - bar.width() // 2), max(0, cy))
        bar.show()
        bar.raise_()
        self._confirm_bar = bar
        if self._panels:
            self._panels[0].setFocus()

    def _hide_confirm_bar(self) -> None:
        if self._confirm_bar is not None:
            self._confirm_bar.close()
            self._confirm_bar.deleteLater()
            self._confirm_bar = None

    def _redraw(self) -> None:
        self._hide_confirm_bar()
        self._state.pending_global = None
        self._state.phase = _Phase.DRAG
        self._state.reset_drag()
        self._state.reset_confirm_adjust()
        for panel in self._panels:
            panel.setCursor(Qt.CursorShape.CrossCursor)
            panel.setFocus()
        self._state.repaint_all()

    def _accept_selection(self) -> None:
        region = self._state.sync_pending_region()
        if region is None:
            return
        self.region_selected.emit(region)
        self._finish(cancel=False)

    def _finish(self, *, cancel: bool) -> None:
        if self._finished:
            return
        self._finished = True
        self._remove_key_filter()
        self._hide_confirm_bar()
        if cancel:
            self.cancelled.emit()
        self._desktop_slices.clear()
        for panel in self._panels:
            panel.close()
        self._panels.clear()
        self._state.panels.clear()
        self.deleteLater()

    def close(self) -> None:
        """Compatibility with callers that close the overlay directly."""
        self._finish(cancel=True)

