from __future__ import annotations

import logging
import queue
import threading
import time
from copy import deepcopy
from typing import Any, Dict, Optional

import cv2

from .config import AppConfig
from .image_codec import decode_payload_to_bgr
from .models import CamFrame

LOG = logging.getLogger(__name__)


class _PreviewEncoder(threading.Thread):
    def __init__(self, monitor: "RecorderMonitor"):
        super().__init__(daemon=True, name="PreviewEncoder")
        self.monitor = monitor
        self.queue: queue.Queue[CamFrame | None] = queue.Queue(maxsize=8)
        self.stop_evt = threading.Event()

    def submit(self, frame: CamFrame) -> None:
        if self.stop_evt.is_set():
            return
        try:
            self.queue.put_nowait(frame)
        except queue.Full:
            try:
                self.queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self.queue.put_nowait(frame)
            except queue.Full:
                pass

    def request_stop(self) -> None:
        self.stop_evt.set()
        try:
            self.queue.put_nowait(None)
        except queue.Full:
            pass

    def run(self) -> None:
        while not self.stop_evt.is_set():
            try:
                frame = self.queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if frame is None:
                continue
            try:
                bgr = decode_payload_to_bgr(
                    frame.payload,
                    frame.fmt,
                    frame.width,
                    frame.height
                )
                if bgr is None:
                    continue
                max_w, max_h = 480, 270
                scale = min(max_w / max(1, frame.width), max_h / max(1, frame.height), 1.0)
                if scale < 1.0:
                    bgr = cv2.resize(
                        bgr,
                        (max(1, int(frame.width * scale)), max(1, int(frame.height * scale))),
                        interpolation=cv2.INTER_AREA,
                    )
                ok, encoded = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 72])
                if ok:
                    self.monitor._store_preview(frame.cam_id, encoded.tobytes())
            except Exception:
                LOG.debug("Preview generation failed for camera %s", frame.cam_id, exc_info=True)


