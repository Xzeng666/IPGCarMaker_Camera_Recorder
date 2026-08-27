from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow
from .theme import COLORS, stylesheet


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CarMaker CameraRSI Recorder GUI")
    parser.add_argument("--config", default="config.json", help="JSON config path")
    parser.add_argument("--smoke-test", action="store_true", help="Create the full GUI offscreen and exit automatically")
    return parser.parse_args()


def _apply_light_palette(app: QApplication) -> None:
    """Pin a readable light palette even when Windows itself uses dark mode."""
    c = COLORS
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(c["bg"]))
    palette.setColor(QPalette.WindowText, QColor(c["text"]))
    palette.setColor(QPalette.Base, QColor(c["panel"]))
    palette.setColor(QPalette.AlternateBase, QColor(c["panel_alt"]))
    palette.setColor(QPalette.Text, QColor(c["text"]))
    palette.setColor(QPalette.Button, QColor(c["panel"]))
    palette.setColor(QPalette.ButtonText, QColor(c["text"]))
    palette.setColor(QPalette.Highlight, QColor(c["accent"]))
    palette.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    palette.setColor(QPalette.PlaceholderText, QColor(c["subtle"]))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(c["disabled"]))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(c["disabled"]))
    app.setPalette(palette)


def main() -> int:
    args = parse_args()
    if args.smoke_test:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    base_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = base_dir / config_path

    app = QApplication(sys.argv)
    app.setApplicationName("CarMaker CameraRSI Recorder")
    app.setOrganizationName("CarMaker Recorder Tools")
    app.setStyle("Fusion")
    _apply_light_palette(app)
    app.setStyleSheet(stylesheet())

    window = MainWindow(base_dir, config_path)
    window.show()
    if args.smoke_test:
        QTimer.singleShot(800, app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
