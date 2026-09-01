from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np

from .config import AppConfig
from .image_codec import (
    build_image_header,
    choose_export_format,
    decode_payload_to_bgr,
    prepare_export_payload,
)
from .models import CamFrame, ImageTask
from .ring_buffer import RingBuffer
from .video_encoder import VideoEncoder, create_video_encoder

LOG = logging.getLogger(__name__)
ErrorCallback = Callable[[str, str, Exception], None]


class ImageSaver(threading.Thread):
    def __init__(
        self,
        images_root: Path,
        cam_id: str,
        system_time_str: str,
        config: AppConfig,
        monitor=None,
        error_callback: ErrorCallback | None = None,
    ):
        super().__init__(daemon=True, name=f"ImageSaver-{cam_id}")
        self.cam_id = str(cam_id)
        self.system_time_str = system_time_str
        self.config = config
        self.monitor = monitor
        self.error_callback = error_callback
        self.camera_view = config.camera_name(cam_id)
        self.dir_path = images_root / f"CAM_{self.camera_view}"
        self.dir_path.mkdir(parents=True, exist_ok=True)
        self.rb: RingBuffer[ImageTask] = RingBuffer(config.buffers.image_task_capacity)
        self.stop_evt = threading.Event()
        self.written = 0
        self.healthy = True
        self.last_error: str | None = None

    def push(self, task: ImageTask) -> bool:
        if not self.healthy or (self.ident is not None and not self.is_alive()):
            return False
        overwritten = self.rb.push_overwrite(task)
        if overwritten:
            if self.monitor is not None:
                self.monitor.mark_queue_drop(self.cam_id, "image")
            drops = self.rb.stats().dropped
            if drops == 1 or drops % 100 == 0:
                LOG.warning("Image queue overwrite CAM %s: dropped=%s", self.cam_id, drops)
        return True

    def stop_and_drain(self) -> None:
        self.stop_evt.set()

    def _fail(self, exc: Exception) -> None:
        self.healthy = False
        self.last_error = str(exc)
        if self.monitor is not None:
            self.monitor.set_writer_state(self.cam_id, "image", "ERROR", self.last_error)
        if self.error_callback is not None:
            self.error_callback("image", self.cam_id, exc)

    def run(self) -> None:
        if self.monitor is not None:
            self.monitor.set_writer_state(self.cam_id, "image", "RUNNING")
        try:
            while True:
                task = self.rb.pop(timeout=0.5)
                if task is None:
                    if self.stop_evt.is_set() and self.rb.size() == 0:
                        break
                    continue

                export_fmt = choose_export_format(
                    self.config.images.export_format,
                    task.fmt,
                    len(task.payload),
                    task.width,
                    task.height,
                )
                ext, header = build_image_header(export_fmt, task.width, task.height)
                sim_ts = f"{task.sim_time:.6f}"
                seq = self.written + 1
                path = self.dir_path / f"{self.camera_view}-{self.system_time_str}-{sim_ts}-{seq:08d}.{ext}"
                tmp = path.with_name(path.name + ".tmp")

                if export_fmt == "jpg":
                    bgr = decode_payload_to_bgr(
                        task.payload,
                        task.fmt,
                        task.width,
                        task.height
                    )
                    if bgr is None:
                        raise ValueError(
                            f"Camera {task.cam_id} payload cannot be decoded as {task.fmt} "
                            f"({task.width}x{task.height}, {len(task.payload)} bytes)"
                        )
                    ok, encoded = cv2.imencode(
                        ".jpg",
                        bgr,
                        [int(cv2.IMWRITE_JPEG_QUALITY), int(self.config.images.jpeg_quality)],
                    )
                    if not ok:
                        raise RuntimeError(f"JPEG encode failed for camera {task.cam_id}")
                    with tmp.open("wb") as f:
                        f.write(memoryview(encoded).cast("B"))
                else:
                    output_payload = prepare_export_payload(
                        task.payload,
                        task.fmt,
                        export_fmt,
                        task.width,
                        task.height,
                    )
                    if output_payload is None:
                        raise ValueError(
                            f"Cannot export source format {task.fmt!r} as {export_fmt!r} "
                            f"for camera {task.cam_id}"
                        )
                    with tmp.open("wb") as f:
                        if header:
                            f.write(header)
                        f.write(output_payload)

                os.replace(tmp, path)
                self.written += 1
                if self.monitor is not None:
                    self.monitor.mark_image_written(self.cam_id)
        except Exception as exc:
            LOG.exception("ImageSaver %s failed", self.cam_id)
            self._fail(exc)
        finally:
            if self.monitor is not None and self.healthy:
                self.monitor.set_writer_state(self.cam_id, "image", "STOPPED")
            LOG.info("[ImageId:%s] wrote %s images", self.cam_id, self.written)


