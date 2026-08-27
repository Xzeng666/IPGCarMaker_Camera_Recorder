from __future__ import annotations

import json
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

from carmaker_recorder.monitor import RecorderMonitor
from carmaker_recorder.runtime import RecorderRuntime
from tests.helpers import latest_config


def _camera_packet(cam_id: int, sim_time: float, w: int = 16, h: int = 16) -> bytes:
    payload = bytes([cam_id * 20 % 255, 80, 160]) * (w * h)
    header = f"*CameraRSI {cam_id} rgb {sim_time:.9f} {w}x{h} {len(payload)}".encode("ascii").ljust(64, b"\x00")
    return header + payload


def _wait_for(predicate, timeout=4.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return bool(predicate())


class CaptureLoopbackTests(unittest.TestCase):
    def test_30hz_images_video_and_manifest(self):
        server = socket.socket(); server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0)); server.listen(1); port = server.getsockname()[1]
        release = threading.Event()

        def serve():
            try:
                conn, _ = server.accept()
                with conn:
                    for i in range(20):
                        conn.sendall(_camera_packet(0, i / 30.0))
                        time.sleep(0.002)
                    release.wait(3.0)
            finally:
                server.close()

        threading.Thread(target=serve, daemon=True).start()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = latest_config(
                network={"host": "127.0.0.1", "ports": [port], "reconnect_delay_sec": 0.1},
                video={"enabled": True, "fps": 30.0, "fourcc": "MJPG", "extension": "avi", "max_gap_fill_frames": 10},
                images={"enabled": True, "sample_hz": 30.0, "export_format": "jpg", "jpeg_quality": 90},
                reliability={"min_free_disk_gb": 0.0},
                output={"save_root": str(root / "capture")},
                gui={"live_preview": False},
            )
            monitor = RecorderMonitor(cfg, capture_previews=False)
            runtime = RecorderRuntime(cfg, root, monitor=monitor)
            rt = threading.Thread(target=runtime.run, name="loopback-runtime")
            rt.start()
            self.assertTrue(_wait_for(lambda: monitor.snapshot().get("cameras", {}).get("0", {}).get("frames_received", 0) >= 20))
            runtime.stop(); rt.join(timeout=5.0); release.set()
            self.assertFalse(rt.is_alive())

            sessions = [p for p in (root / "capture").iterdir() if p.is_dir() and p.name != "logs"]
            self.assertEqual(len(sessions), 1)
            session = sessions[0]
            images = list((session / "Images" / "CAM_FRONT").glob("*.jpg"))
            videos = list((session / "Videos").glob("*.avi"))
            self.assertEqual(len(images), 20)
            self.assertTrue(videos and videos[0].stat().st_size > 0)
            manifest = json.loads((session / "session_manifest.json").read_text(encoding="utf-8"))
            cam = manifest["telemetry"]["cameras"]["0"]
            self.assertEqual(cam["frames_received"], 20)
            self.assertEqual(cam["images_written"], 20)
            self.assertEqual(cam["video_queue_drops"], 0)
            self.assertEqual(len(list((root / "capture" / "logs").glob("recorder-*.log"))), 1)

    def test_one_port_disconnect_does_not_stop_other_port(self):
        s1 = socket.socket(); s1.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); s1.bind(("127.0.0.1", 0)); s1.listen(1); p1 = s1.getsockname()[1]
        s2 = socket.socket(); s2.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); s2.bind(("127.0.0.1", 0)); s2.listen(1); p2 = s2.getsockname()[1]
        release = threading.Event()

        def serve1():
            try:
                conn, _ = s1.accept()
                with conn:
                    conn.sendall(_camera_packet(0, 0.0))
            finally:
                s1.close()

        def serve2():
            try:
                conn, _ = s2.accept()
                with conn:
                    for i in range(25):
                        try:
                            conn.sendall(_camera_packet(1, i / 30.0))
                        except OSError:
                            break
                        time.sleep(0.01)
                    release.wait(3.0)
            finally:
                s2.close()

        threading.Thread(target=serve1, daemon=True).start(); threading.Thread(target=serve2, daemon=True).start()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = latest_config(
                network={"host": "127.0.0.1", "ports": [p1, p2], "reconnect_delay_sec": 0.05},
                video={"enabled": False},
                images={"enabled": True, "sample_hz": 1.0},
                reliability={"min_free_disk_gb": 0.0},
                output={"save_root": str(root / "capture")},
                gui={"live_preview": False},
            )
            monitor = RecorderMonitor(cfg)
            runtime = RecorderRuntime(cfg, root, monitor=monitor)
            rt = threading.Thread(target=runtime.run, name="multiport-runtime"); rt.start()
            self.assertTrue(_wait_for(lambda: monitor.snapshot().get("cameras", {}).get("1", {}).get("frames_received", 0) >= 15))
            snap = monitor.snapshot()
            self.assertEqual(snap["connections"].get(p2), "CONNECTED")
            self.assertNotEqual(snap["connections"].get(p1), "CONNECTED")
            self.assertTrue(rt.is_alive(), "port 1 loss must not stop the recorder while port 2 remains active")
            runtime.stop(); rt.join(timeout=5.0); release.set()
            self.assertFalse(rt.is_alive())


if __name__ == "__main__":
    unittest.main()
