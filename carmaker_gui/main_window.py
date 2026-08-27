from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from carmaker_recorder.config import AppConfig, load_config, save_config

from .config_adapter import apply_to_window, collect_from_window, parse_ports
from .control_state import control_policy
from .pages import (
    AdvancedPage,
    CamerasPage,
    ConnectionPage,
    DashboardPage,
    LogsPage,
    OutputPage,
)
from .theme import COLORS
from .widgets import StatusPill
from .workers import ConnectionTestThread, LogEmitter, QtLogHandler, RecorderThread

LOG = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, base_dir: Path, config_path: Path, parent=None):
        super().__init__(parent)
        self.base_dir = Path(base_dir).resolve()
        self.config_path = Path(config_path).resolve()
        self.worker: RecorderThread | None = None
        self.connection_test: ConnectionTestThread | None = None
        self._log_handler: QtLogHandler | None = None
        self._worker_launch_pending = False
        self._stop_requested = False
        self._connection_test_active = False
        self._last_runtime_error: str | None = None
        self._runtime_component_error = False
        self._config_ack_required = False

        self.setWindowTitle("CarMaker CameraRSI Recorder v1.4")
        self.setMinimumSize(900, 620)
        self.resize(1320, 840)

        self._build_ui()
        self._install_logging()
        self._load_initial_config()
        self._wire_actions()

        self.monitor_timer = QTimer(self)
        self.monitor_timer.setInterval(450)
        self.monitor_timer.timeout.connect(self._refresh_runtime)
        self.monitor_timer.start()

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("AppRoot")
        self.setCentralWidget(root)
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(200)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(18, 22, 14, 18)
        side.setSpacing(8)

        brand = QLabel("CarMaker Recorder")
        brand.setObjectName("BrandTitle")
        sub = QLabel("CameraRSI · RSDS Capture")
        sub.setObjectName("BrandSubtitle")
        side.addWidget(brand)
        side.addWidget(sub)
        side.addSpacing(18)

        self.dashboard_page = DashboardPage()
        self.connection_page = ConnectionPage()
        self.output_page = OutputPage(self.base_dir)
        self.cameras_page = CamerasPage()
        self.advanced_page = AdvancedPage()
        self.logs_page = LogsPage()
        self.pages = [
            self.dashboard_page,
            self.connection_page,
            self.output_page,
            self.cameras_page,
            self.advanced_page,
            self.logs_page,
        ]
        labels = ["采集监控", "连接与采集", "采集输出", "Camera 映射", "高级设置", "运行日志"]
        self.nav_buttons: list[QPushButton] = []
        for index, label in enumerate(labels):
            button = QPushButton(label)
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.clicked.connect(lambda checked=False, i=index: self._select_page(i))
            self.nav_buttons.append(button)
            side.addWidget(button)

        side.addStretch(1)
        version = QLabel("GUI Edition 1.4\nMulti-Camera Recorder")
        version.setObjectName("BrandSubtitle")
        version.setAlignment(Qt.AlignLeft | Qt.AlignBottom)
        side.addWidget(version)
        shell.addWidget(sidebar)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        header = QFrame()
        header.setStyleSheet(
            f"QFrame {{ background: {COLORS['panel']}; border-bottom: 1px solid {COLORS['border_soft']}; }}"
        )
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(20, 11, 20, 12)
        header_layout.setSpacing(8)

        # Keep long configuration paths readable at common Windows scale factors.
        config_row = QHBoxLayout()
        config_row.setSpacing(10)
        config_title = QLabel("当前配置")
        config_title.setObjectName("MutedLabel")
        config_title.setMinimumWidth(72)
        self.config_label = QLabel(str(self.config_path))
        self.config_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.config_label.setWordWrap(True)
        self.config_label.setStyleSheet("font-weight: 600;")
        self.config_label.setToolTip(str(self.config_path))
        config_row.addWidget(config_title, 0, Qt.AlignTop)
        config_row.addWidget(self.config_label, 1)
        header_layout.addLayout(config_row)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        status_title = QLabel("运行状态")
        status_title.setObjectName("MutedLabel")
        self.runtime_status = StatusPill("STOPPED")
        self.load_button = QPushButton("打开配置")
        self.save_as_button = QPushButton("另存配置")
        self.save_button = QPushButton("保存配置")
        self.start_button = QPushButton("启动采集")
        self.start_button.setObjectName("PrimaryButton")
        self.stop_button = QPushButton("停止")
        self.stop_button.setObjectName("DangerButton")
        self.stop_button.setEnabled(False)
        self.stop_button.setToolTip("采集线程启动后可用；停止时会等待视频/图片写盘安全结束。")
        action_row.addWidget(status_title)
        action_row.addWidget(self.runtime_status)
        action_row.addStretch(1)
        action_row.addWidget(self.load_button)
        action_row.addWidget(self.save_as_button)
        action_row.addWidget(self.save_button)
        action_row.addWidget(self.start_button)
        action_row.addWidget(self.stop_button)
        header_layout.addLayout(action_row)
        right_layout.addWidget(header)

        self.stack = QStackedWidget()
        for page in self.pages:
            if page is self.logs_page:
                self.stack.addWidget(page)
            else:
                scroll = QScrollArea()
                scroll.setWidgetResizable(True)
                scroll.setFrameShape(QFrame.NoFrame)
                scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                scroll.setWidget(page)
                self.stack.addWidget(scroll)
        right_layout.addWidget(self.stack, 1)
        shell.addWidget(right, 1)

        self.nav_buttons[0].setChecked(True)
        self.stack.setCurrentIndex(0)

        # Standard shortcuts without adding menu chrome.
        self.save_action = QAction(self)
        self.save_action.setShortcut("Ctrl+S")
        self.save_action.triggered.connect(self.save_current_config)
        self.addAction(self.save_action)

    def _wire_actions(self) -> None:
        self.load_button.clicked.connect(self.open_config)
        self.save_button.clicked.connect(self.save_current_config)
        self.save_as_button.clicked.connect(self.save_config_as)
        self.start_button.clicked.connect(self.start_recording)
        self.stop_button.clicked.connect(self.stop_recording)
        self.connection_page.test_button.clicked.connect(self.test_connection)

    def _install_logging(self) -> None:
        self.log_emitter = LogEmitter(self)
        self.log_emitter.message.connect(self._append_log)
        handler = QtLogHandler(self.log_emitter)
        handler.setLevel(logging.INFO)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-7s | %(threadName)s | %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)
        self._log_handler = handler

    def _append_log(self, message: str, level: int) -> None:
        self.logs_page.append(message)
        if level >= logging.ERROR:
            if self._worker_active():
                self._runtime_component_error = True
            self.runtime_status.set_state("ERROR")

    def _load_initial_config(self) -> None:
        if not self.config_path.exists():
            config = AppConfig()
            try:
                save_config(config, self.config_path)
                LOG.info("已创建 v1.4 默认配置: %s", self.config_path)
            except Exception as exc:
                LOG.error("创建默认配置失败: %s", exc)
            apply_to_window(self, config)
            self._config_ack_required = False
        else:
            try:
                config = load_config(self.config_path)
                apply_to_window(self, config)
                self._config_ack_required = False
            except Exception as exc:
                # Do not migrate or silently accept an older/partial configuration.
                # Latest defaults are shown only as an editable recovery form; the
                # operator must explicitly Save/Save As before Start is permitted.
                apply_to_window(self, AppConfig())
                self._config_ack_required = True
                LOG.error("当前配置不符合 v1.4 schema，未载入: %s", exc)
                error_message = str(exc)
                QTimer.singleShot(0, lambda message=error_message: QMessageBox.critical(
                    self,
                    "配置不符合 v1.4",
                    f"配置文件未被载入，也不会自动迁移。\n\n{message}\n\n"
                    "界面已显示 v1.4 最新默认值。请检查后执行‘保存配置’或‘另存配置’，再启动采集。",
                ))
        self.config_label.setText(str(self.config_path))
        self.config_label.setToolTip(str(self.config_path))

    def _select_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.nav_buttons[index].setChecked(True)

    def _set_settings_enabled(self, enabled: bool) -> None:
        for page in [self.connection_page, self.output_page, self.cameras_page, self.advanced_page]:
            page.setEnabled(enabled)
        self.load_button.setEnabled(enabled)
        self.save_as_button.setEnabled(enabled)
        self.save_button.setEnabled(enabled)

    def _worker_active(self) -> bool:
        # The worker reference is the UI ownership token. Do not unlock controls
        # merely because QThread.isRunning() has already turned False: the queued
        # finished signal may not have been processed yet. Unlocking in that gap
        # could allow a new worker to start and then be cleared by the old worker's
        # late finished handler.
        return self.worker is not None

    def _sync_controls(self) -> None:
        policy = control_policy(
            worker_active=self._worker_active(),
            stop_requested=self._stop_requested,
            connection_test_active=self._connection_test_active,
        )
        self.start_button.setEnabled(policy.start_enabled)
        self.stop_button.setEnabled(policy.stop_enabled)
        self.stop_button.setText("正在停止…" if self._stop_requested and self._worker_active() else "停止")
        self._set_settings_enabled(policy.settings_enabled)
        # ConnectionPage may be disabled as a whole during recording; keep its
        # explicit child state aligned for when the page becomes enabled again.
        self.connection_page.test_button.setEnabled(policy.connection_test_enabled)
        self.save_action.setEnabled(policy.save_shortcut_enabled)

    def _config_or_error(self) -> AppConfig | None:
        try:
            return collect_from_window(self)
        except Exception as exc:
            QMessageBox.critical(self, "配置无效", str(exc))
            return None

    def save_current_config(self) -> bool:
        config = self._config_or_error()
        if config is None:
            return False
        try:
            save_config(config, self.config_path)
            self.config_label.setText(str(self.config_path))
            self.config_label.setToolTip(str(self.config_path))
            self._config_ack_required = False
            LOG.info("配置已保存: %s", self.config_path)
            return True
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return False

    def save_config_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "另存配置",
            str(self.config_path),
            "JSON Config (*.json)",
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        self.config_path = Path(path).resolve()
        self.save_current_config()

    def open_config(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "打开 Recorder 配置",
            str(self.config_path.parent),
            "JSON Config (*.json)",
        )
        if not path:
            return
        try:
            config = load_config(path)
            self.config_path = Path(path).resolve()
            apply_to_window(self, config)
            self.config_label.setText(str(self.config_path))
            self.config_label.setToolTip(str(self.config_path))
            self._config_ack_required = False
            LOG.info("已载入配置: %s", self.config_path)
        except Exception as exc:
            QMessageBox.critical(self, "配置读取失败", str(exc))

    def test_connection(self) -> None:
        if self._worker_active():
            QMessageBox.information(self, "采集正在运行", "请先停止采集，再执行独立 TCP 连通性测试。")
            return
        if self._connection_test_active or (self.connection_test and self.connection_test.isRunning()):
            return
        try:
            host = self.connection_page.host.text().strip()
            ports = parse_ports(self.connection_page.ports.text())
            if not host:
                raise ValueError("主机 / IP 不能为空")
        except Exception as exc:
            QMessageBox.warning(self, "连接参数无效", str(exc))
            return

        self._connection_test_active = True
        self.connection_page.test_status.set_state("STARTING")
        self.connection_test = ConnectionTestThread(host, ports, timeout_sec=1.5, parent=self)
        self.connection_test.result.connect(self._on_connection_test)
        self.connection_test.finished.connect(self._on_connection_test_finished)
        self._sync_controls()
        self.connection_test.start()

    def _on_connection_test(self, results: dict) -> None:
        ok = sum(1 for v in results.values() if v)
        total = len(results)
        if ok == total and total:
            self.connection_page.test_status.set_state("CONNECTED")
        elif ok:
            self.connection_page.test_status.set_state("WAITING")
        else:
            self.connection_page.test_status.set_state("DISCONNECTED")
        LOG.info(
            "TCP 连通性测试 %s: %s",
            self.connection_page.host.text().strip(),
            ", ".join(f"{p}={'OK' if good else 'FAIL'}" for p, good in results.items()),
        )

    def _on_connection_test_finished(self) -> None:
        self._connection_test_active = False
        if self.connection_test is not None:
            self.connection_test.deleteLater()
        self.connection_test = None
        self._sync_controls()

    def start_recording(self) -> None:
        if self._worker_active():
            return
        if self._config_ack_required:
            QMessageBox.warning(
                self,
                "需要确认 v1.4 配置",
                "当前配置文件未通过 v1.4 schema 校验。请先检查界面参数并保存为最新配置，再启动采集。",
            )
            return
        if self._connection_test_active:
            QMessageBox.information(self, "连接测试进行中", "TCP 连通性测试结束后再启动正式采集。")
            return
        config = self._config_or_error()
        if config is None:
            return

        try:
            save_config(config, self.config_path)
        except Exception as exc:
            QMessageBox.critical(self, "无法保存运行配置", str(exc))
            return

        try:
            config.resolve_save_root(self.base_dir).mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            QMessageBox.critical(self, "输出目录不可用", str(exc))
            return

        worker = RecorderThread(
            config,
            self.base_dir,
            capture_previews=config.gui.live_preview,
            parent=self,
        )
        self.worker = worker
        self._worker_launch_pending = True
        self._stop_requested = False
        self._last_runtime_error = None
        self._runtime_component_error = False
        worker.started.connect(self._on_runtime_started)
        worker.failed.connect(self._on_runtime_failed)
        # Re-enable Start only after the worker thread has completely stopped.
        worker.finished.connect(self._on_runtime_finished)
        worker.finished.connect(worker.deleteLater)

        self.runtime_status.set_state("STARTING")
        self._sync_controls()
        self._select_page(0)
        try:
            worker.start()
        except Exception as exc:
            self.worker = None
            self._worker_launch_pending = False
            self._stop_requested = False
            self.runtime_status.set_state("ERROR")
            self._sync_controls()
            QMessageBox.critical(self, "无法启动采集线程", str(exc))
            return
        LOG.info(
            "启动采集 | host=%s | ports=%s | output=%s",
            config.network.host,
            config.network.ports,
            config.resolve_save_root(self.base_dir),
        )

    def _on_runtime_started(self) -> None:
        self._worker_launch_pending = False
        self._sync_controls()

    def stop_recording(self) -> None:
        if not self._worker_active() or self.worker is None:
            self._sync_controls()
            return
        if self._stop_requested:
            return
        self._stop_requested = True
        self.runtime_status.set_state("STOPPING")
        self._sync_controls()
        self.worker.stop()
        LOG.info("正在停止采集：已中断 RSDS socket，等待视频和图片安全写入…")

    def _on_runtime_failed(self, message: str) -> None:
        self._last_runtime_error = message
        self.runtime_status.set_state("ERROR")
        QMessageBox.critical(self, "采集运行失败", message)

    def _on_runtime_finished(self) -> None:
        final_error = self._last_runtime_error
        if final_error is None and self._runtime_component_error:
            final_error = "采集组件记录到错误，请查看运行日志"
        self.worker = None
        self._worker_launch_pending = False
        self._stop_requested = False
        self.runtime_status.set_state("ERROR" if final_error else "STOPPED")
        self._sync_controls()
        LOG.info("采集任务已结束%s", f" | ERROR: {final_error}" if final_error else "")

    def _refresh_runtime(self) -> None:
        if self.worker is None:
            self._sync_controls()
            return
        snapshot = self.worker.monitor.snapshot()
        state = snapshot.get("state", "STOPPED")
        # A failure dialog should not be immediately hidden by the monitor's
        # final STOPPED transition; controls still become available via finished.
        if not self._last_runtime_error and not self._runtime_component_error:
            self.runtime_status.set_state(state)
        else:
            self.runtime_status.set_state("ERROR")
        self.dashboard_page.update_snapshot(snapshot)
        self._sync_controls()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self._worker_active() and self.worker is not None:
            answer = QMessageBox.question(
                self,
                "采集仍在运行",
                "关闭程序前需要停止采集并完成写盘。是否停止并退出？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            self._stop_requested = True
            self.runtime_status.set_state("STOPPING")
            self._sync_controls()
            self.worker.stop()
            if not self.worker.wait(15000):
                QMessageBox.warning(
                    self,
                    "仍在安全停止",
                    "后台仍在完成视频或图片写盘。为避免文件损坏，本次暂不强制退出；请稍后再次关闭。",
                )
                event.ignore()
                return

        if self.connection_test is not None and self.connection_test.isRunning():
            self.connection_test.requestInterruption()
            if not self.connection_test.wait(5000):
                QMessageBox.warning(self, "连接测试仍在结束", "TCP 测试线程尚未退出，请稍后再次关闭。")
                event.ignore()
                return

        if self._log_handler is not None:
            logging.getLogger().removeHandler(self._log_handler)
            self._log_handler = None
        event.accept()
