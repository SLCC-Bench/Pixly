"""System-wide ⌘. stop hotkey on macOS (works while another app is focused)."""

from __future__ import annotations

import platform
from typing import Callable, Optional

_NS_COMMAND = 1 << 20
_KEY_PERIOD = 47

_STOP_CALLBACK: Optional[Callable[[], None]] = None
_LOCAL_MONITOR: object | None = None
_GLOBAL_MONITOR: object | None = None


def global_stop_hotkey_available() -> bool:
    if platform.system() != "Darwin":
        return False
    try:
        import AppKit  # noqa: F401
    except ImportError:
        return False
    return True


def _device_independent_flags(event) -> int:
    import AppKit as appkit

    mask = getattr(appkit, "NSEventModifierFlagDeviceIndependentFlagsMask", 0xFFFF0000)
    return int(event.modifierFlags()) & int(mask)


def _is_cmd_period(event) -> bool:
    flags = _device_independent_flags(event)
    if (flags & _NS_COMMAND) == 0:
        return False
    if int(event.keyCode()) == _KEY_PERIOD:
        return True
    try:
        chars = event.charactersIgnoringModifiers()
        if chars and chars[0] == ".":
            return True
    except Exception:
        pass
    return False


def _handle_key(event) -> None:
    if _is_cmd_period(event) and _STOP_CALLBACK is not None:
        _STOP_CALLBACK()


def _local_handler(event):
    if _is_cmd_period(event):
        _handle_key(event)
        return None
    return event


def _global_handler(event) -> None:
    _handle_key(event)


def _key_down_event_mask() -> int:
    """NSEvent key-down mask (name differs across PyObjC / SDK versions)."""
    import AppKit as appkit

    for name in ("NSEventMaskKeyDown", "NSKeyDownMask"):
        mask = getattr(appkit, name, None)
        if mask is not None:
            return int(mask)
    return 1 << 10  # NSEventMaskKeyDown


def install_global_stop_hotkey(callback: Callable[[], None]) -> tuple[bool, bool]:
    """
    Register ⌘. for stop.

    Returns (installed, global_ok).
    global_ok is False when Accessibility permission is missing (Esc still works in-app).
    """
    global _STOP_CALLBACK, _LOCAL_MONITOR, _GLOBAL_MONITOR

    if not global_stop_hotkey_available():
        return False, False

    from AppKit import NSEvent

    uninstall_global_stop_hotkey()
    _STOP_CALLBACK = callback

    mask = _key_down_event_mask()
    try:
        _LOCAL_MONITOR = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            mask, _local_handler
        )
    except Exception:
        _LOCAL_MONITOR = None
    try:
        _GLOBAL_MONITOR = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            mask, _global_handler
        )
    except Exception:
        _GLOBAL_MONITOR = None

    global_ok = _GLOBAL_MONITOR is not None
    local_ok = _LOCAL_MONITOR is not None
    installed = local_ok or global_ok
    if not installed:
        uninstall_global_stop_hotkey()
    return installed, global_ok


def uninstall_global_stop_hotkey() -> None:
    global _STOP_CALLBACK, _LOCAL_MONITOR, _GLOBAL_MONITOR

    if not global_stop_hotkey_available():
        _STOP_CALLBACK = None
        return

    from AppKit import NSEvent

    if _LOCAL_MONITOR is not None:
        NSEvent.removeMonitor_(_LOCAL_MONITOR)
        _LOCAL_MONITOR = None
    if _GLOBAL_MONITOR is not None:
        NSEvent.removeMonitor_(_GLOBAL_MONITOR)
        _GLOBAL_MONITOR = None
    _STOP_CALLBACK = None