class CameraWriter(threading.Thread):
    def __init__(
        self,
        videos_dir: Path,
        cam_id: str,
        system_time_str: str,
        config: AppConfig,
        monitor=None,
        error_callback: ErrorCallback | None = None,
    ):
        super().__init__(daemon=True, name=f"VideoWriter-{cam_id}")
        self.videos_dir = videos_dir
        self.cam_id = str(cam_id)
        self.system_time_str = system_time_str
        self.config = config
        self.monitor = monitor
        self.error_callback = error_callback
        self.rb: RingBuffer[CamFrame] = RingBuffer(config.buffers.frame_capacity)
        self.stop_evt = threading.Event()
        self.writer: Optional[VideoEncoder] = None
        self.file_path: Optional[Path] = None
        self.current_size: tuple[int, int] | None = None
        self.segment_index = 0
        self.t0: Optional[float] = None
        self.last_sim_time: Optional[float] = None
        self.last_target_idx = -1
        self.last_frame_bgr: Optional[np.ndarray] = None
        self.frames_written = 0
        self.healthy = True
        self.last_error: str | None = None

    def push(self, frame: CamFrame) -> bool:
        if not self.healthy or (self.ident is not None and not self.is_alive()):
            return False
        overwritten = self.rb.push_overwrite(frame)
        if overwritten:
            if self.monitor is not None:
                self.monitor.mark_queue_drop(self.cam_id, "video")
            drops = self.rb.stats().dropped
            if drops == 1 or drops % 100 == 0:
                LOG.warning("Video queue overwrite CAM %s: dropped=%s", self.cam_id, drops)
        return True

    def stop_and_drain(self) -> None:
        self.stop_evt.set()

    def _release_writer(self) -> None:
        if self.writer is not None:
            try:
                self.writer.release()
            finally:
                self.writer = None

    def _open_segment(self, w: int, h: int, sim_time: float, reason: str) -> None:
        self._release_writer()
        self.segment_index += 1
        camera_view = self.config.camera_name(self.cam_id)
        ext = self.config.video.extension.lstrip(".")
        self.file_path = self.videos_dir / (
            f"{self.cam_id}_{camera_view}_{self.system_time_str}_part{self.segment_index:03d}.{ext}"
        )
        writer, fallback_reason = create_video_encoder(
            self.file_path,
            self.config.video,
            w,
            h,
        )
        self.writer = writer
        self.current_size = (w, h)
        self.t0 = sim_time
        self.last_sim_time = None
        self.last_target_idx = -1
        self.last_frame_bgr = None
        if self.monitor is not None:
            self.monitor.set_video_backend(self.cam_id, writer.backend_name)
            if fallback_reason and self.config.video.backend != "auto":
                self.monitor.add_warning(f"video_writer:{self.cam_id}", fallback_reason)
        if fallback_reason:
            log = LOG.info if self.config.video.backend == "auto" else LOG.warning
            log("Camera %s: %s; using %s", self.cam_id, fallback_reason, writer.backend_name)
        LOG.info(
            "Camera %s opened video segment %s (%s, backend=%s)",
            self.cam_id,
            self.file_path,
            reason,
            writer.backend_name,
        )

    def _fail(self, exc: Exception) -> None:
        self.healthy = False
        self.last_error = str(exc)
        if self.monitor is not None:
            self.monitor.set_writer_state(self.cam_id, "video", "ERROR", self.last_error)
        if self.error_callback is not None:
            self.error_callback("video", self.cam_id, exc)

    def run(self) -> None:
        if self.monitor is not None:
            self.monitor.set_writer_state(self.cam_id, "video", "RUNNING")
        try:
            while True:
                frame = self.rb.pop(timeout=0.5)
                if frame is None:
                    if self.stop_evt.is_set() and self.rb.size() == 0:
                        break
                    continue

                if self.writer is None:
                    self._open_segment(frame.width, frame.height, frame.sim_time, "initial")
                elif self.current_size != (frame.width, frame.height):
                    LOG.warning(
                        "Camera %s resolution changed %s -> %s; starting new segment",
                        self.cam_id,
                        self.current_size,
                        (frame.width, frame.height),
                    )
                    self._open_segment(frame.width, frame.height, frame.sim_time, "resolution-change")
                elif self.last_sim_time is not None and frame.sim_time < self.last_sim_time - 1e-6:
                    LOG.warning("Camera %s sim_time rolled back; starting new segment", self.cam_id)
                    self._open_segment(frame.width, frame.height, frame.sim_time, "sim-time-reset")

                if self.t0 is None or self.writer is None:
                    raise RuntimeError("video segment state is incomplete after opening the writer")
                rel = max(0.0, frame.sim_time - self.t0)
                target_idx = int(round(rel * self.config.video.fps))
                if (
                    self.last_frame_bgr is not None
                    and target_idx > self.last_target_idx + 1
                    and (target_idx - self.last_target_idx - 1) > self.config.video.max_gap_fill_frames
                ):
                    LOG.warning(
                        "Camera %s video gap=%s exceeds max_gap_fill_frames=%s; starting new segment",
                        self.cam_id,
                        target_idx - self.last_target_idx - 1,
                        self.config.video.max_gap_fill_frames,
                    )
                    self._open_segment(frame.width, frame.height, frame.sim_time, "large-time-gap")
                    target_idx = 0

                bgr = decode_payload_to_bgr(
                    frame.payload,
                    frame.fmt,
                    frame.width,
                    frame.height
                )
                if bgr is None:
                    raise ValueError(
                        f"Camera {frame.cam_id} payload cannot be decoded as {frame.fmt} "
                        f"({frame.width}x{frame.height}, {len(frame.payload)} bytes)"
                    )

                if self.last_frame_bgr is not None and target_idx > self.last_target_idx + 1:
                    gap = target_idx - (self.last_target_idx + 1)
                    for _ in range(gap):
                        self.writer.write(self.last_frame_bgr)
                        self.frames_written += 1
                        self.last_target_idx += 1
                        if self.monitor is not None:
                            self.monitor.mark_video_frame_written(self.cam_id)

                if target_idx > self.last_target_idx:
                    self.writer.write(bgr)
                    self.frames_written += 1
                    self.last_target_idx = target_idx
                    self.last_frame_bgr = bgr
                    if self.monitor is not None:
                        self.monitor.mark_video_frame_written(self.cam_id)
                self.last_sim_time = frame.sim_time
        except Exception as exc:
            LOG.exception("Video writer %s failed", self.cam_id)
            self._fail(exc)
        finally:
            try:
                self._release_writer()
            except Exception as exc:
                LOG.exception("Video writer %s failed while closing", self.cam_id)
                if self.healthy:
                    self._fail(exc)
            if self.monitor is not None and self.healthy:
                self.monitor.set_writer_state(self.cam_id, "video", "STOPPED")
            LOG.info(
                "[VideoId:%s] wrote %s frames in %s segment(s)",
                self.cam_id,
                self.frames_written,
                self.segment_index,
            )
