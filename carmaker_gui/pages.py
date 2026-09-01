from __future__ import annotations

import os
import time
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .i18n import LanguageManager
from .widgets import CameraCard, MetricCard, PathField, StatusPill


def _page_header() -> tuple[QVBoxLayout, QLabel, QLabel]:
    layout = QVBoxLayout()
    layout.setSpacing(5)
    title_label = QLabel()
    title_label.setObjectName("PageTitle")
    title_label.setWordWrap(True)
    subtitle_label = QLabel()
    subtitle_label.setObjectName("PageSubtitle")
    subtitle_label.setWordWrap(True)
    subtitle_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    layout.addWidget(title_label)
    layout.addWidget(subtitle_label)
    return layout, title_label, subtitle_label


def _hint() -> QLabel:
    label = QLabel()
    label.setObjectName("FieldHint")
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return label


def _add_form_row(form: QFormLayout, field) -> QLabel:
    label = QLabel()
    label.setWordWrap(True)
    form.addRow(label, field)
    return label


def _configure_form(form: QFormLayout) -> None:
    form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    form.setFormAlignment(Qt.AlignTop)
    form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    form.setRowWrapPolicy(QFormLayout.WrapLongRows)
    form.setHorizontalSpacing(18)
    form.setVerticalSpacing(12)


def _localized_status(i18n: LanguageManager, state: str) -> str:
    return i18n.text(f"status.{str(state).lower()}")


