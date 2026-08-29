from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .theme import COLORS

if TYPE_CHECKING:
    from .i18n import LanguageManager


STATUS_KEYS = {
    "CONNECTED": "status.connected",
    "RECORDING": "status.recording",
    "RUNNING": "status.running",
    "WAITING": "status.waiting",
    "RETRYING": "status.retrying",
    "RECONNECTING": "status.reconnecting",
    "CONNECTING": "status.connecting",
    "DEGRADED": "status.degraded",
    "STARTING": "status.starting",
    "STOPPING": "status.stopping",
    "ERROR": "status.error",
    "DISCONNECTED": "status.disconnected",
    "STOPPED": "status.stopped",
    "IDLE": "status.idle",
    "OK": "status.ok",
}


class StatusPill(QLabel):
    def __init__(
        self,
        i18n: LanguageManager,
        text: str = "IDLE",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.i18n = i18n
        self._state = "IDLE"
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumWidth(92)
        self.setMinimumHeight(28)
        self.set_state(text)

    def set_state(self, state: str) -> None:
        state = str(state).upper()
        self._state = state
        # Text + border + background are all changed so state is never color-only.
        mapping = {
            "CONNECTED": ("#14532D", "#DCFCE7", "#86EFAC"),
            "RECORDING": ("#14532D", "#DCFCE7", "#86EFAC"),
            "RUNNING": ("#14532D", "#DCFCE7", "#86EFAC"),
            "WAITING": ("#7C2D12", "#FFEDD5", "#FDBA74"),
            "RETRYING": ("#7C2D12", "#FFEDD5", "#FDBA74"),
            "RECONNECTING": ("#7C2D12", "#FFEDD5", "#FDBA74"),
            "CONNECTING": ("#1E3A8A", "#DBEAFE", "#93C5FD"),
            "DEGRADED": ("#7C2D12", "#FFEDD5", "#FDBA74"),
            "STARTING": ("#1E3A8A", "#DBEAFE", "#93C5FD"),
            "STOPPING": ("#7C2D12", "#FFEDD5", "#FDBA74"),
            "ERROR": ("#991B1B", "#FEE2E2", "#FCA5A5"),
            "DISCONNECTED": ("#991B1B", "#FEE2E2", "#FCA5A5"),
            "STOPPED": ("#334155", "#E2E8F0", "#CBD5E1"),
            "IDLE": ("#334155", "#E2E8F0", "#CBD5E1"),
        }
        fg, bg, border = mapping.get(state, ("#334155", "#E2E8F0", "#CBD5E1"))
        display_state = self.i18n.text(STATUS_KEYS.get(state, "status.idle"))
        self.setText(display_state)
        self.setToolTip(self.i18n.text("status.tooltip", state=display_state))
        self.setStyleSheet(
            f"QLabel {{ color: {fg}; background: {bg}; border: 1px solid {border}; "
            "border-radius: 12px; padding: 4px 10px; font-weight: 700; font-size: 12px; }}"
        )

    def retranslate_ui(self) -> None:
        self.set_state(self._state)


class MetricCard(QFrame):
    def __init__(self, title: str, value: str = "—", subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setMinimumHeight(116)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("MutedLabel")
        self.title_label.setWordWrap(True)
        self.value_label = QLabel(value)
        self.value_label.setStyleSheet("font-size: 22px; font-weight: 700;")
        self.value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.value_label.setWordWrap(True)
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("FieldHint")
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.subtitle_label)

    def set_value(self, value: str, subtitle: str | None = None) -> None:
        self.value_label.setText(str(value))
        if subtitle is not None:
            self.subtitle_label.setText(str(subtitle))
            self.subtitle_label.setToolTip(str(subtitle))

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)


class PathField(QWidget):
    def __init__(self, i18n: LanguageManager, parent=None):
        super().__init__(parent)
        self.i18n = i18n
        self.dialog_title = ""
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.edit = QLineEdit()
        self.edit.setMinimumWidth(260)
        self.browse = QPushButton()
        self.browse.setMinimumWidth(84)
        self.browse.clicked.connect(self._browse)
        layout.addWidget(self.edit, 1)
        layout.addWidget(self.browse)

    def retranslate_ui(self) -> None:
        self.dialog_title = self.i18n.text("output.select_directory")
        self.edit.setPlaceholderText(self.i18n.text("output.placeholder"))
        self.browse.setText(self.i18n.text("path.browse"))
        self.browse.setToolTip(self.i18n.text("path.browse_tooltip"))

    def _browse(self) -> None:
        start = self.edit.text().strip()
        if not start or "{" in start:
            start = str(Path.home())
        selected = QFileDialog.getExistingDirectory(self, self.dialog_title, start)
        if selected:
            self.edit.setText(selected)

    def text(self) -> str:
        return self.edit.text().strip()

    def setText(self, text: str) -> None:
        self.edit.setText(str(text))
        self.edit.setToolTip(str(text))

    def setEnabled(self, enabled: bool) -> None:  # noqa: N802 - Qt API style
        super().setEnabled(enabled)
        self.edit.setEnabled(enabled)
        self.browse.setEnabled(enabled)


