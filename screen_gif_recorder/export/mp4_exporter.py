"""MP4 export via imageio/ffmpeg — tuned for small files at full resolution."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional

from PIL import Image

from screen_gif_recorder.capture.audio_recorder import AudioCaptureResult
from screen_gif_recorder.export.compression import quality_to_crf


def ffmpeg_path() -> str | None:
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return None


def ffmpeg_available() -> bool:
    return ffmpeg_path() is not None


def ffmpeg_install_hint() -> str:
    return (
        "MP4 export needs ffmpeg.\n\n"
        "  pip install imageio imageio-ffmpeg\n"
        "or:\n"
        "  brew install ffmpeg"
    )


def _even_size(w: int, h: int) -> tuple[int, int]:
    return w - (w % 2), h - (h % 2)


def _ffmpeg_encode_params(quality: int) -> list[str]:
    crf = quality_to_crf(quality)
    return [
        "-movflags",
        "+faststart",
        "-crf",
        str(crf),
        "-preset",
        "medium",
        "-tune",
        "animation",
        "-profile:v",
        "high",
    ]


def _audio_file_usable(path: Path | None) -> bool:
    return path is not None and path.is_file() and path.stat().st_size > 44


def mux_audio_into_mp4(
    video_path: Path,
    output_path: Path,
    audio: AudioCaptureResult,
) -> Path:
    """Combine a video-only MP4 with one or two WAV tracks."""
    ffmpeg = ffmpeg_path()
    if ffmpeg is None:
        raise RuntimeError(ffmpeg_install_hint())

    inputs = ["-i", str(video_path)]
    filters: list[str] = []
    mix_labels: list[str] = []
    stream_idx = 1

    if _audio_file_usable(audio.mic_path):
        inputs.extend(["-i", str(audio.mic_path)])
        filters.append(
            f"[{stream_idx}:a]aformat=sample_rates=48000:channel_layouts=mono[amic]"
        )
        mix_labels.append("[amic]")
        stream_idx += 1

    if _audio_file_usable(audio.system_path):
        inputs.extend(["-i", str(audio.system_path)])
        filters.append(
            f"[{stream_idx}:a]aformat=sample_rates=48000:channel_layouts=stereo[asys]"
        )
        mix_labels.append("[asys]")
        stream_idx += 1

    if not mix_labels:
        shutil.copy2(video_path, output_path)
        return output_path

    if len(mix_labels) == 1:
        audio_out = mix_labels[0]
        filter_complex = filters[0]
    else:
        filter_complex = (
            f"{filters[0]};{filters[1]};"
            f"{''.join(mix_labels)}amix=inputs=2:duration=shortest:dropout_transition=0[aout]"
        )
        audio_out = "[aout]"

    cmd = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        *inputs,
        "-filter_complex",
        filter_complex,
        "-map",
        "0:v",
        "-map",
        audio_out,
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or "ffmpeg audio mux failed")
    return output_path


def export_mp4(
    frames: list[Image.Image],
    output_path: Path,
    *,
    fps: float = 12.0,
    quality: int = 70,
    audio: AudioCaptureResult | None = None,
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> Path:
    if not frames:
        raise ValueError("No frames to export")
    if not ffmpeg_available():
        raise RuntimeError(ffmpeg_install_hint())

    fps = max(fps, 1.0)
    total = len(frames)
    use_audio = audio is not None and audio.has_audio()

    if on_progress:
        on_progress(0, total)

    if use_audio:
        with tempfile.TemporaryDirectory(prefix="pixly_mux_") as tmp:
            video_only = Path(tmp) / "video_only.mp4"
            try:
                _export_via_imageio(
                    frames,
                    video_only,
                    fps=fps,
                    quality=quality,
                    on_progress=on_progress,
                )
            except Exception:
                _export_via_jpeg_sequence(
                    frames,
                    video_only,
                    fps=fps,
                    quality=quality,
                    on_progress=on_progress,
                )
            assert audio is not None
            return mux_audio_into_mp4(video_only, output_path, audio)

    try:
        return _export_via_imageio(
            frames, output_path, fps=fps, quality=quality, on_progress=on_progress
        )
    except Exception:
        return _export_via_jpeg_sequence(
            frames, output_path, fps=fps, quality=quality, on_progress=on_progress
        )


def _export_via_imageio(
    frames: list[Image.Image],
    output_path: Path,
    *,
    fps: float,
    quality: int,
    on_progress: Optional[Callable[[int, int], None]],
) -> Path:
    import imageio
    import numpy as np

    first = frames[0].convert("RGB")
    width, height = _even_size(first.width, first.height)

    writer = imageio.get_writer(
        str(output_path),
        fps=fps,
        codec="libx264",
        pixelformat="yuv420p",
        macro_block_size=1,
        ffmpeg_params=_ffmpeg_encode_params(quality),
    )

    try:
        for i, frame in enumerate(frames):
            rgb = frame.convert("RGB")
            if rgb.size != (width, height):
                rgb = rgb.resize((width, height), Image.Resampling.LANCZOS)
            writer.append_data(np.asarray(rgb, dtype=np.uint8))
            if on_progress:
                on_progress(i + 1, len(frames))
    finally:
        writer.close()

    return output_path


def _export_via_jpeg_sequence(
    frames: list[Image.Image],
    output_path: Path,
    *,
    fps: float,
    quality: int,
    on_progress: Optional[Callable[[int, int], None]],
) -> Path:
    ffmpeg = ffmpeg_path()
    assert ffmpeg is not None

    first = frames[0].convert("RGB")
    width, height = _even_size(first.width, first.height)
    total = len(frames)
    crf = quality_to_crf(quality)
    # High JPEG quality for intermediates — final size set by x264 CRF
    jpeg_q = 90

    with tempfile.TemporaryDirectory(prefix="pixly_mp4_") as tmp:
        tmp_path = Path(tmp)
        for i, frame in enumerate(frames):
            rgb = frame.convert("RGB")
            if rgb.size != (width, height):
                rgb = rgb.resize((width, height), Image.Resampling.LANCZOS)
            rgb.save(tmp_path / f"frame_{i:06d}.jpg", "JPEG", quality=jpeg_q, optimize=True)
            if on_progress:
                on_progress(i + 1, total)

        cmd = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-framerate",
            str(fps),
            "-i",
            str(tmp_path / "frame_%06d.jpg"),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            *_ffmpeg_encode_params(quality),
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr or "ffmpeg failed")

    return output_path