class DashboardPage(QWidget):
    def __init__(self, i18n: LanguageManager, parent=None):
        super().__init__(parent)
        self.i18n = i18n
        self._last_snapshot: dict | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 24)
        layout.setSpacing(16)
        header, self.page_title, self.page_subtitle = _page_header()
        layout.addLayout(header)

        top = QGridLayout()
        top.setHorizontalSpacing(12)
        top.setVerticalSpacing(12)
        for column in range(2):
            top.setColumnStretch(column, 1)
        self.state_card = MetricCard("")
        self.connection_card = MetricCard("")
        self.camera_card = MetricCard("")
        self.session_card = MetricCard("")
        self.integrity_card = MetricCard("")
        self.disk_card = MetricCard("")
        cards = [
            self.state_card,
            self.connection_card,
            self.camera_card,
            self.session_card,
            self.integrity_card,
            self.disk_card,
        ]
        for index, card in enumerate(cards):
            top.addWidget(card, index // 2, index % 2)
        layout.addLayout(top)

        self.camera_title = QLabel()
        self.camera_title.setObjectName("SectionTitle")
        layout.addWidget(self.camera_title)
        self.preview_hint = _hint()
        layout.addWidget(self.preview_hint)

        self.camera_grid = QGridLayout()
        self.camera_grid.setHorizontalSpacing(12)
        self.camera_grid.setVerticalSpacing(12)
        self.camera_grid.setColumnStretch(0, 1)
        self.camera_grid.setColumnStretch(1, 1)
        self.camera_cards: dict[str, CameraCard] = {}
        self.placeholder = QLabel()
        self.placeholder.setObjectName("MutedLabel")
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setWordWrap(True)
        self.placeholder.setMinimumHeight(180)
        self.camera_grid.addWidget(self.placeholder, 0, 0, 1, 2)
        layout.addLayout(self.camera_grid, 1)

        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        t = self.i18n.text
        self.page_title.setText(t("dashboard.title"))
        self.page_subtitle.setText(t("dashboard.subtitle"))
        self.state_card.set_title(t("dashboard.capture_state"))
        self.connection_card.set_title(t("dashboard.rsds_connections"))
        self.camera_card.set_title(t("dashboard.active_cameras"))
        self.session_card.set_title(t("dashboard.current_scene"))
        self.integrity_card.set_title(t("dashboard.data_health"))
        self.disk_card.set_title(t("dashboard.disk_free"))
        self.camera_title.setText(t("dashboard.preview_title"))
        self.preview_hint.setText(t("dashboard.preview_hint"))
        self.placeholder.setText(t("dashboard.preview_empty"))
        for card in self.camera_cards.values():
            card.retranslate_ui()
        if self._last_snapshot is None:
            self.state_card.set_value(t("status.stopped"), t("dashboard.not_started"))
            self.connection_card.set_value("0 / 0", t("dashboard.awaiting_connection"))
            self.camera_card.set_value("0", t("dashboard.camera_rsi"))
            self.session_card.set_value("—", t("dashboard.no_session"))
            self.integrity_card.set_value(t("status.ok"), t("dashboard.no_errors"))
            self.disk_card.set_value("—", t("dashboard.awaiting_check"))
        else:
            self.update_snapshot(self._last_snapshot)

    def _ensure_camera(self, cam_id: str, name: str) -> CameraCard:
        if cam_id in self.camera_cards:
            return self.camera_cards[cam_id]
        self.placeholder.hide()
        card = CameraCard(self.i18n, cam_id, name)
        self.camera_cards[cam_id] = card
        index = len(self.camera_cards) - 1
        self.camera_grid.addWidget(card, index // 2, index % 2)
        return card

    def update_snapshot(self, snapshot: dict) -> None:
        self._last_snapshot = snapshot
        t = self.i18n.text
        state = snapshot.get("state", "STOPPED")
        uptime = float(snapshot.get("uptime_sec", 0.0))
        runtime_text = (
            t("dashboard.runtime", seconds=uptime)
            if uptime
            else t("dashboard.not_started")
        )
        self.state_card.set_value(_localized_status(self.i18n, state), runtime_text)

        connections = snapshot.get("connections", {})
        connected = sum(1 for status in connections.values() if status == "CONNECTED")
        connection_detail = " · ".join(
            f"{port}:{_localized_status(self.i18n, status)}"
            for port, status in connections.items()
        ) or t("dashboard.no_ports")
        self.connection_card.set_value(
            f"{connected} / {len(connections)}", connection_detail
        )

        cameras = snapshot.get("cameras", {})
        active_count = 0
        now = time.time()
        for cam_id, data in sorted(
            cameras.items(),
            key=lambda item: int(item[0]) if str(item[0]).isdigit() else 9999,
        ):
            active = (now - float(data.get("last_seen_epoch", 0.0))) < 2.5
            active_count += int(active)
            card = self._ensure_camera(str(cam_id), data.get("name", str(cam_id)))
            card.update_camera(str(cam_id), data, active)
        self.camera_card.set_value(
            str(active_count), t("dashboard.detected_cameras", count=len(cameras))
        )

        scene = snapshot.get("scene_id") or "—"
        root = snapshot.get("session_root") or t("dashboard.no_session")
        self.session_card.set_value(f"scene-{scene}" if scene != "—" else "—", root)

        network_drops = int(snapshot.get("network_drops", 0))
        queue_drops = sum(
            int(camera.get("video_queue_drops", 0))
            + int(camera.get("image_queue_drops", 0))
            for camera in cameras.values()
        )
        errors = snapshot.get("errors", [])
        warnings = snapshot.get("warnings", [])
        if errors:
            health = "ERROR"
        elif network_drops or queue_drops or warnings:
            health = "DEGRADED"
        else:
            health = "OK"
        self.integrity_card.set_value(
            _localized_status(self.i18n, health),
            t(
                "dashboard.health_detail",
                network=network_drops,
                queue=queue_drops,
                errors=len(errors),
            ),
        )
        disk = snapshot.get("disk_free_gb")
        self.disk_card.set_value(
            "—" if disk is None else f"{float(disk):.1f} GiB",
            t("dashboard.continuous_check"),
        )


class ConnectionPage(QWidget):
    def __init__(self, i18n: LanguageManager, parent=None):
        super().__init__(parent)
        self.i18n = i18n
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 24)
        layout.setSpacing(16)
        header, self.page_title, self.page_subtitle = _page_header()
        layout.addLayout(header)

        self.network_group = QGroupBox()
        form = QFormLayout(self.network_group)
        _configure_form(form)
        self.host = QLineEdit("localhost")
        self.host.setMinimumWidth(280)
        self.ports = QLineEdit("2210")
        self.ports.setMinimumWidth(280)
        self.test_button = QPushButton()
        self.test_status = StatusPill(i18n, "IDLE")
        test_row = QHBoxLayout()
        test_row.setSpacing(10)
        test_row.addWidget(self.test_button)
        test_row.addWidget(self.test_status)
        test_row.addStretch(1)
        self.host_label = _add_form_row(form, self.host)
        self.ports_label = _add_form_row(form, self.ports)
        self.test_label = _add_form_row(form, test_row)
        self.network_hint = _hint()
        form.addRow("", self.network_hint)
        layout.addWidget(self.network_group)

        self.capture_group = QGroupBox()
        capture_form = QFormLayout(self.capture_group)
        _configure_form(capture_form)
        self.video_enabled = QCheckBox()
        self.video_enabled.setChecked(True)
        self.video_fps = QDoubleSpinBox()
        self.video_fps.setRange(1.0, 240.0)
        self.video_fps.setDecimals(1)
        self.video_fps.setValue(30.0)
        self.video_fps.setSuffix(" FPS")
        self.images_enabled = QCheckBox()
        self.images_enabled.setChecked(True)
        self.image_hz = QDoubleSpinBox()
        self.image_hz.setRange(0.1, 240.0)
        self.image_hz.setDecimals(1)
        self.image_hz.setValue(10.0)
        self.image_hz.setSuffix(" Hz")
        self.image_format = QComboBox()
        self.image_format.addItems(["jpg", "auto", "ppm", "g8", "g16", "raw"])
        self.jpeg_quality = QSpinBox()
        self.jpeg_quality.setRange(1, 100)
        self.jpeg_quality.setValue(95)
        self.jpeg_quality.setSuffix(" %")
        self.gui_preview = QCheckBox()
        self.gui_preview.setChecked(True)
        for control in [
            self.video_fps,
            self.image_hz,
            self.image_format,
            self.jpeg_quality,
        ]:
            control.setMinimumWidth(150)
        self.video_enabled_label = _add_form_row(capture_form, self.video_enabled)
        self.video_fps_label = _add_form_row(capture_form, self.video_fps)
        self.images_enabled_label = _add_form_row(capture_form, self.images_enabled)
        self.image_hz_label = _add_form_row(capture_form, self.image_hz)
        self.image_format_label = _add_form_row(capture_form, self.image_format)
        self.jpeg_quality_label = _add_form_row(capture_form, self.jpeg_quality)
        self.gui_preview_label = _add_form_row(capture_form, self.gui_preview)
        self.sampling_hint = _hint()
        capture_form.addRow("", self.sampling_hint)
        layout.addWidget(self.capture_group)
        layout.addStretch(1)

        self.video_enabled.toggled.connect(self.video_fps.setEnabled)
        self.images_enabled.toggled.connect(self.image_hz.setEnabled)
        self.images_enabled.toggled.connect(self.image_format.setEnabled)
        self.images_enabled.toggled.connect(self.jpeg_quality.setEnabled)
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        t = self.i18n.text
        self.page_title.setText(t("connection.title"))
        self.page_subtitle.setText(t("connection.subtitle"))
        self.network_group.setTitle(t("connection.network_group"))
        self.host_label.setText(t("connection.host"))
        self.host.setPlaceholderText(t("connection.host_placeholder"))
        self.ports_label.setText(t("connection.ports"))
        self.ports.setPlaceholderText(t("connection.ports_placeholder"))
        self.test_label.setText(t("connection.connectivity"))
        self.test_button.setText(t("connection.test"))
        self.test_status.retranslate_ui()
        self.network_hint.setText(t("connection.network_hint"))
        self.capture_group.setTitle(t("connection.output_group"))
        self.video_enabled_label.setText(t("connection.video_output"))
        self.video_enabled.setText(t("connection.save_video"))
        self.video_fps_label.setText(t("connection.video_fps"))
        self.images_enabled_label.setText(t("connection.image_output"))
        self.images_enabled.setText(t("connection.save_images"))
        self.image_hz_label.setText(t("connection.image_rate"))
        self.image_format_label.setText(t("connection.image_format"))
        self.jpeg_quality_label.setText(t("connection.jpeg_quality"))
        self.gui_preview_label.setText(t("connection.gui_monitor"))
        self.gui_preview.setText(t("connection.show_preview"))
        self.sampling_hint.setText(t("connection.sampling_hint"))


class OutputPage(QWidget):
    def __init__(self, i18n: LanguageManager, base_dir: Path, parent=None):
        super().__init__(parent)
        self.i18n = i18n
        self.base_dir = base_dir
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 24)
        layout.setSpacing(16)
        header, self.page_title, self.page_subtitle = _page_header()
        layout.addLayout(header)

        self.output_group = QGroupBox()
        form = QFormLayout(self.output_group)
        _configure_form(form)
        self.save_root = PathField(i18n)
        self.save_root_label = _add_form_row(form, self.save_root)
        self.open_output = QPushButton()
        open_row = QHBoxLayout()
        open_row.addWidget(self.open_output)
        open_row.addStretch(1)
        form.addRow("", open_row)
        self.output_hint = _hint()
        form.addRow("", self.output_hint)
        layout.addWidget(self.output_group)
        layout.addStretch(1)

        self.open_output.clicked.connect(self._open_output)
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        t = self.i18n.text
        self.page_title.setText(t("output.title"))
        self.page_subtitle.setText(t("output.subtitle"))
        self.output_group.setTitle(t("output.group"))
        self.save_root_label.setText(t("output.root"))
        self.save_root.retranslate_ui()
        self.open_output.setText(t("output.open_directory"))
        self.output_hint.setText(t("output.hint"))

    def _open_output(self) -> None:
        t = self.i18n.text
        raw = self.save_root.text()
        if not raw:
            QMessageBox.information(
                self, t("output.missing_title"), t("output.missing_message")
            )
            return
        try:
            expanded = os.path.expandvars(os.path.expanduser(raw))
            path = Path(expanded)
            if not path.is_absolute():
                path = self.base_dir / path
            path.mkdir(parents=True, exist_ok=True)
            resolved = path.resolve()
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(resolved))):
                QMessageBox.warning(
                    self,
                    t("output.open_failed_title"),
                    t("output.open_failed_message", path=resolved),
                )
        except Exception as exc:
            QMessageBox.critical(self, t("output.unavailable_title"), str(exc))


