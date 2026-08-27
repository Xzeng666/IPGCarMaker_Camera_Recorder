from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from carmaker_recorder.models import CamFrame
from carmaker_recorder.writers import CameraWriter
from tests.helpers import latest_config


def rgb_frame(w: int, h: int, t: float) -> CamFrame:
    return CamFrame(
        cam_id="0",
        fmt="rgb",
        sim_time=t,
        width=w,
        height=h,
        payload=bytes([20, 40, 60]) * (w * h),
        received_epoch=time.time(),
        source_port=2210,
    )


class VideoWriterSegmentTests(unittest.TestCase):
    def test_resolution_change_creates_new_segment(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = latest_config(
                video={"fourcc": "MJPG", "extension": "avi", "fps": 30.0, "max_gap_fill_frames": 5},
            )
            writer = CameraWriter(root, "0", "test", cfg)
            writer.start()
            writer.push(rgb_frame(8, 8, 0.0))
            writer.push(rgb_frame(8, 8, 1 / 30))
            writer.push(rgb_frame(10, 10, 2 / 30))
            writer.stop_and_drain()
            writer.join(timeout=5)
            self.assertFalse(writer.is_alive())
            self.assertTrue(writer.healthy, writer.last_error)
            self.assertEqual(writer.segment_index, 2)
            self.assertEqual(len(list(root.glob("*_part*.avi"))), 2)

    def test_large_time_gap_creates_new_segment_instead_of_unbounded_fill(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = latest_config(
                video={"fourcc": "MJPG", "extension": "avi", "fps": 30.0, "max_gap_fill_frames": 2},
            )
            writer = CameraWriter(root, "0", "test", cfg)
            writer.start()
            writer.push(rgb_frame(8, 8, 0.0))
            writer.push(rgb_frame(8, 8, 1.0))
            writer.stop_and_drain()
            writer.join(timeout=5)
            self.assertTrue(writer.healthy, writer.last_error)
            self.assertEqual(writer.segment_index, 2)
            self.assertLess(writer.frames_written, 10)


if __name__ == "__main__":
    unittest.main()
