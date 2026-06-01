"""List and track browser windows on macOS for accurate region capture."""

from __future__ import annotations

import platform
import subprocess
from dataclasses import dataclass

BROWSER_OWNERS = frozenset(
    {
        "Google Chrome",
        "Safari",
        "Firefox",
        "Arc",
        "Microsoft Edge",
        "Brave Browser",
        "Chromium",
        "Opera",
        "Vivaldi",
    }
)

SKIP_TITLES = frozenset({"", "Pixly — Screen to GIF", "Pixly"})
_BOUNDS_MATCH_TOLERANCE = 12


@dataclass(frozen=True)
class WindowInfo:
    """A browser window; window_id is CGWindowNumber when from Quartz."""

    window_id: int
    window_index: int  # 1-based index in the app (for focus via AppleScript)
    title: str
    owner: str
    x: int
    y: int
    width: int
    height: int

    @property
    def display_name(self) -> str:
        title = self.title.strip() or "(untitled)"
        return f"{title} — {self.owner}"

    def to_logical_region(self):
        from screen_gif_recorder.ui.region_selector import LogicalRegion

        return LogicalRegion(
            x=self.x,
            y=self.y,
            width=self.width,
            height=self.height,
        )


def macos_window_api_available() -> bool:
    return platform.system() == "Darwin"


def capture_window_thumbnail(
    window_id: int,
    *,
    max_width: int | None = None,
    max_height: int | None = None,
):
    from screen_gif_recorder.ui.picker_grid import THUMB_H, THUMB_W

    if max_width is None:
        max_width = THUMB_W
    if max_height is None:
        max_height = THUMB_H
    """
    Grab a preview of a window for the picker UI.
    Requires Screen Recording permission on recent macOS.
    """
    if not window_id or not _quartz_available():
        return None

    try:
        import Quartz
        from PIL import Image

        from screen_gif_recorder.utils.qt_image import pil_to_pixmap

        cg_image = Quartz.CGWindowListCreateImage(
            Quartz.CGRectNull,
            Quartz.kCGWindowListOptionIncludingWindow,
            window_id,
            Quartz.kCGWindowImageBoundsIgnoreFraming,
        )
        if cg_image is None:
            return None

        width = Quartz.CGImageGetWidth(cg_image)
        height = Quartz.CGImageGetHeight(cg_image)
        if width < 1 or height < 1:
            return None

        bpr = Quartz.CGImageGetBytesPerRow(cg_image)
        provider = Quartz.CGImageGetDataProvider(cg_image)
        data = bytes(Quartz.CGDataProviderCopyData(provider))
        from screen_gif_recorder.ui.picker_grid import image_cover_crop

        img = Image.frombytes("RGBA", (width, height), data, "raw", "BGRA", bpr, 1)
        img = img.convert("RGB")
        img = image_cover_crop(img, max_width, max_height)
        return pil_to_pixmap(img)
    except Exception:
        return None


def placeholder_window_thumbnail(
    owner: str,
    *,
    width: int | None = None,
    height: int | None = None,
):
    from screen_gif_recorder.ui.picker_grid import THUMB_H, THUMB_W

    if width is None:
        width = THUMB_W
    if height is None:
        height = THUMB_H
    """Fallback tile when Screen Recording blocks window previews."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap

    pix = QPixmap(width, height)
    pix.fill(QColor(26, 26, 31))
    painter = QPainter(pix)
    painter.setPen(QColor(113, 113, 122))
    painter.setFont(QFont("Helvetica", 28, QFont.Weight.Bold))
    letter = (owner.strip()[:1] or "?").upper()
    painter.drawText(pix.rect(), int(Qt.AlignmentFlag.AlignCenter), letter)
    painter.end()
    return pix


def _quartz_available() -> bool:
    try:
        import Quartz  # noqa: F401

        return True
    except ImportError:
        return False


def _run_osascript(script: str, *argv: str) -> str:
    cmd = ["osascript", "-e", script]
    if argv:
        cmd.extend(argv)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _bounds_from_quartz_dict(bounds: dict) -> tuple[int, int, int, int] | None:
    width = int(round(bounds.get("Width", 0)))
    height = int(round(bounds.get("Height", 0)))
    if width < 80 or height < 80:
        return None
    return (
        int(round(bounds.get("X", 0))),
        int(round(bounds.get("Y", 0))),
        width,
        height,
    )


def _titles_match(a: str, b: str) -> bool:
    a, b = a.strip(), b.strip()
    if not a or not b:
        return False
    return a == b or a.startswith(b) or b.startswith(a)


def _bounds_match(
    ax: int,
    ay: int,
    aw: int,
    ah: int,
    bx: int,
    by: int,
    bw: int,
    bh: int,
    tolerance: int = _BOUNDS_MATCH_TOLERANCE,
) -> bool:
    return (
        abs(ax - bx) <= tolerance
        and abs(ay - by) <= tolerance
        and abs(aw - bw) <= tolerance
        and abs(ah - bh) <= tolerance
    )


def resolve_applescript_window_index(info: WindowInfo) -> int:
    """Map a Quartz-listed window to the browser's real window index for AppleScript."""
    for candidate in _list_app_windows_applescript(info.owner):
        if _titles_match(candidate.title, info.title) and _bounds_match(
            info.x, info.y, info.width, info.height,
            candidate.x, candidate.y, candidate.width, candidate.height,
        ):
            return candidate.window_index
    return info.window_index


