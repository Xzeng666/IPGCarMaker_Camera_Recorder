from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path

from carmaker_recorder.models import CamFrame, Message
from carmaker_recorder.processor import SequentialProcessor
from carmaker_recorder.ring_buffer import RingBuffer
from tests.helpers import latest_config


def frame(port: int, cam: str, sim_time: float) -> CamFrame:
    return CamFrame(
        cam_id=cam,
        fmt="rgb",
        sim_time=sim_time,
        width=1,
        height=1,
        payload=b"\x00\x00\x00",
        received_epoch=time.time(),
        source_port=port,
    )


class SimTimeStreamIntegrityTests(unittest.TestCase):
    def make_processor(self, root: Path) -> SequentialProcessor:
        cfg = latest_config(
            output={"save_root": str(root)},
            reliability={"sim_time_reset_threshold_sec": 0.5},
        )
        return SequentialProcessor(
            root,
            RingBuffer[Message](8),
            threading.Event(),
            cfg,
            time.time(),
        )

    def test_cross_camera_transport_skew_is_not_a_false_reset(self):
        with tempfile.TemporaryDirectory() as td:
            proc = self.make_processor(Path(td))
            self.assertTrue(proc._check_sim_time(frame(2210, "0", 10.0)))
            # A different stream may legitimately arrive far behind in sim-time.
            self.assertTrue(proc._check_sim_time(frame(2211, "1", 9.0)))
            self.assertFalse(proc.global_exit_evt.is_set())

    def test_same_stream_large_rollback_is_fatal(self):
        with tempfile.TemporaryDirectory() as td:
            proc = self.make_processor(Path(td))
            self.assertTrue(proc._check_sim_time(frame(2210, "0", 10.0)))
            self.assertFalse(proc._check_sim_time(frame(2210, "0", 8.0)))
            self.assertTrue(proc.global_exit_evt.is_set())


if __name__ == "__main__":
    unittest.main()
