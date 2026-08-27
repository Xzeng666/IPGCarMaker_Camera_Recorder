import tempfile
import unittest
from pathlib import Path

from carmaker_recorder.config import SCHEMA_VERSION, AppConfig, load_config, save_config
from carmaker_recorder.models import CamFrame
from carmaker_recorder.monitor import RecorderMonitor


class GuiSupportTests(unittest.TestCase):
    def test_config_roundtrip(self):
        config = AppConfig()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "config.json"
            save_config(config, path)
            loaded = load_config(path)
            self.assertEqual(loaded.schema_version, SCHEMA_VERSION)
            self.assertEqual(loaded.network.host, "localhost")
            self.assertEqual(loaded.network.ports, [2210])
            self.assertEqual(loaded.images.sample_hz, 10.0)

    def test_monitor_frame_stats_without_preview(self):
        config = AppConfig()
        monitor = RecorderMonitor(config, capture_previews=False)
        monitor.reset()
        monitor.set_connection(2210, "CONNECTED")
        frame = CamFrame("0", "rgb", 1.25, 2, 2, bytes([0] * 12), received_epoch=1.0, source_port=2210)
        monitor.mark_frame(frame)
        monitor.mark_image_written("0")
        monitor.mark_video_frame_written("0")
        snap = monitor.snapshot()
        self.assertEqual(snap["connections"][2210], "CONNECTED")
        self.assertEqual(snap["cameras"]["0"]["frames_received"], 1)
        self.assertEqual(snap["cameras"]["0"]["images_written"], 1)
        self.assertEqual(snap["cameras"]["0"]["video_frames_written"], 1)
        monitor.stop_preview_worker()


if __name__ == "__main__":
    unittest.main()
