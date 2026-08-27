from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .config import AppConfig, TOOL_VERSION, config_to_dict

LOG = logging.getLogger(__name__)


def _iso(epoch: float | None) -> str | None:
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


@dataclass(frozen=True)
class SessionPaths:
    root: Path
    videos_dir: Path
    images_dir: Path
    system_time_str: str
    scene_id_str: str
    manifest_path: Path


class SessionManager:
    """One logical CarMaker simulation segment with traceable wall/sim timebase."""

    def __init__(self, save_root: Path, scene_index: int, runtime_start_epoch: float | None = None):
        self.save_root = Path(save_root)
        self.scene_index = int(scene_index)
        self._lock = threading.Lock()
        self._paths: SessionPaths | None = None
        self.runtime_start_epoch = float(runtime_start_epoch or time.time())
        self.first_frame_epoch: Optional[float] = None
        self.last_frame_epoch: Optional[float] = None
        self.first_sim_time: Optional[float] = None
        self.last_sim_time: Optional[float] = None
        self.frames_observed = 0

    def observe_frame(self, sim_time: float, received_epoch: float) -> None:
        with self._lock:
            t = float(sim_time)
            wall = float(received_epoch or time.time())
            if self.first_frame_epoch is None:
                self.first_frame_epoch = wall
                self.first_sim_time = t
            self.last_frame_epoch = wall
            self.last_sim_time = t
            self.frames_observed += 1

    def ensure_created(self) -> SessionPaths:
        with self._lock:
            if self._paths is not None:
                return self._paths

            now = datetime.now()
            millis = int(now.microsecond / 1000)
            stamp = now.strftime("%Y.%m.%d-%H_%M_%S") + f"_{millis:03d}"
            base = f"{stamp}-scene-{self.scene_index:04d}"
            root = self.save_root / base
            suffix = 2
            while root.exists():
                root = self.save_root / f"{base}-{suffix}"
                suffix += 1

            videos = root / "Videos"
            images = root / "Images"
            for directory in (videos, images):
                directory.mkdir(parents=True, exist_ok=True)

            scene_id = f"{self.scene_index:04d}"
            self._paths = SessionPaths(
                root=root,
                videos_dir=videos,
                images_dir=images,
                system_time_str=now.strftime("%Y.%m.%d-%H_%M_%S"),
                scene_id_str=scene_id,
                manifest_path=root / "session_manifest.json",
            )
            LOG.info("Session created: %s (scene-%s)", root, scene_id)
            return self._paths

    @property
    def created(self) -> bool:
        with self._lock:
            return self._paths is not None

    @property
    def paths(self) -> SessionPaths | None:
        with self._lock:
            return self._paths

    def write_manifest(
        self,
        config: AppConfig,
        monitor_snapshot: dict[str, Any],
        *,
        end_epoch: float | None = None,
        runtime_log: str | None = None,
    ) -> Path | None:
        paths = self.paths
        if paths is None:
            return None
        end = float(end_epoch or time.time())
        manifest = {
            "tool": {
                "name": "CarMaker CameraRSI Recorder",
                "version": TOOL_VERSION,
                "config_schema": config.schema_version,
            },
            "session": {
                "scene_id": paths.scene_id_str,
                "root": str(paths.root),
                "runtime_start_utc": _iso(self.runtime_start_epoch),
                "capture_start_utc": _iso(self.first_frame_epoch),
                "capture_end_utc": _iso(self.last_frame_epoch or end),
                "finalize_utc": _iso(end),
                "first_sim_time": self.first_sim_time,
                "last_sim_time": self.last_sim_time,
                "timebase": {
                    "simulation": "CameraRSI sim_time",
                    "wall_clock": "local receive timestamps in UTC",
                },
                "frames_observed": self.frames_observed,
            },
            "source": {
                "host": config.network.host,
                "ports": list(config.network.ports),
            },
            "outputs": {
                "video_enabled": config.video.enabled,
                "image_enabled": config.images.enabled,
                "runtime_log": runtime_log,
            },
            "telemetry": {
                "connections": monitor_snapshot.get("connections", {}),
                "cameras": monitor_snapshot.get("cameras", {}),
                "network_drops": monitor_snapshot.get("network_drops", 0),
                "message_buffer": monitor_snapshot.get("message_buffer", {}),
                "disk_free_gb": monitor_snapshot.get("disk_free_gb"),
            },
            "errors": monitor_snapshot.get("errors", []),
            "warnings": monitor_snapshot.get("warnings", []),
            "config": config_to_dict(config),
        }
        # Preview JPEGs are runtime-only and must never bloat the manifest.
        for camera in manifest["telemetry"]["cameras"].values():
            camera.pop("preview_jpeg", None)

        tmp = paths.manifest_path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, paths.manifest_path)
        LOG.info("Session manifest written: %s", paths.manifest_path)
        return paths.manifest_path
