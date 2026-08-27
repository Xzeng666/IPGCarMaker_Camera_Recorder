from __future__ import annotations

import logging
import socket
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from carmaker_recorder.config import AppConfig
from carmaker_recorder.monitor import RecorderMonitor
from carmaker_recorder.runtime import RecorderRuntime


class RecorderThread(QThread):
    failed = Signal(str)

    def __init__(self, config: AppConfig, base_dir: Path, capture_previews: bool = True, parent=None):
        super().__init__(parent)
        self.monitor = RecorderMonitor(config, capture_previews=capture_previews, preview_hz=config.gui.preview_hz)
        self.runtime = RecorderRuntime(config, base_dir, monitor=self.monitor)

    def run(self) -> None:
        try:
            self.runtime.run()
        except Exception as exc:
            logging.getLogger(__name__).exception("Recorder runtime failed")
            self.failed.emit(str(exc))

    def stop(self) -> None:
        self.runtime.stop()


class ConnectionTestThread(QThread):
    result = Signal(dict)

    def __init__(self, host: str, ports: list[int], timeout_sec: float = 1.5, parent=None):
        super().__init__(parent)
        self.host = host
        self.ports = ports
        self.timeout_sec = timeout_sec

    def run(self) -> None:
        results = {}
        for port in self.ports:
            if self.isInterruptionRequested():
                break
            try:
                with socket.create_connection((self.host, int(port)), timeout=self.timeout_sec):
                    results[int(port)] = True
            except OSError:
                results[int(port)] = False
        if not self.isInterruptionRequested():
            self.result.emit(results)


class LogEmitter(QObject):
    message = Signal(str, int)


class QtLogHandler(logging.Handler):
    def __init__(self, emitter: LogEmitter):
        super().__init__()
        self.emitter = emitter

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.emitter.message.emit(self.format(record), record.levelno)
        except Exception:
            self.handleError(record)
