from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, List

SCHEMA_VERSION = 5
TOOL_VERSION = "1.5.0"

_WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_INVALID_FILENAME_CHARS = set('<>:"/\\|?*')


def _validate_camera_name(name: str) -> None:
    value = str(name).strip()
    if not value:
        raise ValueError("camera display/output name must not be empty")
    if any(ch in _INVALID_FILENAME_CHARS for ch in value):
        raise ValueError(f"camera name contains Windows-invalid filename characters: {value!r}")
    if value.endswith((".", " ")):
        raise ValueError(f"camera name must not end with dot/space: {value!r}")
    if value.upper() in _WINDOWS_RESERVED_NAMES:
        raise ValueError(f"camera name is a Windows-reserved filename: {value!r}")


@dataclass(frozen=True)
class NetworkConfig:
    host: str = "localhost"
    ports: List[int] = field(default_factory=lambda: [2210])
    socket_timeout_sec: float = 3.0
    connect_timeout_sec: float = 2.0
    reconnect_delay_sec: float = 0.5
    max_timeouts_before_reconnect: int = 1
    header_size: int = 64
    max_payload_bytes: int = 256 * 1024 * 1024


@dataclass(frozen=True)
class BufferConfig:
    message_capacity: int = 512
    frame_capacity: int = 180
    image_task_capacity: int = 512


@dataclass(frozen=True)
class VideoConfig:
    enabled: bool = True
    fps: float = 30.0
    backend: str = "auto"
    codec: str = "h264"
    bitrate_mbps: float = 12.0
    allow_cpu_fallback: bool = True
    ffmpeg_path: str = "ffmpeg"
    fourcc: str = "XVID"
    extension: str = "avi"
    max_gap_fill_frames: int = 60


@dataclass(frozen=True)
class ImageConfig:
    enabled: bool = True
    sample_hz: float = 10.0
    export_format: str = "jpg"
    jpeg_quality: int = 95


@dataclass(frozen=True)
class ReliabilityConfig:
    writer_failure_policy: str = "stop"  # stop | degraded
    min_free_disk_gb: float = 2.0
    disk_check_interval_sec: float = 5.0
    mark_degraded_on_drop: bool = True
    sim_time_reset_threshold_sec: float = 0.5


@dataclass(frozen=True)
class LoggingConfig:
    level: str = "INFO"
    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 5


@dataclass(frozen=True)
class OutputConfig:
    save_root: str = "carmaker_videos"
    camera_names: Dict[int, str] = field(default_factory=lambda: {
        0: "FRONT",
        1: "FRONT_LEFT",
        2: "FRONT_RIGHT",
        3: "BACK_LEFT",
        4: "BACK_RIGHT",
        5: "BACK",
    })


@dataclass(frozen=True)
class GuiConfig:
    live_preview: bool = True
    preview_hz: float = 2.0


