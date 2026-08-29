from __future__ import annotations

import os
import socket
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    HAS_QT = True
except ImportError:  # CI/source-review environments may not have Qt installed.
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "PySide6 not installed in this test environment")
class QtGuiButtonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _pump_until(self, predicate, timeout=3.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return True
            time.sleep(0.02)
        self.app.processEvents()
        return bool(predicate())

    def test_language_switch_updates_ui_without_resetting_form_data(self):
        from carmaker_gui.i18n import LANGUAGE_SETTING_KEY, LanguageManager
        from carmaker_gui.main_window import MainWindow
        from carmaker_recorder.config import AppConfig, save_config

        class MemorySettings:
            def __init__(self):
                self.values = {}

            def value(self, key, default=None):
                return self.values.get(key, default)

            def setValue(self, key, value):  # noqa: N802 - mirrors QSettings
                self.values[key] = value

            def sync(self):
                pass

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "config.json"
            save_config(AppConfig(), config_path)
            settings = MemorySettings()
            manager = LanguageManager(settings, "en_US")
            window = MainWindow(root, config_path, language_manager=manager)
            window.connection_page.host.setText("capture-host")
            window.show()
            self.app.processEvents()

            self.assertEqual(window.dashboard_page.page_title.text(), "Capture Monitor")
            chinese_index = window.language_combo.findData("zh")
            window.language_combo.setCurrentIndex(chinese_index)
            self.app.processEvents()
            self.assertEqual(window.dashboard_page.page_title.text(), "采集监控")
            self.assertEqual(window.connection_page.host.text(), "capture-host")
            self.assertEqual(settings.values[LANGUAGE_SETTING_KEY], "zh")

            english_index = window.language_combo.findData("en")
            window.language_combo.setCurrentIndex(english_index)
            self.app.processEvents()
            self.assertEqual(window.dashboard_page.page_title.text(), "Capture Monitor")
            self.assertEqual(window.connection_page.host.text(), "capture-host")
            window.close()
            self.app.processEvents()

    def test_start_enables_stop_and_stop_finishes_worker(self):
        from carmaker_gui.main_window import MainWindow
        from carmaker_recorder.config import save_config

        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            from tests.helpers import latest_config

            cfg = latest_config(
                network={
                    "host": "127.0.0.1",
                    "ports": [port],
                    "socket_timeout_sec": 5.0,
                    "connect_timeout_sec": 2.0,
                    "max_timeouts_before_reconnect": 2,
                    "reconnect_delay_sec": 10.0,
                    "header_size": 64,
                },
                video={"enabled": False},
                images={"enabled": True, "sample_hz": 10.0},
                reliability={"min_free_disk_gb": 0.0},
                output={"save_root": str(root / "capture")},
                gui={"live_preview": False, "preview_hz": 2.0},
            )
            config_path = root / "config.json"
            save_config(cfg, config_path)
            window = MainWindow(root, config_path)
            window.show()
            self.app.processEvents()

            self.assertTrue(window.start_button.isEnabled())
            self.assertFalse(window.stop_button.isEnabled())
            QTest.mouseClick(window.start_button, Qt.LeftButton)
            self.assertTrue(self._pump_until(lambda: window.stop_button.isEnabled()))
            self.assertFalse(window.start_button.isEnabled())

            QTest.mouseClick(window.stop_button, Qt.LeftButton)
            self.assertTrue(
                self._pump_until(lambda: window.worker is None, timeout=4.0)
            )
            self.assertTrue(window.start_button.isEnabled())
            self.assertFalse(window.stop_button.isEnabled())
            window.close()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
