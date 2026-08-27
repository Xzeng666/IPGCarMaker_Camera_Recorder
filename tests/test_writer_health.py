from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

from carmaker_recorder.models import ImageTask
from carmaker_recorder.writers import ImageSaver
from tests.helpers import latest_config


class WriterHealthTests(unittest.TestCase):
    def test_image_writer_failure_is_exposed(self):
        failures = []
        evt = threading.Event()
        def callback(kind, cam_id, exc):
            failures.append((kind, cam_id, str(exc)))
            evt.set()

        with tempfile.TemporaryDirectory() as td:
            cfg = latest_config(
                video={"enabled": False},
                images={"enabled": True, "export_format": "jpg"},
                reliability={"min_free_disk_gb": 0.0},
            )
            saver = ImageSaver(Path(td), "0", "stamp", cfg, error_callback=callback)
            saver.start()
            saver.push(ImageTask("0", "unsupported", 0.0, 2, 2, b"bad", "localhost", 2210))
            self.assertTrue(evt.wait(2.0))
            saver.stop_and_drain(); saver.join(timeout=2.0)
            self.assertFalse(saver.healthy)
            self.assertEqual(failures[0][0:2], ("image", "0"))


if __name__ == "__main__":
    unittest.main()
