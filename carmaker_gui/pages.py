from __future__ import annotations

import os
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
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .widgets import CameraCard, MetricCard, PathField, StatusPill


def _page_header(title: str, subtitle: str) -> QVBoxLayout:
    layout = QVBoxLayout()
    layout.setSpacing(5)
    title_label = QLabel(title)
    title_label.setObjectName("PageTitle")
    title_label.setWordWrap(True)
    subtitle_label = QLabel(subtitle)
    subtitle_label.setObjectName("PageSubtitle")
    subtitle_label.setWordWrap(True)
    subtitle_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    layout.addWidget(title_label)
    layout.addWidget(subtitle_label)
    return layout


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("FieldHint")
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return label


def _configure_form(form: QFormLayout) -> None:
    form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    form.setFormAlignment(Qt.AlignTop)
    form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    form.setRowWrapPolicy(QFormLayout.WrapLongRows)
    form.setHorizontalSpacing(18)
    form.setVerticalSpacing(12)


class DashboardPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 24)
        layout.setSpacing(16)
        layout.addLayout(_page_header("采集监控", "实时查看连接、数据完整性、磁盘余量与多路 CameraRSI 状态。"))

        top = QGridLayout()
        top.setHorizontalSpacing(12)
        top.setVerticalSpacing(12)
        for col in range(2):
            top.setColumnStretch(col, 1)
        self.state_card = MetricCard("采集状态", "STOPPED", "尚未启动")
        self.connection_card = MetricCard("RSDS 连接", "0 / 0", "等待连接")
        self.camera_card = MetricCard("活动摄像头", "0", "CameraRSI")
        self.session_card = MetricCard("当前 Scene", "—", "暂无 Session")
        self.integrity_card = MetricCard("数据健康", "OK", "无丢帧/组件错误")
        self.disk_card = MetricCard("磁盘可用", "—", "等待检测")
        cards = [
            self.state_card, self.connection_card,
            self.camera_card, self.session_card,
            self.integrity_card, self.disk_card,
        ]
        for i, card in enumerate(cards):
            top.addWidget(card, i // 2, i % 2)
        layout.addLayout(top)

        camera_title = QLabel("CameraRSI 实时预览")
        camera_title.setObjectName("SectionTitle")
        layout.addWidget(camera_title)
        self.preview_hint = _hint("GUI 预览为独立低优先级编码线程，仅用于监控，不参与视频/图片采集时序。")
        layout.addWidget(self.preview_hint)

        self.camera_grid = QGridLayout()
        self.camera_grid.setHorizontalSpacing(12)
        self.camera_grid.setVerticalSpacing(12)
        self.camera_grid.setColumnStretch(0, 1)
        self.camera_grid.setColumnStretch(1, 1)
        self.camera_cards: dict[str, CameraCard] = {}
        self.placeholder = QLabel("启动采集后，检测到的 CameraRSI 通道会自动显示在这里。")
        self.placeholder.setObjectName("MutedLabel")
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setWordWrap(True)
        self.placeholder.setMinimumHeight(180)
        self.camera_grid.addWidget(self.placeholder, 0, 0, 1, 2)
        layout.addLayout(self.camera_grid, 1)

    def _ensure_camera(self, cam_id: str, name: str) -> CameraCard:
        if cam_id in self.camera_cards:
            return self.camera_cards[cam_id]
        self.placeholder.hide()
        card = CameraCard(cam_id, name)
        self.camera_cards[cam_id] = card
        index = len(self.camera_cards) - 1
        self.camera_grid.addWidget(card, index // 2, index % 2)
        return card

    def update_snapshot(self, snapshot: dict) -> None:
        import time

        state = snapshot.get("state", "STOPPED")
        uptime = float(snapshot.get("uptime_sec", 0.0))
        self.state_card.set_value(state, f"运行 {uptime:.1f} 秒" if uptime else "尚未启动")

        connections = snapshot.get("connections", {})
        connected = sum(1 for status in connections.values() if status == "CONNECTED")
        self.connection_card.set_value(
            f"{connected} / {len(connections)}",
            " · ".join(f"{p}:{s}" for p, s in connections.items()) or "无端口",
        )

        cameras = snapshot.get("cameras", {})
        active_count = 0
        now = time.time()
        for cam_id, data in sorted(cameras.items(), key=lambda x: int(x[0]) if str(x[0]).isdigit() else 9999):
            active = (now - float(data.get("last_seen_epoch", 0.0))) < 2.5
            active_count += int(active)
            self._ensure_camera(str(cam_id), data.get("name", str(cam_id))).update_camera(str(cam_id), data, active)
        self.camera_card.set_value(str(active_count), f"已识别 {len(cameras)} 路")

        scene = snapshot.get("scene_id") or "—"
        root = snapshot.get("session_root") or "暂无 Session"
        self.session_card.set_value(f"scene-{scene}" if scene != "—" else "—", root)

        network_drops = int(snapshot.get("network_drops", 0))
        queue_drops = sum(
            int(cam.get("video_queue_drops", 0)) + int(cam.get("image_queue_drops", 0))
            for cam in cameras.values()
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
            health,
            f"Network drop {network_drops} · Queue drop {queue_drops} · Error {len(errors)}",
        )
        disk = snapshot.get("disk_free_gb")
        self.disk_card.set_value("—" if disk is None else f"{float(disk):.1f} GiB", "运行期持续检测")


class ConnectionPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 24)
        layout.setSpacing(16)
        layout.addLayout(_page_header("连接与采集", "默认即可连接本机 CarMaker；多端口之间相互独立重连。"))

        network = QGroupBox("CarMaker / MovieNX 连接")
        form = QFormLayout(network)
        _configure_form(form)
        self.host = QLineEdit("localhost")
        self.host.setPlaceholderText("localhost 或 192.168.1.100")
        self.host.setMinimumWidth(280)
        self.ports = QLineEdit("2210")
        self.ports.setPlaceholderText("2210 或 2210,2211,2212")
        self.ports.setMinimumWidth(280)
        self.test_button = QPushButton("测试 TCP 连接")
        self.test_status = StatusPill("IDLE")
        test_row = QHBoxLayout()
        test_row.setSpacing(10)
        test_row.addWidget(self.test_button)
        test_row.addWidget(self.test_status)
        test_row.addStretch(1)
        form.addRow("主机 / IP", self.host)
        form.addRow("RSDS 端口", self.ports)
        form.addRow("连通性", test_row)
        form.addRow("", _hint("每个端口独立建立 TCP/RSDS 连接；单路掉线不会主动中断其他正常通道。"))
        layout.addWidget(network)

        capture = QGroupBox("输出策略")
        cform = QFormLayout(capture)
        _configure_form(cform)
        self.video_enabled = QCheckBox("保存视频")
        self.video_enabled.setChecked(True)
        self.video_fps = QDoubleSpinBox(); self.video_fps.setRange(1.0, 240.0); self.video_fps.setDecimals(1); self.video_fps.setValue(30.0); self.video_fps.setSuffix(" FPS")
        self.images_enabled = QCheckBox("保存图片")
        self.images_enabled.setChecked(True)
        self.image_hz = QDoubleSpinBox(); self.image_hz.setRange(0.1, 240.0); self.image_hz.setDecimals(1); self.image_hz.setValue(10.0); self.image_hz.setSuffix(" Hz")
        self.image_format = QComboBox(); self.image_format.addItems(["jpg", "auto", "ppm", "g8", "g16", "raw"])
        self.jpeg_quality = QSpinBox(); self.jpeg_quality.setRange(1, 100); self.jpeg_quality.setValue(95); self.jpeg_quality.setSuffix(" %")
        self.gui_preview = QCheckBox("在 GUI 中显示低频实时预览"); self.gui_preview.setChecked(True)
        for control in [self.video_fps, self.image_hz, self.image_format, self.jpeg_quality]:
            control.setMinimumWidth(150)
        cform.addRow("视频输出", self.video_enabled)
        cform.addRow("视频帧率", self.video_fps)
        cform.addRow("图片输出", self.images_enabled)
        cform.addRow("图片采样率", self.image_hz)
        cform.addRow("图片格式", self.image_format)
        cform.addRow("JPG 质量", self.jpeg_quality)
        cform.addRow("GUI 监控", self.gui_preview)
        cform.addRow("", _hint("图片采样使用仿真时间周期调度，不再使用浮点乘法截断索引。"))
        layout.addWidget(capture)
        layout.addStretch(1)

        self.video_enabled.toggled.connect(self.video_fps.setEnabled)
        self.images_enabled.toggled.connect(self.image_hz.setEnabled)
        self.images_enabled.toggled.connect(self.image_format.setEnabled)
        self.images_enabled.toggled.connect(self.jpeg_quality.setEnabled)


class OutputPage(QWidget):
    def __init__(self, base_dir: Path, parent=None):
        super().__init__(parent)
        self.base_dir = base_dir
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 24)
        layout.setSpacing(16)
        layout.addLayout(_page_header("采集输出", "每次有效采集都会生成独立 Session 和 Manifest。"))

        out = QGroupBox("采集输出")
        form = QFormLayout(out)
        _configure_form(form)
        self.save_root = PathField("例如 D:/CarMakerCapture 或 carmaker_videos", "选择采集输出目录")
        self.open_output = QPushButton("打开当前输出目录")
        open_row = QHBoxLayout(); open_row.addWidget(self.open_output); open_row.addStretch(1)
        form.addRow("输出根目录", self.save_root)
        form.addRow("", open_row)
        form.addRow("", _hint("运行日志位于输出根目录 logs/；每次有效采集生成独立 Session 和 session_manifest.json。"))
        layout.addWidget(out)

        layout.addStretch(1)

        self.open_output.clicked.connect(self._open_output)

    def _open_output(self) -> None:
        raw = self.save_root.text()
        if not raw:
            QMessageBox.information(self, "输出目录", "请先填写输出根目录。")
            return
        try:
            expanded = os.path.expandvars(os.path.expanduser(raw))
            p = Path(expanded)
            if not p.is_absolute():
                p = self.base_dir / p
            p.mkdir(parents=True, exist_ok=True)
            resolved = p.resolve()
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(resolved))):
                QMessageBox.warning(self, "无法打开目录", f"系统未能打开：\n{resolved}")
        except Exception as exc:
            QMessageBox.critical(self, "输出目录不可用", str(exc))


class CamerasPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 24)
        layout.setSpacing(16)
        layout.addLayout(_page_header("CameraRSI 映射", "CameraRSI ID 与输出名称必须唯一，非法 Windows 文件名会在启动前拒绝。"))
        group = QGroupBox("Camera ID → 名称")
        gl = QVBoxLayout(group); gl.setSpacing(12)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["CameraRSI ID", "显示 / 输出名称"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setMinimumSectionSize(140)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(300)
        buttons = QHBoxLayout(); buttons.setSpacing(8)
        self.add_button = QPushButton("新增映射")
        self.remove_button = QPushButton("删除选中")
        self.restore_button = QPushButton("恢复六路默认值")
        for b in [self.add_button, self.remove_button, self.restore_button]: buttons.addWidget(b)
        buttons.addStretch(1)
        gl.addWidget(self.table, 1); gl.addLayout(buttons)
        layout.addWidget(group, 1)
        self.add_button.clicked.connect(self.add_row)
        self.remove_button.clicked.connect(self.remove_selected)
        self.restore_button.clicked.connect(self.restore_defaults)

    def set_mapping(self, mapping: dict) -> None:
        self.table.setRowCount(0)
        for cam_id, name in sorted(mapping.items(), key=lambda x: int(x[0])):
            self.add_row(str(cam_id), str(name))

    def add_row(self, cam_id: str | None = None, name: str | None = None) -> None:
        row = self.table.rowCount(); self.table.insertRow(row)
        if cam_id is None:
            existing = {int(self.table.item(r, 0).text()) for r in range(row) if self.table.item(r, 0) and self.table.item(r, 0).text().isdigit()}
            next_id = 0
            while next_id in existing: next_id += 1
            cam_id = str(next_id)
        self.table.setItem(row, 0, QTableWidgetItem(str(cam_id)))
        self.table.setItem(row, 1, QTableWidgetItem(name or f"CAM_{cam_id}"))
        self.table.resizeRowToContents(row)

    def remove_selected(self) -> None:
        for row in sorted({idx.row() for idx in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(row)

    def restore_defaults(self) -> None:
        self.set_mapping({"0": "FRONT", "1": "FRONT_LEFT", "2": "FRONT_RIGHT", "3": "BACK_LEFT", "4": "BACK_RIGHT", "5": "BACK"})


class AdvancedPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 24)
        layout.setSpacing(16)
        layout.addLayout(_page_header("高级设置", "这些参数控制网络、缓冲、媒体写入和运行日志。"))

        network = QGroupBox("RSDS / 网络")
        nf = QFormLayout(network); _configure_form(nf)
        self.socket_timeout = QDoubleSpinBox(); self.socket_timeout.setRange(0.1, 120); self.socket_timeout.setValue(3.0); self.socket_timeout.setSuffix(" s")
        self.connect_timeout = QDoubleSpinBox(); self.connect_timeout.setRange(0.1, 120); self.connect_timeout.setValue(2.0); self.connect_timeout.setSuffix(" s")
        self.max_timeouts = QSpinBox(); self.max_timeouts.setRange(1, 100); self.max_timeouts.setValue(1)
        self.reconnect_delay = QDoubleSpinBox(); self.reconnect_delay.setRange(0, 60); self.reconnect_delay.setValue(0.5); self.reconnect_delay.setSuffix(" s")
        self.header_size = QSpinBox(); self.header_size.setRange(1, 4096); self.header_size.setValue(64); self.header_size.setSuffix(" bytes")
        self.max_payload_mb = QSpinBox(); self.max_payload_mb.setRange(1, 2048); self.max_payload_mb.setValue(256); self.max_payload_mb.setSuffix(" MiB")
        nf.addRow("Socket 超时", self.socket_timeout); nf.addRow("连接超时", self.connect_timeout); nf.addRow("超时后重连阈值", self.max_timeouts); nf.addRow("重连间隔", self.reconnect_delay); nf.addRow("RSDS Header", self.header_size); nf.addRow("单消息最大 Payload", self.max_payload_mb)

        reliability = QGroupBox("可靠性 / 缓冲")
        rf = QFormLayout(reliability); _configure_form(rf)
        self.message_capacity = QSpinBox(); self.message_capacity.setRange(2, 100000); self.message_capacity.setValue(512)
        self.frame_capacity = QSpinBox(); self.frame_capacity.setRange(2, 100000); self.frame_capacity.setValue(180)
        self.image_capacity = QSpinBox(); self.image_capacity.setRange(2, 100000); self.image_capacity.setValue(512)
        self.writer_failure_policy = QComboBox(); self.writer_failure_policy.addItems(["stop", "degraded"])
        self.min_free_disk_gb = QDoubleSpinBox(); self.min_free_disk_gb.setRange(0, 10000); self.min_free_disk_gb.setValue(2.0); self.min_free_disk_gb.setSuffix(" GiB")
        self.disk_check_interval = QDoubleSpinBox(); self.disk_check_interval.setRange(0.5, 300); self.disk_check_interval.setValue(5.0); self.disk_check_interval.setSuffix(" s")
        self.sim_reset_threshold = QDoubleSpinBox(); self.sim_reset_threshold.setRange(0.01, 60); self.sim_reset_threshold.setDecimals(2); self.sim_reset_threshold.setValue(0.5); self.sim_reset_threshold.setSuffix(" s")
        self.mark_degraded_on_drop = QCheckBox("任意 RingBuffer 丢弃数据时标记 DEGRADED"); self.mark_degraded_on_drop.setChecked(True)
        rf.addRow("消息环形缓冲", self.message_capacity); rf.addRow("每路视频帧缓冲", self.frame_capacity); rf.addRow("每路图片任务缓冲", self.image_capacity)
        rf.addRow("Writer 失败策略", self.writer_failure_policy); rf.addRow("最小磁盘余量", self.min_free_disk_gb); rf.addRow("磁盘检查间隔", self.disk_check_interval); rf.addRow("SimTime 回退阈值", self.sim_reset_threshold); rf.addRow("丢帧状态", self.mark_degraded_on_drop)

        media = QGroupBox("视频 / 图像")
        mf = QFormLayout(media); _configure_form(mf)
        self.fourcc = QLineEdit("XVID"); self.fourcc.setMaxLength(4)
        self.video_extension = QLineEdit("avi")
        self.max_gap_fill_frames = QSpinBox(); self.max_gap_fill_frames.setRange(0, 100000); self.max_gap_fill_frames.setValue(60)
        self.preview_hz = QDoubleSpinBox(); self.preview_hz.setRange(0.2, 15.0); self.preview_hz.setDecimals(1); self.preview_hz.setValue(2.0); self.preview_hz.setSuffix(" Hz")
        mf.addRow("Video FOURCC", self.fourcc); mf.addRow("视频扩展名", self.video_extension); mf.addRow("最大补帧数", self.max_gap_fill_frames); mf.addRow("GUI 预览频率", self.preview_hz)
        mf.addRow("", _hint("分辨率变化或视频时间大跳变会自动切换到新的 partXXX 视频段，避免无上限补帧。"))

        logs = QGroupBox("持久日志")
        lf = QFormLayout(logs); _configure_form(lf)
        self.log_level = QComboBox(); self.log_level.addItems(["DEBUG", "INFO", "WARNING", "ERROR"]); self.log_level.setCurrentText("INFO")
        self.log_max_mb = QSpinBox(); self.log_max_mb.setRange(1, 1024); self.log_max_mb.setValue(10); self.log_max_mb.setSuffix(" MB")
        self.log_backups = QSpinBox(); self.log_backups.setRange(1, 50); self.log_backups.setValue(5)
        lf.addRow("日志级别", self.log_level); lf.addRow("单文件上限", self.log_max_mb); lf.addRow("保留滚动文件", self.log_backups)

        for group in [network, reliability, media, logs]:
            layout.addWidget(group)
        layout.addStretch(1)


class LogsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 24)
        layout.setSpacing(12)
        layout.addLayout(_page_header("运行日志", "GUI 日志用于查看；完整运行日志会自动滚动写入输出根目录 logs/recorder.log。"))
        toolbar = QHBoxLayout(); toolbar.setSpacing(8)
        self.clear_button = QPushButton("清空"); self.export_button = QPushButton("导出日志…"); self.auto_scroll = QCheckBox("自动滚动"); self.auto_scroll.setChecked(True)
        toolbar.addWidget(self.clear_button); toolbar.addWidget(self.export_button); toolbar.addWidget(self.auto_scroll); toolbar.addStretch(1)
        layout.addLayout(toolbar)
        from PySide6.QtWidgets import QPlainTextEdit
        self.text = QPlainTextEdit(); self.text.setReadOnly(True); self.text.setMaximumBlockCount(10000)
        self.text.setStyleSheet('font-family: "Cascadia Mono", "Consolas", monospace; font-size: 13px; line-height: 1.35;')
        layout.addWidget(self.text, 1)
        self.clear_button.clicked.connect(self.text.clear)
        self.export_button.clicked.connect(self.export_log)

    def append(self, message: str) -> None:
        self.text.appendPlainText(message)
        if self.auto_scroll.isChecked():
            bar = self.text.verticalScrollBar(); bar.setValue(bar.maximum())

    def export_log(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "导出运行日志", "carmaker_recorder.log", "Log (*.log);;Text (*.txt)")
        if not path: return
        try:
            Path(path).write_text(self.text.toPlainText(), encoding="utf-8")
        except Exception as exc:
            QMessageBox.critical(self, "日志导出失败", str(exc))