class RecorderMonitor:
    """Thread-safe runtime telemetry for GUI, manifest and automated checks."""

    def __init__(self, config: AppConfig, capture_previews: bool = False, preview_hz: float = 2.0):
        self.config = config
        self.capture_previews = bool(capture_previews)
        self.preview_hz = max(0.2, float(preview_hz))
        self._lock = threading.Lock()
        self._preview_worker: Optional[_PreviewEncoder] = None
        self._started_epoch: Optional[float] = None
        self._state = "STOPPED"
        self._connections: Dict[int, str] = {int(p): "IDLE" for p in config.network.ports}
        self._cameras: Dict[str, Dict[str, Any]] = {}
        self._session_root: Optional[str] = None
        self._scene_id: Optional[str] = None
        self._last_preview_epoch: Dict[str, float] = {}
        self._network_drops = 0
        self._message_buffer: Dict[str, Any] = {}
        self._disk_free_gb: Optional[float] = None
        self._errors: list[dict[str, Any]] = []
        self._warnings: list[dict[str, Any]] = []

    def reset(self) -> None:
        self.stop_preview_worker()
        with self._lock:
            self._started_epoch = time.time()
            self._state = "STARTING"
            self._connections = {int(p): "IDLE" for p in self.config.network.ports}
            self._cameras = {}
            self._session_root = None
            self._scene_id = None
            self._last_preview_epoch = {}
            self._network_drops = 0
            self._message_buffer = {}
            self._disk_free_gb = None
            self._errors = []
            self._warnings = []
        if self.capture_previews:
            self._preview_worker = _PreviewEncoder(self)
            self._preview_worker.start()

    def stop_preview_worker(self) -> None:
        worker = self._preview_worker
        self._preview_worker = None
        if worker is not None:
            worker.request_stop()
            worker.join(timeout=2.0)

    def set_state(self, state: str) -> None:
        with self._lock:
            self._state = str(state).upper()

    def set_connection(self, port: int, state: str) -> None:
        with self._lock:
            self._connections[int(port)] = str(state).upper()

    def begin_session(self, root, scene_id: str) -> None:
        """Attach the on-disk session without erasing pre-session health events.

        Connection retries, queue pressure, warnings and errors that happened while
        waiting for the first CameraRSI frame are part of the same Start→Stop run
        and therefore remain visible in the final manifest.
        """
        with self._lock:
            self._session_root = str(root)
            self._scene_id = str(scene_id)
            if self._state not in {"STOPPING", "STOPPED", "ERROR", "DEGRADED"}:
                self._state = "RECORDING"

    def clear_session(self) -> None:
        with self._lock:
            self._session_root = None
            self._scene_id = None

    def mark_frame(self, frame: CamFrame) -> None:
        now = time.time()
        generate_preview = False
        with self._lock:
            entry = self._cameras.setdefault(
                str(frame.cam_id),
                {
                    "name": self.config.camera_name(frame.cam_id),
                    "frames_received": 0,
                    "video_frames_written": 0,
                    "images_written": 0,
                    "video_queue_drops": 0,
                    "image_queue_drops": 0,
                    "sim_time": 0.0,
                    "width": 0,
                    "height": 0,
                    "format": "-",
                    "source_port": 0,
                    "first_seen_epoch": now,
                    "last_seen_epoch": 0.0,
                    "bytes_received": 0,
                    "preview_jpeg": None,
                    "video_writer": "IDLE",
                    "video_backend": None,
                    "image_writer": "IDLE",
                    "last_error": None,
                },
            )
            entry["frames_received"] += 1
            entry["sim_time"] = float(frame.sim_time)
            entry["width"] = int(frame.width)
            entry["height"] = int(frame.height)
            entry["format"] = str(frame.fmt)
            entry["source_port"] = int(frame.source_port)
            entry["last_seen_epoch"] = now
            entry["bytes_received"] = int(entry.get("bytes_received", 0)) + len(frame.payload)
            last_preview = self._last_preview_epoch.get(str(frame.cam_id), 0.0)
            if self.capture_previews and (now - last_preview) >= (1.0 / self.preview_hz):
                self._last_preview_epoch[str(frame.cam_id)] = now
                generate_preview = True
            if self._state not in {"STOPPING", "STOPPED", "ERROR", "DEGRADED"}:
                self._state = "RECORDING"
        if generate_preview and self._preview_worker is not None:
            self._preview_worker.submit(frame)

    def _store_preview(self, cam_id: str, jpeg: bytes) -> None:
        with self._lock:
            entry = self._cameras.get(str(cam_id))
            if entry is not None:
                entry["preview_jpeg"] = jpeg

    def mark_image_written(self, cam_id: str) -> None:
        with self._lock:
            entry = self._cameras.get(str(cam_id))
            if entry is not None:
                entry["images_written"] += 1

    def mark_video_frame_written(self, cam_id: str, count: int = 1) -> None:
        with self._lock:
            entry = self._cameras.get(str(cam_id))
            if entry is not None:
                entry["video_frames_written"] += int(count)

    def mark_queue_drop(self, cam_id: str, kind: str) -> None:
        key = "video_queue_drops" if kind == "video" else "image_queue_drops"
        with self._lock:
            entry = self._cameras.get(str(cam_id))
            if entry is not None:
                entry[key] += 1
            if self.config.reliability.mark_degraded_on_drop and self._state not in {"ERROR", "STOPPING", "STOPPED"}:
                self._state = "DEGRADED"

    def mark_network_drop(self, port: int) -> None:
        with self._lock:
            self._network_drops += 1
            if self.config.reliability.mark_degraded_on_drop and self._state not in {"ERROR", "STOPPING", "STOPPED"}:
                self._state = "DEGRADED"

    def set_message_buffer_stats(self, stats) -> None:
        with self._lock:
            self._message_buffer = {
                "capacity": stats.capacity,
                "size": stats.size,
                "pushed": stats.pushed,
                "popped": stats.popped,
                "dropped": stats.dropped,
                "high_watermark": stats.high_watermark,
            }

    def set_queue_stats(self, cam_id: str, kind: str, stats) -> None:
        key = "video_queue" if kind == "video" else "image_queue"
        with self._lock:
            entry = self._cameras.get(str(cam_id))
            if entry is not None:
                entry[key] = {
                    "capacity": stats.capacity,
                    "size": stats.size,
                    "pushed": stats.pushed,
                    "popped": stats.popped,
                    "dropped": stats.dropped,
                    "high_watermark": stats.high_watermark,
                }

    def set_writer_state(self, cam_id: str, kind: str, state: str, error: str | None = None) -> None:
        key = "video_writer" if kind == "video" else "image_writer"
        with self._lock:
            entry = self._cameras.setdefault(str(cam_id), {"name": self.config.camera_name(cam_id)})
            entry[key] = state.upper()
            if error:
                entry["last_error"] = error

    def set_video_backend(self, cam_id: str, backend: str) -> None:
        with self._lock:
            entry = self._cameras.setdefault(str(cam_id), {"name": self.config.camera_name(cam_id)})
            entry["video_backend"] = str(backend)

    def add_error(self, component: str, message: str, *, fatal: bool = False) -> None:
        event = {"epoch": time.time(), "component": component, "message": str(message), "fatal": bool(fatal)}
        with self._lock:
            self._errors.append(event)
            self._state = "ERROR" if fatal else "DEGRADED"

    def add_warning(self, component: str, message: str) -> None:
        event = {"epoch": time.time(), "component": component, "message": str(message)}
        with self._lock:
            self._warnings.append(event)
            if self._state not in {"ERROR", "STOPPING", "STOPPED"}:
                self._state = "DEGRADED"

    def set_disk_free_gb(self, value: float) -> None:
        with self._lock:
            self._disk_free_gb = float(value)

    def snapshot(self) -> Dict[str, Any]:
        now = time.time()
        with self._lock:
            cameras = deepcopy(self._cameras)
            snapshot = {
                "state": self._state,
                "started_epoch": self._started_epoch,
                "uptime_sec": 0.0 if self._started_epoch is None else max(0.0, now - self._started_epoch),
                "connections": deepcopy(self._connections),
                "cameras": cameras,
                "session_root": self._session_root,
                "scene_id": self._scene_id,
                "network_drops": self._network_drops,
                "message_buffer": deepcopy(self._message_buffer),
                "disk_free_gb": self._disk_free_gb,
                "errors": deepcopy(self._errors),
                "warnings": deepcopy(self._warnings),
            }
        for entry in cameras.values():
            first = float(entry.get("first_seen_epoch", now) or now)
            elapsed = max(1e-6, now - first)
            entry["average_rx_fps"] = float(entry.get("frames_received", 0)) / elapsed
            entry["average_rx_mib_s"] = float(entry.get("bytes_received", 0)) / elapsed / (1024 * 1024)
        return snapshot