def _enrich_window_indices(windows: list[WindowInfo]) -> list[WindowInfo]:
    """Replace enumeration-order indices with AppleScript window indices."""
    enriched: list[WindowInfo] = []
    for win in windows:
        idx = resolve_applescript_window_index(win)
        if idx == win.window_index:
            enriched.append(win)
        else:
            enriched.append(
                WindowInfo(
                    window_id=win.window_id,
                    window_index=idx,
                    title=win.title,
                    owner=win.owner,
                    x=win.x,
                    y=win.y,
                    width=win.width,
                    height=win.height,
                )
            )
    return enriched


def _list_via_quartz(*, browsers_only: bool) -> list[WindowInfo]:
    import Quartz

    options = (
        Quartz.kCGWindowListOptionOnScreenOnly
        | Quartz.kCGWindowListExcludeDesktopElements
    )
    raw = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID) or []

    results: list[WindowInfo] = []
    index_by_owner: dict[str, int] = {}

    for entry in raw:
        owner = entry.get(Quartz.kCGWindowOwnerName, "") or ""
        if browsers_only and owner not in BROWSER_OWNERS:
            continue
        if entry.get(Quartz.kCGWindowLayer, 0) != 0:
            continue

        bounds = entry.get(Quartz.kCGWindowBounds)
        if not bounds:
            continue
        parsed = _bounds_from_quartz_dict(bounds)
        if parsed is None:
            continue

        x, y, width, height = parsed
        title = entry.get(Quartz.kCGWindowName, "") or ""
        if title in SKIP_TITLES:
            continue

        window_id = int(entry.get(Quartz.kCGWindowNumber, 0))
        index_by_owner[owner] = index_by_owner.get(owner, 0) + 1

        results.append(
            WindowInfo(
                window_id=window_id,
                window_index=index_by_owner[owner],
                title=title,
                owner=owner,
                x=x,
                y=y,
                width=width,
                height=height,
            )
        )

    return results


def _list_app_windows_applescript(app_name: str) -> list[WindowInfo]:
    script = f'''
    tell application "{app_name}"
        set outText to ""
        try
            repeat with i from 1 to (count of windows)
                set w to window i
                set b to bounds of w
                set t to name of w
                set leftBound to item 1 of b
                set topBound to item 2 of b
                set rightBound to item 3 of b
                set bottomBound to item 4 of b
                set outText to outText & i & (ASCII character 31) & t & (ASCII character 31) & leftBound & (ASCII character 31) & topBound & (ASCII character 31) & rightBound & (ASCII character 31) & bottomBound & (ASCII character 30)
            end repeat
        end try
        return outText
    end tell
    '''
    raw = _run_osascript(script)
    if not raw:
        return []

    windows: list[WindowInfo] = []
    for block in raw.split(chr(30)):
        if not block.strip():
            continue
        parts = block.split(chr(31))
        if len(parts) != 6:
            continue
        index_s, title, left_s, top_s, right_s, bottom_s = parts
        if title in SKIP_TITLES:
            continue
        try:
            idx = int(index_s)
            left, top, right, bottom = (
                int(float(left_s)),
                int(float(top_s)),
                int(float(right_s)),
                int(float(bottom_s)),
            )
        except ValueError:
            continue
        width, height = right - left, bottom - top
        if width < 80 or height < 80:
            continue
        windows.append(
            WindowInfo(
                window_id=0,
                window_index=idx,
                title=title,
                owner=app_name,
                x=left,
                y=top,
                width=width,
                height=height,
            )
        )
    return windows


