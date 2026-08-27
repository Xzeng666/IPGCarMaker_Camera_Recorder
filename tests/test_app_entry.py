from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from carmaker_recorder.app import run
from tests.helpers import latest_config


class AppEntryTests(unittest.TestCase):
    def test_run_invokes_runtime(self):
        with tempfile.TemporaryDirectory() as td, patch("carmaker_recorder.app.RecorderRuntime") as runtime_cls:
            run(latest_config(), Path(td))
            runtime_cls.assert_called_once()
            runtime_cls.return_value.run.assert_called_once()

    def test_keyboard_interrupt_requests_stop(self):
        with tempfile.TemporaryDirectory() as td, patch("carmaker_recorder.app.RecorderRuntime") as runtime_cls:
            runtime_cls.return_value.run.side_effect = KeyboardInterrupt
            run(latest_config(), Path(td))
            runtime_cls.return_value.stop.assert_called_once()


if __name__ == "__main__":
    unittest.main()
