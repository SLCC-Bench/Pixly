"""Record microphone and/or system audio alongside screen capture."""

from __future__ import annotations

import threading
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from screen_gif_recorder.utils.audio_devices import (
    AudioDeviceInfo,
    default_microphone,
    find_system_audio_device,
    sounddevice_available,
)

SAMPLE_RATE = 48_000


@dataclass
class AudioCaptureConfig:
    record_mic: bool = False
    record_system: bool = False
    mute_mic: bool = False
    mute_system: bool = False


@dataclass
class AudioCaptureResult:
    mic_path: Path | None = None
    system_path: Path | None = None
    sample_rate: int = SAMPLE_RATE

    def has_audio(self) -> bool:
        for path in (self.mic_path, self.system_path):
            if path is not None and path.is_file() and path.stat().st_size > 44:
                return True
        return False


class _WavWriter:
    def __init__(self, path: Path, channels: int) -> None:
        self._path = path
        self._channels = channels
        self._wf = wave.open(str(path), "wb")
        self._wf.setnchannels(channels)
        self._wf.setsampwidth(2)
        self._wf.setframerate(SAMPLE_RATE)
        self._lock = threading.Lock()

    def write(self, data: np.ndarray) -> None:
        if data.size == 0:
            return
        if data.ndim == 1:
            data = data.reshape(-1, 1)
        pcm = np.clip(data, -1.0, 1.0)
        pcm = (pcm * 32767.0).astype(np.int16)
        with self._lock:
            self._wf.writeframes(pcm.tobytes())

    def close(self) -> None:
        with self._lock:
            self._wf.close()


class AudioRecorder:
    """Captures one or two input streams to WAV files in a workspace directory."""

    def __init__(self, config: AudioCaptureConfig, output_dir: Path) -> None:
        self._config = config
        self._output_dir = output_dir
        self._mic_writer: _WavWriter | None = None
        self._system_writer: _WavWriter | None = None
        self._streams: list = []
        self._mic_device: AudioDeviceInfo | None = None
        self._system_device: AudioDeviceInfo | None = None
        self._mic_muted = config.mute_mic
        self._system_muted = config.mute_system
        self._lock = threading.Lock()

    @property
    def mic_muted(self) -> bool:
        return self._mic_muted

    @mic_muted.setter
    def mic_muted(self, value: bool) -> None:
        self._mic_muted = value

    @property
    def system_muted(self) -> bool:
        return self._system_muted

    @system_muted.setter
    def system_muted(self, value: bool) -> None:
        self._system_muted = value

    def start(self) -> None:
        if not sounddevice_available():
            raise RuntimeError("Audio capture requires the sounddevice package.")

        import sounddevice as sd

        want_mic = self._config.record_mic
        want_system = self._config.record_system

        if want_mic:
            self._mic_device = default_microphone()
            if self._mic_device is None:
                raise RuntimeError("No microphone input device found.")
            mic_path = self._output_dir / "mic.wav"
            ch = 1
            self._mic_writer = _WavWriter(mic_path, ch)

            def mic_cb(indata, _frames, _time, _status) -> None:
                data = np.array(indata, copy=True)
                if self._mic_muted:
                    data.fill(0.0)
                self._mic_writer.write(data)

            stream = sd.InputStream(
                device=self._mic_device.index,
                channels=ch,
                samplerate=SAMPLE_RATE,
                dtype="float32",
                callback=mic_cb,
            )
            self._streams.append(stream)

        if want_system:
            self._system_device = find_system_audio_device()
            if self._system_device is None:
                raise RuntimeError(
                    "No system audio loopback device found. "
                    "Install BlackHole 2ch and set it as an audio output."
                )
            sys_path = self._output_dir / "system.wav"
            ch = min(2, self._system_device.channels)
            self._system_writer = _WavWriter(sys_path, ch)

            def sys_cb(indata, _frames, _time, _status) -> None:
                data = np.array(indata, copy=True)
                if self._system_muted:
                    data.fill(0.0)
                if ch == 1 and data.shape[1] > 1:
                    data = data.mean(axis=1, keepdims=True)
                self._system_writer.write(data)

            stream = sd.InputStream(
                device=self._system_device.index,
                channels=ch,
                samplerate=SAMPLE_RATE,
                dtype="float32",
                callback=sys_cb,
            )
            self._streams.append(stream)

        for stream in self._streams:
            stream.start()

    def stop(self) -> AudioCaptureResult:
        for stream in self._streams:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        self._streams.clear()

        if self._mic_writer is not None:
            self._mic_writer.close()
        if self._system_writer is not None:
            self._system_writer.close()

        mic_path = self._output_dir / "mic.wav"
        system_path = self._output_dir / "system.wav"

        return AudioCaptureResult(
            mic_path=mic_path if self._config.record_mic and mic_path.is_file() else None,
            system_path=(
                system_path if self._config.record_system and system_path.is_file() else None
            ),
            sample_rate=SAMPLE_RATE,
        )