def list_on_screen_windows(
    *,
    browsers_only: bool = True,
    enrich_indices: bool = True,
) -> list[WindowInfo]:
    if platform.system() != "Darwin":
        return []

    results: list[WindowInfo] = []
    if _quartz_available():
        results = _list_via_quartz(browsers_only=browsers_only)

    if not results:
        apps = BROWSER_OWNERS if browsers_only else BROWSER_OWNERS
        for app in apps:
            results.extend(_list_app_windows_applescript(app))

    results.sort(key=lambda w: (w.owner.lower(), w.title.lower()))
    if enrich_indices:
        return _enrich_window_indices(results)
    return results


def refresh_window_bounds(info: WindowInfo) -> WindowInfo | None:
    """Re-read window position (call right before recording)."""
    if platform.system() != "Darwin":
        return None

    if info.window_id and _quartz_available():
        import Quartz

        raw = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionIncludingWindow,
            info.window_id,
        )
        if raw:
            entry = raw[0]
            bounds = entry.get(Quartz.kCGWindowBounds)
            if bounds:
                parsed = _bounds_from_quartz_dict(bounds)
                if parsed:
                    x, y, width, height = parsed
                    title = entry.get(Quartz.kCGWindowName, "") or info.title
                    return WindowInfo(
                        window_id=info.window_id,
                        window_index=info.window_index,
                        title=title,
                        owner=info.owner,
                        x=x,
                        y=y,
                        width=width,
                        height=height,
                    )

    script = f'''
    tell application "{info.owner}"
        if (count of windows) < {info.window_index} then return ""
        set w to window {info.window_index}
        set b to bounds of w
        set t to name of w
        return t & (ASCII character 31) & (item 1 of b) & (ASCII character 31) & (item 2 of b) & (ASCII character 31) & (item 3 of b) & (ASCII character 31) & (item 4 of b)
    end tell
    '''
    raw = _run_osascript(script)
    if not raw:
        return None
    parts = raw.split(chr(31))
    if len(parts) != 5:
        return None
    title, left_s, top_s, right_s, bottom_s = parts
    try:
        left, top, right, bottom = (
            int(float(left_s)),
            int(float(top_s)),
            int(float(right_s)),
            int(float(bottom_s)),
        )
    except ValueError:
        return None
    width, height = right - left, bottom - top
    if width < 80 or height < 80:
        return None
    return WindowInfo(
        window_id=info.window_id,
        window_index=info.window_index,
        title=title,
        owner=info.owner,
        x=left,
        y=top,
        width=width,
        height=height,
    )


def focus_browser_window(info: WindowInfo, *, activate_app: bool = False) -> bool:
    """
    Raise the chosen window on its current display.

    Avoids ``activate`` by default — on multi-monitor Macs, ``activate`` often
    moves the window to the built-in display while capture still targets the
    old coordinates on the external monitor.
    """
    if platform.system() != "Darwin":
        return False

    win_index = str(resolve_applescript_window_index(info))

    # System Events raises the window where it already lives (needs Accessibility).
    raise_script = """
    on run argv
        set appName to item 1 of argv
        set winIndex to item 2 of argv as integer
        tell application "System Events"
            if not (exists process appName) then return "missing"
            tell process appName
                if (count of windows) < winIndex then return "missing"
                set frontmost to true
                perform action "AXRaise" of window winIndex
                return "ok"
            end tell
        end tell
    end run
    """
    out = _run_osascript(raise_script, info.owner, win_index)
    if out == "ok":
        return True

    if not activate_app:
        return False

    script = """
    on run argv
        set appName to item 1 of argv
        set winIndex to item 2 of argv as integer
        tell application appName
            activate
            if (count of windows) >= winIndex then
                set index of window winIndex to 1
                return "ok"
            end if
        end tell
        return "missing"
    end run
    """
    out = _run_osascript(script, info.owner, win_index)
    return out == "ok"
