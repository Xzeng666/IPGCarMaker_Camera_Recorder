from __future__ import annotations

import logging
import shutil
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from .config import AppConfig
from .models import Message
from .monitor import RecorderMonitor
from .network import NetworkReceiver
from .processor import SequentialProcessor
from .ring_buffer import RingBuffer

LOG = logging.getLogger(__name__)


class RecorderRuntime:
    """Stoppable recorder runtime shared by CLI and GUI.

    Each RSDS port reconnects independently. A single port failure never ends
    other healthy ports. The run ends only on user stop or a fail-fast integrity
    error (writer, disk, simulation-time reset, processor failure).
    """

    def __init__(
        self,
        config: AppConfig,
        base_dir: Path,
        monitor: Optional[RecorderMonitor] = None,
    ):
        self.config = config
        self.base_dir = Path(base_dir).resolve()
        self.monitor = monitor or RecorderMonitor(config, capture_previews=False)
        self._global_exit_evt = threading.Event()
        self._run_lock = threading.Lock()
        self._active_lock = threading.Lock()
        self._active_receivers: list[NetworkReceiver] = []
        self._processor: SequentialProcessor | None = None
        self.runtime_log_path: Path | None = None
        self._file_handler: RotatingFileHandler | None = None
        self._previous_root_level: int | None = None

    @property
    def stop_requested(self) -> bool:
        return self._global_exit_evt.is_set()

    def stop(self) -> None:
        if self.monitor.snapshot().get("state") not in {"ERROR", "STOPPED"}:
            self.monitor.set_state("STOPPING")
        self._global_exit_evt.set()
        with self._active_lock:
            receivers = list(self._active_receivers)
        for receiver in receivers:
            receiver.request_stop()

    def _set_active_receivers(self, receivers: list[NetworkReceiver]) -> None:
        with self._active_lock:
            self._active_receivers = list(receivers)

    def _attach_file_logging(self, save_root: Path) -> None:
        logs_dir = save_root / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        self.runtime_log_path = logs_dir / time.strftime("recorder-%Y%m%d.log")
        handler = RotatingFileHandler(
            self.runtime_log_path,
            maxBytes=self.config.logging.max_bytes,
            backupCount=self.config.logging.backup_count,
            encoding="utf-8",
        )
        handler.setLevel(getattr(logging, self.config.logging.level.upper()))
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-7s | %(threadName)s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        root_logger = logging.getLogger()
        self._previous_root_level = root_logger.level
        desired = getattr(logging, self.config.logging.level.upper())
        if root_logger.level == logging.NOTSET or desired < root_logger.level:
            root_logger.setLevel(desired)
        root_logger.addHandler(handler)
        self._file_handler = handler

    def _detach_file_logging(self) -> None:
        handler = self._file_handler
        self._file_handler = None
        if handler is not None:
            root_logger = logging.getLogger()
            root_logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                LOG.debug("Failed to close runtime log handler", exc_info=True)
            if self._previous_root_level is not None:
                root_logger.setLevel(self._previous_root_level)
        self._previous_root_level = None

    def run(self) -> None:
        if not self._run_lock.acquire(blocking=False):
            raise RuntimeError("RecorderRuntime is already running")
        self._global_exit_evt.clear()

        receivers: list[NetworkReceiver] = []
        msg_ring: RingBuffer[Message] | None = None
        try:
            runtime_start_epoch = time.time()
            save_root = self.config.resolve_save_root(self.base_dir)
            save_root.mkdir(parents=True, exist_ok=True)
            free_gb = shutil.disk_usage(save_root).free / (1024 ** 3)
            if free_gb < self.config.reliability.min_free_disk_gb:
                raise RuntimeError(
                    f"free disk space {free_gb:.2f} GiB is below configured minimum "
                    f"{self.config.reliability.min_free_disk_gb:.2f} GiB"
                )

            self.monitor.reset()
            self.monitor.set_disk_free_gb(free_gb)
            self._attach_file_logging(save_root)
            msg_ring = RingBuffer(self.config.buffers.message_capacity)

            self.monitor.set_state("WAITING")
            receivers = [
                NetworkReceiver(
                    self.config.network.host,
                    port,
                    msg_ring,
                    self._global_exit_evt,
                    self.config,
                    monitor=self.monitor,
                )
                for port in self.config.network.ports
            ]
            self._set_active_receivers(receivers)
            for receiver in receivers:
                receiver.start()

            processor = SequentialProcessor(
                save_root,
                msg_ring,
                self._global_exit_evt,
                self.config,
                runtime_start_epoch,
                monitor=self.monitor,
                runtime_log_path=str(self.runtime_log_path) if self.runtime_log_path else None,
            )
            self._processor = processor
            processor.start()

            while not self._global_exit_evt.wait(0.2):
                pass
        except BaseException as exc:
            self._global_exit_evt.set()
            if self.monitor.snapshot().get("state") not in {"ERROR", "STOPPED"}:
                self.monitor.add_error("runtime", str(exc), fatal=True)
            raise
        finally:
            self._global_exit_evt.set()
            for receiver in receivers:
                receiver.request_stop()
            for receiver in receivers:
                if receiver.is_alive():
                    receiver.join()
            self._set_active_receivers([])

            if self._processor is not None and self._processor.is_alive():
                self._processor.join()
            self._processor = None
            if msg_ring is not None:
                self.monitor.set_message_buffer_stats(msg_ring.stats())
            self.monitor.stop_preview_worker()

            snapshot = self.monitor.snapshot()
            has_fatal = any(bool(item.get("fatal")) for item in snapshot.get("errors", []))
            if snapshot.get("state") != "STOPPED":
                self.monitor.set_state("ERROR" if has_fatal else "STOPPED")
            self._detach_file_logging()
            self._run_lock.release()
            LOG.info("Recorder stopped")
