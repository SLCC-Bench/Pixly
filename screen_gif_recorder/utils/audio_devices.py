"""Discover microphone and system-audio input devices (macOS-focused)."""

from __future__ import annotations

import platform
import re
from dataclasses import dataclass

_SYSTEM_HINTS = re.compile(
    r"blackhole|loopback|soundflower|aggregate|monitor of|virtual",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class AudioDeviceInfo:
    index: int
    name: str
    channels: int
    sample_rate: float


def sounddevice_available() -> bool:
    try:
        import sounddevice  # noqa: F401

        return True
    except ImportError:
        return False


def list_input_devices() -> list[AudioDeviceInfo]:
    if not sounddevice_available():
        return []

    import sounddevice as sd

    devices: list[AudioDeviceInfo] = []
    for index, dev in enumerate(sd.query_devices()):
        if int(dev.get("max_input_channels", 0)) < 1:
            continue
        devices.append(
            AudioDeviceInfo(
                index=index,
                name=str(dev.get("name", f"Device {index}")),
                channels=int(dev["max_input_channels"]),
                sample_rate=float(dev.get("default_samplerate", 48000)),
            )
        )
    return devices


def default_microphone() -> AudioDeviceInfo | None:
    if not sounddevice_available():
        return None

    import sounddevice as sd

    try:
        default_in = sd.default.device[0]
    except (TypeError, IndexError, sd.PortAudioError):
        default_in = None

    for dev in list_input_devices():
        if default_in is not None and dev.index == default_in:
            return dev
    inputs = list_input_devices()
    return inputs[0] if inputs else None


def find_system_audio_device() -> AudioDeviceInfo | None:
    """
  Loopback-style input used for system audio on macOS (e.g. BlackHole).
  Returns None if no suitable device is installed.
  """
    candidates: list[AudioDeviceInfo] = []
    for dev in list_input_devices():
        if _SYSTEM_HINTS.search(dev.name):
            candidates.append(dev)
    if not candidates:
        return None
    # Prefer stereo BlackHole-style devices
    candidates.sort(key=lambda d: (-d.channels, len(d.name)))
    return candidates[0]


def system_audio_setup_hint() -> str:
    if platform.system() != "Darwin":
        return "System audio capture is only supported on macOS."
    return (
        "To record system audio, install a virtual loopback device such as "
        "BlackHole 2ch (brew install blackhole-2ch), then route Mac output through it "
        "in Audio MIDI Setup."
    )