class CamerasPage(QWidget):
    def __init__(self, i18n: LanguageManager, parent=None):
        super().__init__(parent)
        self.i18n = i18n
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 24)
        layout.setSpacing(16)
        header, self.page_title, self.page_subtitle = _page_header()
        layout.addLayout(header)
        self.mapping_group = QGroupBox()
        group_layout = QVBoxLayout(self.mapping_group)
        group_layout.setSpacing(12)
        self.table = QTableWidget(0, 2)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setMinimumSectionSize(140)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(300)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.add_button = QPushButton()
        self.remove_button = QPushButton()
        self.restore_button = QPushButton()
        for button in [self.add_button, self.remove_button, self.restore_button]:
            buttons.addWidget(button)
        buttons.addStretch(1)
        group_layout.addWidget(self.table, 1)
        group_layout.addLayout(buttons)
        layout.addWidget(self.mapping_group, 1)

        self.add_button.clicked.connect(self.add_row)
        self.remove_button.clicked.connect(self.remove_selected)
        self.restore_button.clicked.connect(self.restore_defaults)
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        t = self.i18n.text
        self.page_title.setText(t("cameras.title"))
        self.page_subtitle.setText(t("cameras.subtitle"))
        self.mapping_group.setTitle(t("cameras.group"))
        self.table.setHorizontalHeaderLabels(
            [t("cameras.id_header"), t("cameras.name_header")]
        )
        self.add_button.setText(t("cameras.add"))
        self.remove_button.setText(t("cameras.remove"))
        self.restore_button.setText(t("cameras.restore"))

    def set_mapping(self, mapping: dict) -> None:
        self.table.setRowCount(0)
        for cam_id, name in sorted(mapping.items(), key=lambda item: int(item[0])):
            self.add_row(str(cam_id), str(name))

    def add_row(self, cam_id: str | None = None, name: str | None = None) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        if cam_id is None:
            existing = {
                int(self.table.item(index, 0).text())
                for index in range(row)
                if self.table.item(index, 0)
                and self.table.item(index, 0).text().isdigit()
            }
            next_id = 0
            while next_id in existing:
                next_id += 1
            cam_id = str(next_id)
        self.table.setItem(row, 0, QTableWidgetItem(str(cam_id)))
        self.table.setItem(row, 1, QTableWidgetItem(name or f"CAM_{cam_id}"))
        self.table.resizeRowToContents(row)

    def remove_selected(self) -> None:
        for row in sorted(
            {index.row() for index in self.table.selectedIndexes()}, reverse=True
        ):
            self.table.removeRow(row)

    def restore_defaults(self) -> None:
        self.set_mapping(
            {
                "0": "FRONT",
                "1": "FRONT_LEFT",
                "2": "FRONT_RIGHT",
                "3": "BACK_LEFT",
                "4": "BACK_RIGHT",
                "5": "BACK",
            }
        )


