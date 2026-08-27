from __future__ import annotations

import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

from carmaker_recorder.monitor import RecorderMonitor
from carmaker_recorder.runtime import RecorderRuntime
from carmaker_recorder.session import SessionManager
from tests.helpers import latest_config


def _config(root: Path, port: int, *, reconnect_delay: float = 30.0, socket_timeout: float = 30.0):
    return latest_config(
        network={
            "host": "127.0.0.1",
            "ports": [port],
            "socket_timeout_sec": socket_timeout,
            "connect_timeout_sec": 10.0,
            "max_timeouts_before_reconnect": 10,
            "reconnect_delay_sec": reconnect_delay,
            "header_size": 64,
        },
        video={"enabled": False},
        images={"enabled": True, "sample_hz": 10.0},
        reliability={"min_free_disk_gb": 0.0},
        output={"save_root": str(root)},
        gui={"live_preview": False, "preview_hz": 2.0},
    )


def _wait_for(predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate(): return True
        time.sleep(0.02)
    return bool(predicate())


class RuntimeStopTests(unittest.TestCase):
    def test_stop_interrupts_long_reconnect_delay(self):
        probe = socket.socket(); probe.bind(("127.0.0.1", 0)); port = probe.getsockname()[1]; probe.close()
        with tempfile.TemporaryDirectory() as td:
            cfg = _config(Path(td), port, reconnect_delay=30.0)
            monitor = RecorderMonitor(cfg)
            runtime = RecorderRuntime(cfg, Path(td), monitor=monitor)
            thread = threading.Thread(target=runtime.run, name="runtime-test")
            thread.start()
            self.assertTrue(_wait_for(lambda: monitor.snapshot()["connections"].get(port) == "RETRYING"))
            t0 = time.monotonic(); runtime.stop(); thread.join(timeout=2.0)
            self.assertFalse(thread.is_alive())
            self.assertLess(time.monotonic() - t0, 2.0)
            self.assertEqual(monitor.snapshot()["state"], "STOPPED")

    def test_stop_interrupts_blocking_recv(self):
        server = socket.socket(); server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); server.bind(("127.0.0.1", 0)); server.listen(1)
        port = server.getsockname()[1]; accepted = threading.Event(); release = threading.Event()
        def serve():
            try:
                conn, _ = server.accept(); accepted.set()
                with conn: release.wait(5.0)
            finally: server.close()
        threading.Thread(target=serve, daemon=True).start()
        with tempfile.TemporaryDirectory() as td:
            cfg = _config(Path(td), port, socket_timeout=30.0)
            monitor = RecorderMonitor(cfg); runtime = RecorderRuntime(cfg, Path(td), monitor=monitor)
            thread = threading.Thread(target=runtime.run, name="runtime-active-recv"); thread.start()
            self.assertTrue(accepted.wait(2.0)); self.assertTrue(_wait_for(lambda: monitor.snapshot()["connections"].get(port) == "CONNECTED"))
            t0 = time.monotonic(); runtime.stop(); thread.join(timeout=2.0); release.set()
            self.assertFalse(thread.is_alive()); self.assertLess(time.monotonic() - t0, 2.0)

    def test_session_directories_never_reuse_existing_path(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            first = SessionManager(root, 1).ensure_created().root
            second = SessionManager(root, 1).ensure_created().root
            self.assertNotEqual(first, second)

    def test_runtime_rejects_insufficient_disk_before_threads_start(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            probe = socket.socket(); probe.bind(("127.0.0.1", 0)); port = probe.getsockname()[1]; probe.close()
            cfg = _config(root, port)
            raw = __import__('carmaker_recorder.config', fromlist=['config_to_dict']).config_to_dict(cfg)
            raw['reliability']['min_free_disk_gb'] = 10**9
            from carmaker_recorder.config import config_from_dict
            runtime = RecorderRuntime(config_from_dict(raw), root)
            with self.assertRaises(RuntimeError):
                runtime.run()


if __name__ == "__main__":
    unittest.main()
