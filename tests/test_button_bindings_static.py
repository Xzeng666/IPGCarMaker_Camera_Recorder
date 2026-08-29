import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ButtonBindingStaticTests(unittest.TestCase):
    def test_main_toolbar_bindings(self):
        text = (ROOT / "carmaker_gui" / "main_window.py").read_text(encoding="utf-8")
        expected = [
            "self.load_button.clicked.connect(self.open_config)",
            "self.save_button.clicked.connect(self.save_current_config)",
            "self.save_as_button.clicked.connect(self.save_config_as)",
            "self.start_button.clicked.connect(self.start_recording)",
            "self.stop_button.clicked.connect(self.stop_recording)",
            "self.connection_page.test_button.clicked.connect(self.test_connection)",
            "self.language_combo.currentIndexChanged.connect(self._on_language_changed)",
            "self.save_action.triggered.connect(self.save_current_config)",
        ]
        for binding in expected:
            self.assertIn(binding, text)
        self.assertIn("worker.finished.connect(self._on_runtime_finished)", text)

    def test_page_button_bindings(self):
        text = (ROOT / "carmaker_gui" / "pages.py").read_text(encoding="utf-8")
        expected = [
            "self.open_output.clicked.connect(self._open_output)",
            "self.add_button.clicked.connect(self.add_row)",
            "self.remove_button.clicked.connect(self.remove_selected)",
            "self.restore_button.clicked.connect(self.restore_defaults)",
            "self.clear_button.clicked.connect(self.text.clear)",
            "self.export_button.clicked.connect(self.export_log)",
        ]
        for binding in expected:
            self.assertIn(binding, text)

    def test_dependency_toggle_bindings(self):
        text = (ROOT / "carmaker_gui" / "pages.py").read_text(encoding="utf-8")
        self.assertIn(
            "self.video_enabled.toggled.connect(self.video_fps.setEnabled)", text
        )
        self.assertIn(
            "self.images_enabled.toggled.connect(self.image_hz.setEnabled)", text
        )
        self.assertIn(
            "self.images_enabled.toggled.connect(self.image_format.setEnabled)", text
        )
        self.assertIn(
            "self.images_enabled.toggled.connect(self.jpeg_quality.setEnabled)", text
        )

    def test_path_browse_binding(self):
        text = (ROOT / "carmaker_gui" / "widgets.py").read_text(encoding="utf-8")
        self.assertIn("self.browse.clicked.connect(self._browse)", text)


if __name__ == "__main__":
    unittest.main()