class CameraCard(QFrame):
    def __init__(self, i18n: LanguageManager, cam_id: str, name: str, parent=None):
        super().__init__(parent)
        self.i18n = i18n
        self._cam_id = str(cam_id)
        self._last_data: dict = {"name": name}
        self._active = False
        self.setObjectName("Card")
        self.setMinimumSize(280, 260)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(9)

        header = QHBoxLayout()
        header.setSpacing(10)
        self.title = QLabel(f"CAM {cam_id} · {name}")
        self.title.setObjectName("SectionTitle")
        self.title.setWordWrap(True)
        self.title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.status = StatusPill(i18n, "IDLE")
        header.addWidget(self.title, 1)
        header.addWidget(self.status, 0, Qt.AlignTop)

        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(150)
        self.preview.setWordWrap(True)
        self.preview.setStyleSheet(
            f"background: #EEF2F6; border: 1px solid {COLORS['border_soft']}; "
            f"border-radius: 5px; color: {COLORS['muted']}; padding: 8px;"
        )
        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.meta = QLabel()
        self.meta.setObjectName("FieldHint")
        self.meta.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.meta.setWordWrap(True)
        self.counts = QLabel()
        self.counts.setObjectName("FieldHint")
        self.counts.setWordWrap(True)

        layout.addLayout(header)
        layout.addWidget(self.preview, 1)
        layout.addWidget(self.meta)
        layout.addWidget(self.counts)
        self.retranslate_ui()

    def update_camera(self, cam_id: str, data: dict, active: bool) -> None:
        self._cam_id = str(cam_id)
        self._last_data = dict(data)
        self._active = bool(active)
        title = f"CAM {cam_id} · {data.get('name', cam_id)}"
        self.title.setText(title)
        self.title.setToolTip(title)
        self.status.set_state("CONNECTED" if active else "IDLE")
        frames = int(data.get("frames_received", 0))
        w, h = int(data.get("width", 0)), int(data.get("height", 0))
        fmt = data.get("format", "—")
        sim_time = float(data.get("sim_time", 0.0))
        resolution = f"{w}×{h}" if w and h else "—"
        avg_fps = float(data.get("average_rx_fps", 0.0))
        avg_mib = float(data.get("average_rx_mib_s", 0.0))
        if frames:
            meta = self.i18n.text(
                "camera.meta",
                frames=frames,
                resolution=resolution,
                format=fmt,
                sim_time=sim_time,
                fps=avg_fps,
                mib=avg_mib,
            )
        else:
            meta = self.i18n.text("camera.initial_meta")
        self.meta.setText(meta)
        self.meta.setToolTip(meta)
        if frames:
            counts = self.i18n.text(
                "camera.counts",
                video=int(data.get("video_frames_written", 0)),
                images=int(data.get("images_written", 0)),
                video_drops=int(data.get("video_queue_drops", 0)),
                image_drops=int(data.get("image_queue_drops", 0)),
                video_writer=data.get("video_writer", "IDLE"),
                image_writer=data.get("image_writer", "IDLE"),
            )
        else:
            counts = self.i18n.text("camera.initial_counts")
        self.counts.setText(counts)
        jpeg = data.get("preview_jpeg")
        if jpeg:
            pix = QPixmap()
            if pix.loadFromData(jpeg, "JPG"):
                self.preview.setPixmap(
                    pix.scaled(
                        self.preview.size(),
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
                    )
                )
                self.preview.setText("")
        else:
            self.preview.clear()
            preview_key = (
                "camera.waiting" if frames == 0 else "camera.preview_unavailable"
            )
            self.preview.setText(self.i18n.text(preview_key))

    def retranslate_ui(self) -> None:
        self.status.retranslate_ui()
        self.update_camera(self._cam_id, self._last_data, self._active)

    def resizeEvent(self, event):  # noqa: N802
        # The next runtime refresh supplies the source preview again, avoiding
        # repeated resampling of an already-scaled pixmap.
        super().resizeEvent(event)
