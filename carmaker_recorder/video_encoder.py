from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np

from .config import VideoConfig

LOG = logging.getLogger(__name__)


class VideoEncoder(Protocol):
    backend_name: str

    def write(self, frame: np.ndarray) -> None: ...

    def release(self) -> None: ...


class OpenCvVideoEncoder:
    def __init__(self, path: Path, config: VideoConfig, width: int, height: int):
        fourcc = cv2.VideoWriter_fourcc(*config.fourcc)
        self._writer = cv2.VideoWriter(
            str(path),
            fourcc,
            float(config.fps),
            (width, height),
            True,
        )
        if not self._writer.isOpened():
            self._writer.release()
            raise RuntimeError(f"OpenCV VideoWriter open failed: {path}")
        try:
            api = self._writer.getBackendName()
        except cv2.error:
            api = "unknown"
        self.backend_name = f"opencv:{api}:{config.fourcc}"

    def write(self, frame: np.ndarray) -> None:
        self._writer.write(frame)

    def release(self) -> None:
        self._writer.release()


def _creation_flags() -> int:
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if os.name == "nt" else 0


def _resolve_ffmpeg(executable: str) -> str | None:
    candidate = str(executable).strip()
    if not candidate:
        return None
    resolved = shutil.which(candidate)
    if resolved:
        return resolved
    path = Path(candidate).expanduser()
    if path.is_file():
        return str(path.resolve())
    return None


def _hardware_encoder_name(backend: str, codec: str) -> str:
    return f"{codec}_{backend}"


@lru_cache(maxsize=32)
def _probe_ffmpeg_encoder(executable: str, encoder: str) -> tuple[bool, str]:
    command = [
        executable,
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=256x256:r=1",
        "-frames:v",
        "1",
        "-an",
        "-c:v",
        encoder,
        "-f",
        "null",
        "-",
    ]
    try:
        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=15,
            check=False,
            creationflags=_creation_flags(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    detail = result.stderr.decode("utf-8", errors="replace").strip()
    return result.returncode == 0, detail


def available_hardware_backend(config: VideoConfig) -> tuple[str, str, str] | None:
    executable = _resolve_ffmpeg(config.ffmpeg_path)
    if executable is None:
        return None
    candidates = (
        ("nvenc", "qsv", "amf") if config.backend == "auto" else (config.backend,)
    )
    for backend in candidates:
        encoder = _hardware_encoder_name(backend, config.codec)
        available, detail = _probe_ffmpeg_encoder(executable, encoder)
        if available:
            return executable, backend, encoder
        LOG.debug(
            "FFmpeg encoder probe failed for %s: %s", encoder, detail or "unavailable"
        )
    return None


class FfmpegHardwareEncoder:
    def __init__(
        self,
        path: Path,
        config: VideoConfig,
        width: int,
        height: int,
        executable: str,
        backend: str,
        encoder: str,
    ):
        self.backend_name = f"ffmpeg:{encoder}"
        self._stderr = tempfile.TemporaryFile(mode="w+b")
        command = [
            executable,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-f",
            "rawvideo",
            "-pixel_format",
            "bgr24",
            "-video_size",
            f"{width}x{height}",
            "-framerate",
            f"{config.fps:g}",
            "-i",
            "pipe:0",
            "-an",
            "-c:v",
            encoder,
            "-b:v",
            f"{config.bitrate_mbps:g}M",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ]
        try:
            self._process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=self._stderr,
                creationflags=_creation_flags(),
            )
        except Exception:
            self._stderr.close()
            raise
        self._backend = backend

    def _error_detail(self) -> str:
        try:
            self._stderr.flush()
            self._stderr.seek(0)
            return self._stderr.read().decode("utf-8", errors="replace").strip()
        except (OSError, ValueError):
            return ""

    def write(self, frame: np.ndarray) -> None:
        if self._process.poll() is not None:
            detail = self._error_detail()
            raise RuntimeError(
                f"FFmpeg {self._backend} encoder exited with code {self._process.returncode}: {detail}"
            )
        if frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError("FFmpeg hardware encoder requires an 8-bit BGR frame")
        if not frame.flags.c_contiguous:
            frame = np.ascontiguousarray(frame)
        if self._process.stdin is None:
            raise RuntimeError("FFmpeg encoder input is closed")
        try:
            self._process.stdin.write(memoryview(frame).cast("B"))
        except (BrokenPipeError, OSError) as exc:
            detail = self._error_detail()
            raise RuntimeError(
                f"FFmpeg {self._backend} encoder write failed: {detail}"
            ) from exc

    def release(self) -> None:
        process = self._process
        if process.stdin is not None and not process.stdin.closed:
            try:
                process.stdin.close()
            except OSError:
                pass
        try:
            return_code = process.wait(timeout=30)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            process.wait(timeout=5)
            detail = self._error_detail()
            self._stderr.close()
            raise RuntimeError(
                f"FFmpeg {self._backend} encoder did not stop: {detail}"
            ) from exc
        detail = self._error_detail()
        self._stderr.close()
        if return_code != 0:
            raise RuntimeError(
                f"FFmpeg {self._backend} encoder exited with code {return_code}: {detail}"
            )


def create_video_encoder(
    path: Path,
    config: VideoConfig,
    width: int,
    height: int,
) -> tuple[VideoEncoder, str | None]:
    if config.backend == "opencv":
        return OpenCvVideoEncoder(path, config, width, height), None

    selected = available_hardware_backend(config)
    if selected is not None:
        executable, backend, encoder = selected
        instance = FfmpegHardwareEncoder(
            path,
            config,
            width,
            height,
            executable,
            backend,
            encoder,
        )
        return instance, None

    message = f"hardware video backend {config.backend!r} with codec {config.codec!r} is unavailable"
    if not config.allow_cpu_fallback:
        raise RuntimeError(message)
    return OpenCvVideoEncoder(path, config, width, height), message