class AdvancedPage(QWidget):
    def __init__(self, i18n: LanguageManager, parent=None):
        super().__init__(parent)
        self.i18n = i18n
        self.form_labels: dict[str, QLabel] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 24)
        layout.setSpacing(16)
        header, self.page_title, self.page_subtitle = _page_header()
        layout.addLayout(header)

        self.network_group = QGroupBox()
        network_form = QFormLayout(self.network_group)
        _configure_form(network_form)
        self.socket_timeout = QDoubleSpinBox()
        self.socket_timeout.setRange(0.1, 120)
        self.socket_timeout.setValue(3.0)
        self.socket_timeout.setSuffix(" s")
        self.connect_timeout = QDoubleSpinBox()
        self.connect_timeout.setRange(0.1, 120)
        self.connect_timeout.setValue(2.0)
        self.connect_timeout.setSuffix(" s")
        self.max_timeouts = QSpinBox()
        self.max_timeouts.setRange(1, 100)
        self.max_timeouts.setValue(1)
        self.reconnect_delay = QDoubleSpinBox()
        self.reconnect_delay.setRange(0, 60)
        self.reconnect_delay.setValue(0.5)
        self.reconnect_delay.setSuffix(" s")
        self.header_size = QSpinBox()
        self.header_size.setRange(1, 4096)
        self.header_size.setValue(64)
        self.header_size.setSuffix(" bytes")
        self.max_payload_mb = QSpinBox()
        self.max_payload_mb.setRange(1, 2048)
        self.max_payload_mb.setValue(256)
        self.max_payload_mb.setSuffix(" MiB")
        self._add_advanced_row(
            network_form, "advanced.socket_timeout", self.socket_timeout
        )
        self._add_advanced_row(
            network_form, "advanced.connect_timeout", self.connect_timeout
        )
        self._add_advanced_row(
            network_form, "advanced.timeout_threshold", self.max_timeouts
        )
        self._add_advanced_row(
            network_form, "advanced.reconnect_delay", self.reconnect_delay
        )
        self._add_advanced_row(network_form, "advanced.header_size", self.header_size)
        self._add_advanced_row(
            network_form, "advanced.max_payload", self.max_payload_mb
        )

        self.reliability_group = QGroupBox()
        reliability_form = QFormLayout(self.reliability_group)
        _configure_form(reliability_form)
        self.message_capacity = QSpinBox()
        self.message_capacity.setRange(2, 100000)
        self.message_capacity.setValue(512)
        self.frame_capacity = QSpinBox()
        self.frame_capacity.setRange(2, 100000)
        self.frame_capacity.setValue(180)
        self.image_capacity = QSpinBox()
        self.image_capacity.setRange(2, 100000)
        self.image_capacity.setValue(512)
        self.writer_failure_policy = QComboBox()
        self.writer_failure_policy.addItem("", "stop")
        self.writer_failure_policy.addItem("", "degraded")
        self.min_free_disk_gb = QDoubleSpinBox()
        self.min_free_disk_gb.setRange(0, 10000)
        self.min_free_disk_gb.setValue(2.0)
        self.min_free_disk_gb.setSuffix(" GiB")
        self.disk_check_interval = QDoubleSpinBox()
        self.disk_check_interval.setRange(0.5, 300)
        self.disk_check_interval.setValue(5.0)
        self.disk_check_interval.setSuffix(" s")
        self.sim_reset_threshold = QDoubleSpinBox()
        self.sim_reset_threshold.setRange(0.01, 60)
        self.sim_reset_threshold.setDecimals(2)
        self.sim_reset_threshold.setValue(0.5)
        self.sim_reset_threshold.setSuffix(" s")
        self.mark_degraded_on_drop = QCheckBox()
        self.mark_degraded_on_drop.setChecked(True)
        self._add_advanced_row(
            reliability_form, "advanced.message_buffer", self.message_capacity
        )
        self._add_advanced_row(
            reliability_form, "advanced.video_buffer", self.frame_capacity
        )
        self._add_advanced_row(
            reliability_form, "advanced.image_buffer", self.image_capacity
        )
        self._add_advanced_row(
            reliability_form, "advanced.writer_policy", self.writer_failure_policy
        )
        self._add_advanced_row(
            reliability_form, "advanced.min_disk", self.min_free_disk_gb
        )
        self._add_advanced_row(
            reliability_form, "advanced.disk_interval", self.disk_check_interval
        )
        self._add_advanced_row(
            reliability_form, "advanced.sim_reset", self.sim_reset_threshold
        )
        self._add_advanced_row(
            reliability_form, "advanced.drop_state", self.mark_degraded_on_drop
        )

        self.media_group = QGroupBox()
        media_form = QFormLayout(self.media_group)
        _configure_form(media_form)
        self.video_backend = QComboBox()
        self.video_backend.addItem("", "auto")
        self.video_backend.addItem("", "opencv")
        self.video_backend.addItem("", "nvenc")
        self.video_backend.addItem("", "qsv")
        self.video_backend.addItem("", "amf")
        self.video_codec = QComboBox()
        self.video_codec.addItem("H.264", "h264")
        self.video_codec.addItem("H.265 / HEVC", "hevc")
        self.video_codec.addItem("AV1", "av1")
        self.video_bitrate = QDoubleSpinBox()
        self.video_bitrate.setRange(0.1, 1000.0)
        self.video_bitrate.setDecimals(1)
        self.video_bitrate.setValue(12.0)
        self.video_bitrate.setSuffix(" Mbps")
        self.allow_cpu_fallback = QCheckBox()
        self.allow_cpu_fallback.setChecked(True)
        self.ffmpeg_path = QLineEdit("ffmpeg")
        self.fourcc = QLineEdit("XVID")
        self.fourcc.setMaxLength(4)
        self.video_extension = QLineEdit("avi")
        self.max_gap_fill_frames = QSpinBox()
        self.max_gap_fill_frames.setRange(0, 100000)
        self.max_gap_fill_frames.setValue(60)
        self.preview_hz = QDoubleSpinBox()
        self.preview_hz.setRange(0.2, 15.0)
        self.preview_hz.setDecimals(1)
        self.preview_hz.setValue(2.0)
        self.preview_hz.setSuffix(" Hz")
        self._add_advanced_row(
            media_form, "advanced.video_backend", self.video_backend
        )
        self._add_advanced_row(media_form, "advanced.video_codec", self.video_codec)
        self._add_advanced_row(
            media_form, "advanced.video_bitrate", self.video_bitrate
        )
        self._add_advanced_row(media_form, "advanced.ffmpeg_path", self.ffmpeg_path)
        self._add_advanced_row(
            media_form, "advanced.cpu_fallback", self.allow_cpu_fallback
        )
        self._add_advanced_row(media_form, "advanced.fourcc", self.fourcc)
        self._add_advanced_row(
            media_form, "advanced.video_extension", self.video_extension
        )
        self._add_advanced_row(
            media_form, "advanced.max_gap_fill", self.max_gap_fill_frames
        )
        self._add_advanced_row(media_form, "advanced.preview_rate", self.preview_hz)
        self.media_hint = _hint()
        media_form.addRow("", self.media_hint)
        self.video_backend.currentIndexChanged.connect(
            lambda _index: self._sync_video_backend_fields()
        )
        self._sync_video_backend_fields()

        self.logs_group = QGroupBox()
        logs_form = QFormLayout(self.logs_group)
        _configure_form(logs_form)
        self.log_level = QComboBox()
        self.log_level.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self.log_level.setCurrentText("INFO")
        self.log_max_mb = QSpinBox()
        self.log_max_mb.setRange(1, 1024)
        self.log_max_mb.setValue(10)
        self.log_max_mb.setSuffix(" MB")
        self.log_backups = QSpinBox()
        self.log_backups.setRange(1, 50)
        self.log_backups.setValue(5)
        self._add_advanced_row(logs_form, "advanced.log_level", self.log_level)
        self._add_advanced_row(logs_form, "advanced.log_size", self.log_max_mb)
        self._add_advanced_row(logs_form, "advanced.log_backups", self.log_backups)

        for group in [
            self.network_group,
            self.reliability_group,
            self.media_group,
            self.logs_group,
        ]:
            layout.addWidget(group)
        layout.addStretch(1)
        self.retranslate_ui()

    def _add_advanced_row(self, form: QFormLayout, key: str, field) -> None:
        self.form_labels[key] = _add_form_row(form, field)

    def _sync_video_backend_fields(self) -> None:
        hardware_enabled = self.video_backend.currentData() != "opencv"
        for field in (
            self.video_codec,
            self.video_bitrate,
            self.ffmpeg_path,
            self.allow_cpu_fallback,
        ):
            field.setEnabled(hardware_enabled)

    def retranslate_ui(self) -> None:
        t = self.i18n.text
        self.page_title.setText(t("advanced.title"))
        self.page_subtitle.setText(t("advanced.subtitle"))
        self.network_group.setTitle(t("advanced.network_group"))
        self.reliability_group.setTitle(t("advanced.reliability_group"))
        self.media_group.setTitle(t("advanced.media_group"))
        self.logs_group.setTitle(t("advanced.logs_group"))
        for key, label in self.form_labels.items():
            label.setText(t(key))
        self.mark_degraded_on_drop.setText(t("advanced.mark_degraded"))
        self.media_hint.setText(t("advanced.media_hint"))
        current_backend = self.video_backend.currentData()
        self.video_backend.setItemText(0, t("advanced.backend_auto"))
        self.video_backend.setItemText(1, t("advanced.backend_opencv"))
        self.video_backend.setItemText(2, "NVIDIA NVENC")
        self.video_backend.setItemText(3, "Intel QSV")
        self.video_backend.setItemText(4, "AMD AMF")
        backend_index = self.video_backend.findData(current_backend)
        if backend_index >= 0:
            self.video_backend.setCurrentIndex(backend_index)
        self.allow_cpu_fallback.setText(t("advanced.allow_cpu_fallback"))
        current_policy = self.writer_failure_policy.currentData()
        self.writer_failure_policy.setItemText(0, t("advanced.policy_stop"))
        self.writer_failure_policy.setItemText(1, t("advanced.policy_degraded"))
        policy_index = self.writer_failure_policy.findData(current_policy)
        if policy_index >= 0:
            self.writer_failure_policy.setCurrentIndex(policy_index)


