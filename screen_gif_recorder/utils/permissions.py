"""macOS Screen Recording permission helpers."""

from __future__ import annotations

import platform
import subprocess
import sys


def is_macos() -> bool:
    return platform.system() == "Darwin"


def check_screen_capture_permission() -> bool:
    """
    Best-effort check for Screen Recording permission on macOS 10.15+.
    A successful 1x1 capture via mss indicates permission is granted.
    """
    if not is_macos():
        return True

    try:
        import mss

        with mss.mss() as sct:
            monitor = sct.monitors[0]
            # Tiny grab — fails or returns black if permission denied on some setups
            region = {
                "left": monitor["left"],
                "top": monitor["top"],
                "width": 2,
                "height": 2,
            }
            img = sct.grab(region)
            return img is not None and len(img.rgb) > 0
    except Exception:
        return False


def open_screen_recording_preferences() -> None:
    """Open System Settings → Privacy → Screen Recording (macOS 13+)."""
    if not is_macos():
        return
    # Works on Ventura+; older macOS may ignore unknown pane
    url = "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
    subprocess.run(["open", url], check=False)


def permission_hint_message() -> str:
    return (
        "Screen Recording permission is required.\n\n"
        "Open System Settings → Privacy & Security → Screen Recording,\n"
        "enable this app, then restart the application."
    )


def _accessibility_api_available() -> bool:
    if not is_macos():
        return False
    try:
        from ApplicationServices import AXIsProcessTrusted  # noqa: F401

        return True
    except ImportError:
        return False


def check_accessibility_permission() -> bool:
    """True when this process may install global key monitors (macOS Accessibility)."""
    if not is_macos():
        return True
    if not _accessibility_api_available():
        return False
    from ApplicationServices import AXIsProcessTrusted

    return bool(AXIsProcessTrusted())


def request_accessibility_permission(*, prompt: bool = True) -> bool:
    """
    Ask macOS to trust this app for Accessibility (global ⌘. stop).
    Returns whether the app is already trusted after the call.
    """
    if not is_macos():
        return True
    if not _accessibility_api_available():
        open_accessibility_preferences()
        return False
    from ApplicationServices import (
        AXIsProcessTrustedWithOptions,
        kAXTrustedCheckOptionPrompt,
    )
    from Foundation import NSDictionary, NSNumber

    options = NSDictionary.dictionaryWithObject_forKey_(
        NSNumber.numberWithBool_(bool(prompt)),
        kAXTrustedCheckOptionPrompt,
    )
    return bool(AXIsProcessTrustedWithOptions(options))


def open_accessibility_preferences() -> None:
    if not is_macos():
        return
    url = "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
    subprocess.run(["open", url], check=False)


def accessibility_hint_message() -> str:
    name = "Pixly" if getattr(sys, "frozen", False) else "Python or Terminal"
    return (
        f"Global ⌘. stop needs Accessibility permission for {name}.\n\n"
        "Open System Settings → Privacy & Security → Accessibility,\n"
        "enable Pixly, then try recording again."
    )
