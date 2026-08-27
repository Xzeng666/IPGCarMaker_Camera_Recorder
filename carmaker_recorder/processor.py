from __future__ import annotations

import logging
import shutil
import threading
import time
from pathlib import Path
from typing import Dict, Optional

from .config import AppConfig
from .models import CamFrame, ImageTask, Message
from .ring_buffer import RingBuffer
from .rsds_protocol import header_to_words
from .sampling import PeriodicSimTimeSampler
from .session import SessionManager, SessionPaths
from .writers import CameraWriter, ImageSaver

LOG = logging.getLogger(__name__)


class SequentialProcessor(threading.Thread):
    """Order-preserving CameraRSI dispatcher and session finalizer.

    One GUI/CLI Start→Stop cycle is one logical capture run. A large simulation
    time rollback is treated as a fatal boundary instead of silently mixing two
    CarMaker runs into the same dataset.
    """

    def __init__(
        self,
        save_root: Path,
        msg_ring: RingBuffer[Message],
        global_exit_evt: threading.Event,
        config: AppConfig,
        runtime_start_epoch: float,
        monitor=None,
        runtime_log_path: str | None = None,
    ):
        super().__init__(daemon=True, name="SequentialProcessor")
        self.save_root = Path(save_root)
        self.msg_ring = msg_ring
        self.global_exit_evt = global_exit_evt
        self.config = config
        self.runtime_start_epoch = float(runtime_start_epoch)
        self.monitor = monitor
        self.runtime_log_path = runtime_log_path

        self.session_mgr = SessionManager(self.save_root, 1, runtime_start_epoch=self.runtime_start_epoch)
        self._session_paths: Optional[SessionPaths] = None
        self.video_writers: Dict[str, CameraWriter] = {}
        self.image_savers: Dict[str, ImageSaver] = {}
        self.image_samplers: Dict[str, PeriodicSimTimeSampler] = {}
        self.last_sim_time_by_stream: Dict[tuple[int, str], float] = {}
        self._disk_last_check = 0.0
        self._fatal_error: str | None = None

    def _ensure_session(self, frame: CamFrame) -> SessionPaths:
        self.session_mgr.observe_frame(frame.sim_time, frame.received_epoch)
        if self._session_paths is None:
            self._session_paths = self.session_mgr.ensure_created()
            if self.monitor is not None:
                self.monitor.begin_session(self._session_paths.root, self._session_paths.scene_id_str)
            self._check_disk_space(force=True)
        return self._session_paths

    def _writer_error(self, kind: str, cam_id: str, exc: Exception) -> None:
        message = f"CAM {cam_id} {kind} writer failed: {exc}"
        fatal = self.config.reliability.writer_failure_policy == "stop"
        if self.monitor is not None:
            self.monitor.add_error(f"{kind}_writer:{cam_id}", message, fatal=fatal)
        if fatal:
            self._fatal_error = message
            self.global_exit_evt.set()
        else:
            LOG.error("%s; recorder continues in degraded mode", message)

    def _get_video_writer(self, cam_id: str) -> CameraWriter:
        if self._session_paths is None:
            raise RuntimeError("video writer requested before session creation")
        if cam_id not in self.video_writers:
            writer = CameraWriter(
                self._session_paths.videos_dir,
                cam_id,
                self._session_paths.system_time_str,
                self.config,
                monitor=self.monitor,
                error_callback=self._writer_error,
            )
            self.video_writers[cam_id] = writer
            writer.start()
        return self.video_writers[cam_id]

    def _get_image_saver(self, cam_id: str) -> ImageSaver:
        if self._session_paths is None:
            raise RuntimeError("image saver requested before session creation")
        if cam_id not in self.image_savers:
            saver = ImageSaver(
                self._session_paths.images_dir,
                cam_id,
                self._session_paths.system_time_str,
                self.config,
                monitor=self.monitor,
                error_callback=self._writer_error,
            )
            self.image_savers[cam_id] = saver
            saver.start()
        return self.image_savers[cam_id]

    def _should_save_image(self, cam_id: str, sim_time: float) -> bool:
        sampler = self.image_samplers.get(cam_id)
        if sampler is None:
            sampler = PeriodicSimTimeSampler(self.config.images.sample_hz)
            self.image_samplers[cam_id] = sampler
        return sampler.should_sample(sim_time)

    def _check_sim_time(self, frame: CamFrame) -> bool:
        """Detect a simulation restart per RSDS stream, not across cameras.

        Frames from different ports/cameras can arrive with different transport
        latency. Comparing every frame against one global maximum can therefore
        misclassify a healthy but slower camera as a simulation rollback.
        """
        stream = (int(frame.source_port), str(frame.cam_id))
        current = float(frame.sim_time)
        previous = self.last_sim_time_by_stream.get(stream)
        threshold = self.config.reliability.sim_time_reset_threshold_sec
        if previous is not None and current < previous - threshold:
            message = (
                f"simulation time rollback detected on port {frame.source_port} CAM {frame.cam_id}: "
                f"{current:.6f}s after {previous:.6f}s; start a new recorder run for the new simulation"
            )
            self._fatal_error = message
            if self.monitor is not None:
                self.monitor.add_error("sim_time", message, fatal=True)
            LOG.error(message)
            self.global_exit_evt.set()
            return False
        self.last_sim_time_by_stream[stream] = max(previous if previous is not None else current, current)
        return True

    def _check_disk_space(self, *, force: bool = False) -> bool:
        now = time.monotonic()
        if not force and now - self._disk_last_check < self.config.reliability.disk_check_interval_sec:
            return True
        self._disk_last_check = now
        target = self._session_paths.root if self._session_paths is not None else self.save_root
        try:
            free_gb = shutil.disk_usage(target).free / (1024 ** 3)
        except OSError as exc:
            message = f"disk usage check failed for {target}: {exc}"
            self._fatal_error = message
            if self.monitor is not None:
                self.monitor.add_error("disk", message, fatal=True)
            self.global_exit_evt.set()
            return False
        if self.monitor is not None:
            self.monitor.set_disk_free_gb(free_gb)
        if free_gb < self.config.reliability.min_free_disk_gb:
            message = (
                f"free disk space {free_gb:.2f} GiB is below configured minimum "
                f"{self.config.reliability.min_free_disk_gb:.2f} GiB"
            )
            self._fatal_error = message
            if self.monitor is not None:
                self.monitor.add_error("disk", message, fatal=True)
            LOG.error(message)
            self.global_exit_evt.set()
            return False
        return True

    def _parse_camera_message(self, msg: Message) -> CamFrame | None:
        msg_type, parts = header_to_words(msg.header)
        if msg_type != "CameraRSI":
            return None
        try:
            camera_id_num = int(parts[1])
            if camera_id_num < 0:
                raise ValueError("negative camera ID")
            cam_id = str(camera_id_num)
            fmt = parts[2].strip().lower()
            sim_time = float(parts[3])
            w_str, h_str = parts[4].split("x")
            width, height = int(w_str), int(h_str)
            if width <= 0 or height <= 0:
                raise ValueError("invalid dimensions")
            payload_len = int(parts[5])
        except (IndexError, TypeError, ValueError):
            LOG.warning("Malformed CameraRSI header: %r", msg.header)
            return None
        if msg.data is None or len(msg.data) != payload_len:
            LOG.warning("CameraRSI payload mismatch for CAM %s", cam_id)
            return None
        return CamFrame(
            cam_id=cam_id,
            fmt=fmt,
            sim_time=sim_time,
            width=width,
            height=height,
            payload=msg.data,
            received_epoch=msg.received_epoch,
            source_port=msg.port,
        )

    def _stop_writers(self) -> None:
        for writer in self.video_writers.values():
            writer.stop_and_drain()
        for saver in self.image_savers.values():
            saver.stop_and_drain()
        for writer in self.video_writers.values():
            writer.join()
            if self.monitor is not None:
                self.monitor.set_queue_stats(writer.cam_id, "video", writer.rb.stats())
        for saver in self.image_savers.values():
            saver.join()
            if self.monitor is not None:
                self.monitor.set_queue_stats(saver.cam_id, "image", saver.rb.stats())

    def _finalize_session(self) -> None:
        if self._session_paths is None:
            return
        self._stop_writers()

        if self.monitor is not None:
            self.monitor.set_message_buffer_stats(self.msg_ring.stats())
            snapshot = self.monitor.snapshot()
        else:
            snapshot = {}
        self.session_mgr.write_manifest(
            self.config,
            snapshot,
            end_epoch=time.time(),
            runtime_log=self.runtime_log_path,
        )

    def run(self) -> None:
        try:
            while True:
                msg = self.msg_ring.pop(timeout=0.25)
                if self.monitor is not None:
                    self.monitor.set_message_buffer_stats(self.msg_ring.stats())
                if msg is None:
                    if self.global_exit_evt.is_set() and self.msg_ring.size() == 0:
                        break
                    self._check_disk_space()
                    continue

                frame = self._parse_camera_message(msg)
                if frame is None:
                    continue
                if not self._check_sim_time(frame):
                    break
                self._ensure_session(frame)
                if not self._check_disk_space():
                    break

                if self.monitor is not None:
                    self.monitor.mark_frame(frame)

                if self.config.video.enabled:
                    writer = self._get_video_writer(frame.cam_id)
                    if not writer.push(frame) and writer.healthy:
                        LOG.warning("Video frame was not accepted for CAM %s", frame.cam_id)

                if self.config.images.enabled and self._should_save_image(frame.cam_id, frame.sim_time):
                    saver = self._get_image_saver(frame.cam_id)
                    saver.push(
                        ImageTask(
                            frame.cam_id,
                            frame.fmt,
                            frame.sim_time,
                            frame.width,
                            frame.height,
                            frame.payload,
                            msg.domain,
                            msg.port,
                        )
                    )
        except Exception as exc:
            self._fatal_error = str(exc)
            if self.monitor is not None:
                self.monitor.add_error("processor", str(exc), fatal=True)
            self.global_exit_evt.set()
            LOG.exception("Sequential processor failed")
        finally:
            try:
                self._finalize_session()
            except Exception as exc:
                if self.monitor is not None:
                    self.monitor.add_error("finalize", str(exc), fatal=True)
                LOG.exception("Session finalization failed")