class LogsPage(QWidget):
    def __init__(self, i18n: LanguageManager, parent=None):
        super().__init__(parent)
        self.i18n = i18n
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 24)
        layout.setSpacing(12)
        header, self.page_title, self.page_subtitle = _page_header()
        layout.addLayout(header)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.clear_button = QPushButton()
        self.export_button = QPushButton()
        self.auto_scroll = QCheckBox()
        self.auto_scroll.setChecked(True)
        toolbar.addWidget(self.clear_button)
        toolbar.addWidget(self.export_button)
        toolbar.addWidget(self.auto_scroll)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setMaximumBlockCount(10000)
        self.text.setStyleSheet(
            'font-family: "Cascadia Mono", "Consolas", monospace; font-size: 13px; line-height: 1.35;'
        )
        layout.addWidget(self.text, 1)
        self.clear_button.clicked.connect(self.text.clear)
        self.export_button.clicked.connect(self.export_log)
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        t = self.i18n.text
        self.page_title.setText(t("logs.title"))
        self.page_subtitle.setText(t("logs.subtitle"))
        self.clear_button.setText(t("logs.clear"))
        self.export_button.setText(t("logs.export"))
        self.auto_scroll.setText(t("logs.auto_scroll"))

    def append(self, message: str) -> None:
        self.text.appendPlainText(message)
        if self.auto_scroll.isChecked():
            bar = self.text.verticalScrollBar()
            bar.setValue(bar.maximum())

    def export_log(self) -> None:
        t = self.i18n.text
        path, _ = QFileDialog.getSaveFileName(
            self,
            t("logs.export_title"),
            "carmaker_recorder.log",
            t("logs.export_filter"),
        )
        if not path:
            return
        try:
            Path(path).write_text(self.text.toPlainText(), encoding="utf-8")
        except Exception as exc:
            QMessageBox.critical(self, t("logs.export_failed"), str(exc))