@dataclass(frozen=True)
class AppConfig:
    schema_version: int = SCHEMA_VERSION
    network: NetworkConfig = field(default_factory=NetworkConfig)
    buffers: BufferConfig = field(default_factory=BufferConfig)
    video: VideoConfig = field(default_factory=VideoConfig)
    images: ImageConfig = field(default_factory=ImageConfig)
    reliability: ReliabilityConfig = field(default_factory=ReliabilityConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    gui: GuiConfig = field(default_factory=GuiConfig)

    def camera_name(self, cam_id: str) -> str:
        try:
            return self.output.camera_names.get(int(cam_id), str(cam_id))
        except (TypeError, ValueError):
            return str(cam_id)

    def resolve_save_root(self, base_dir: Path) -> Path:
        raw = os.path.expandvars(os.path.expanduser(self.output.save_root))
        p = Path(raw)
        return p if p.is_absolute() else (base_dir / p).resolve()

def _strict_section(data: Dict[str, Any], name: str, cls) -> Dict[str, Any]:
    if name not in data:
        raise ValueError(f"missing required config section: {name}")
    value = data[name]
    if not isinstance(value, dict):
        raise ValueError(f"config section '{name}' must be an object")
    expected = {item.name for item in fields(cls)}
    actual = set(value)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        parts = []
        if missing:
            parts.append(f"missing={missing}")
        if extra:
            parts.append(f"unknown={extra}")
        raise ValueError(f"config section '{name}' does not match schema v{SCHEMA_VERSION}: " + ", ".join(parts))
    return value


def config_from_dict(raw: Dict[str, Any]) -> AppConfig:
    """Parse the current schema and reject missing, unknown, or legacy fields."""
    if not isinstance(raw, dict):
        raise ValueError("config root must be an object")
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"config.schema_version must be exactly {SCHEMA_VERSION} for v{TOOL_VERSION}"
        )
    expected_root = {
        "schema_version", "network", "buffers", "video", "images",
        "reliability", "logging", "output", "gui",
    }
    actual_root = set(raw)
    if actual_root != expected_root:
        missing = sorted(expected_root - actual_root)
        extra = sorted(actual_root - expected_root)
        raise ValueError(
            f"config root does not match schema v{SCHEMA_VERSION}: missing={missing}, unknown={extra}"
        )

    network = NetworkConfig(**_strict_section(raw, "network", NetworkConfig))
    buffers = BufferConfig(**_strict_section(raw, "buffers", BufferConfig))
    video = VideoConfig(**_strict_section(raw, "video", VideoConfig))
    images = ImageConfig(**_strict_section(raw, "images", ImageConfig))
    reliability = ReliabilityConfig(**_strict_section(raw, "reliability", ReliabilityConfig))
    logging_cfg = LoggingConfig(**_strict_section(raw, "logging", LoggingConfig))

    output_raw = dict(_strict_section(raw, "output", OutputConfig))
    camera_names_raw = output_raw.get("camera_names")
    if not isinstance(camera_names_raw, dict):
        raise ValueError("output.camera_names must be an object")
    converted_camera_names: Dict[int, str] = {}
    for raw_id, raw_name in camera_names_raw.items():
        try:
            camera_id = int(raw_id)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"camera ID must be an integer: {raw_id!r}") from exc
        if camera_id < 0:
            raise ValueError(f"camera ID must be >= 0: {camera_id}")
        if camera_id in converted_camera_names:
            raise ValueError(f"duplicate camera ID after integer normalization: {camera_id}")
        converted_camera_names[camera_id] = str(raw_name)
    output_raw["camera_names"] = converted_camera_names
    output = OutputConfig(**output_raw)
    gui = GuiConfig(**_strict_section(raw, "gui", GuiConfig))

    host = network.host.strip()
    if not host:
        raise ValueError("network.host must not be empty")
    if network.header_size <= 0:
        raise ValueError("network.header_size must be > 0")
    if network.max_payload_bytes < 1024 * 1024:
        raise ValueError("network.max_payload_bytes must be >= 1 MiB")
    if not network.ports:
        raise ValueError("network.ports must contain at least one port")
    if len(set(int(p) for p in network.ports)) != len(network.ports):
        raise ValueError("network.ports must not contain duplicates")
    if any(not (1 <= int(p) <= 65535) for p in network.ports):
        raise ValueError("all network.ports must be in range 1..65535")
    if network.socket_timeout_sec <= 0 or network.connect_timeout_sec <= 0:
        raise ValueError("network timeouts must be > 0")
    if network.reconnect_delay_sec < 0:
        raise ValueError("network.reconnect_delay_sec must be >= 0")
    if network.max_timeouts_before_reconnect <= 0:
        raise ValueError("network.max_timeouts_before_reconnect must be > 0")

    if min(buffers.message_capacity, buffers.frame_capacity, buffers.image_task_capacity) < 2:
        raise ValueError("all buffer capacities must be >= 2")

    if not video.enabled and not images.enabled:
        raise ValueError("at least one of video/images must be enabled")
    if video.backend not in {"auto", "opencv", "nvenc", "qsv", "amf"}:
        raise ValueError("video.backend must be auto/opencv/nvenc/qsv/amf")
    if video.codec not in {"h264", "hevc", "av1"}:
        raise ValueError("video.codec must be h264/hevc/av1")
    if video.bitrate_mbps <= 0:
        raise ValueError("video.bitrate_mbps must be > 0")
    if not video.ffmpeg_path.strip():
        raise ValueError("video.ffmpeg_path must not be empty")
    if len(video.fourcc) != 4:
        raise ValueError("video.fourcc must contain exactly 4 characters")
    if video.fps <= 0:
        raise ValueError("video.fps must be > 0")
    if video.max_gap_fill_frames < 0:
        raise ValueError("video.max_gap_fill_frames must be >= 0")
    if not re.fullmatch(r"[A-Za-z0-9]{1,8}", video.extension):
        raise ValueError("video.extension must contain 1..8 letters/numbers without a dot")

    if images.sample_hz <= 0:
        raise ValueError("images.sample_hz must be > 0")
    if images.export_format.lower() not in {"auto", "ppm", "g8", "g16", "raw", "jpg"}:
        raise ValueError("images.export_format is unsupported")
    if not (1 <= images.jpeg_quality <= 100):
        raise ValueError("images.jpeg_quality must be in range 1..100")

    if reliability.writer_failure_policy not in {"stop", "degraded"}:
        raise ValueError("reliability.writer_failure_policy must be 'stop' or 'degraded'")
    if reliability.min_free_disk_gb < 0:
        raise ValueError("reliability.min_free_disk_gb must be >= 0")
    if reliability.disk_check_interval_sec <= 0:
        raise ValueError("reliability.disk_check_interval_sec must be > 0")
    if reliability.sim_time_reset_threshold_sec <= 0:
        raise ValueError("reliability.sim_time_reset_threshold_sec must be > 0")

    if logging_cfg.level.upper() not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
        raise ValueError("logging.level must be DEBUG/INFO/WARNING/ERROR")
    if logging_cfg.max_bytes < 1024:
        raise ValueError("logging.max_bytes must be >= 1024")
    if logging_cfg.backup_count < 1:
        raise ValueError("logging.backup_count must be >= 1")

    if not output.save_root.strip():
        raise ValueError("output.save_root must not be empty")
    camera_name_keys = []
    for camera_name in output.camera_names.values():
        _validate_camera_name(camera_name)
        camera_name_keys.append(str(camera_name).strip().casefold())
    if len(camera_name_keys) != len(set(camera_name_keys)):
        raise ValueError("output.camera_names must be unique to avoid output collisions")

    if gui.preview_hz <= 0:
        raise ValueError("gui.preview_hz must be > 0")

    return AppConfig(
        schema_version=SCHEMA_VERSION,
        network=network,
        buffers=buffers,
        video=video,
        images=images,
        reliability=reliability,
        logging=logging_cfg,
        output=output,
        gui=gui,
    )


def config_to_dict(config: AppConfig) -> Dict[str, Any]:
    raw = asdict(config)
    raw["schema_version"] = SCHEMA_VERSION
    raw["output"]["camera_names"] = {str(k): v for k, v in config.output.camera_names.items()}
    return raw


def load_config(path: str | Path) -> AppConfig:
    path = Path(path).expanduser().resolve()
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    return config_from_dict(raw)


def save_config(config: AppConfig, path: str | Path) -> Path:
    path = Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(config_to_dict(config), f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    return path
