from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QLibraryInfo, Qt, QTimer, QTranslator
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
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
from .i18n import LanguageManager
from .pages import (
    AdvancedPage,
    CamerasPage,
    ConnectionPage,
    DashboardPage,
    LogsPage,
    OutputPage,
)
from .widgets import StatusPill
from .workers import ConnectionTestThread, LogEmitter, QtLogHandler, RecorderThread

LOG = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(
        self,
        base_dir: Path,
        config_path: Path,
        parent=None,
        language_manager: LanguageManager | None = None,
    ):
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
        self.i18n = language_manager or LanguageManager()
        self._qt_translator: QTranslator | None = None
        self._apply_qt_translation()

        self.setMinimumSize(1040, 680)
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
        sidebar.setFixedWidth(216)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(18, 22, 14, 18)
        side.setSpacing(8)

        self.brand_label = QLabel()
        self.brand_label.setObjectName("BrandTitle")
        self.brand_subtitle = QLabel()
        self.brand_subtitle.setObjectName("BrandSubtitle")
        self.brand_subtitle.setWordWrap(True)
        side.addWidget(self.brand_label)
        side.addWidget(self.brand_subtitle)
        side.addSpacing(18)

        self.dashboard_page = DashboardPage(self.i18n)
        self.connection_page = ConnectionPage(self.i18n)
        self.output_page = OutputPage(self.i18n, self.base_dir)
        self.cameras_page = CamerasPage(self.i18n)
        self.advanced_page = AdvancedPage(self.i18n)
        self.logs_page = LogsPage(self.i18n)
        self.pages = [
            self.dashboard_page,
            self.connection_page,
            self.output_page,
            self.cameras_page,
            self.advanced_page,
            self.logs_page,
        ]
        self.nav_buttons: list[QPushButton] = []
        for index in range(len(self.pages)):
            button = QPushButton()
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.clicked.connect(lambda checked=False, i=index: self._select_page(i))
            self.nav_buttons.append(button)
            side.addWidget(button)

        side.addStretch(1)

        language_panel = QFrame()
        language_panel.setObjectName("LanguagePanel")
        language_layout = QVBoxLayout(language_panel)
        language_layout.setContentsMargins(11, 10, 11, 11)
        language_layout.setSpacing(7)
        self.language_label = QLabel()
        self.language_label.setObjectName("LanguageLabel")
        self.language_combo = QComboBox()
        self.language_combo.setObjectName("LanguageCombo")
        self.language_combo.addItem("English", "en")
        self.language_combo.addItem("中文", "zh")
        current_language = self.language_combo.findData(self.i18n.language)
        if current_language >= 0:
            self.language_combo.setCurrentIndex(current_language)
        language_layout.addWidget(self.language_label)
        language_layout.addWidget(self.language_combo)
        side.addWidget(language_panel)
        side.addSpacing(10)

        self.version_label = QLabel()
        self.version_label.setObjectName("BrandSubtitle")
        self.version_label.setAlignment(Qt.AlignLeft | Qt.AlignBottom)
        side.addWidget(self.version_label)
        shell.addWidget(sidebar)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("TopBar")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(20, 11, 20, 12)
        header_layout.setSpacing(8)

        # Keep long configuration paths readable at common Windows scale factors.
        config_row = QHBoxLayout()
        config_row.setSpacing(10)
        self.config_title = QLabel()
        self.config_title.setObjectName("MutedLabel")
        self.config_title.setMinimumWidth(116)
        self.config_label = QLabel(self._config_display_text())
        self.config_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.config_label.setWordWrap(True)
        self.config_label.setStyleSheet("font-weight: 600;")
        self.config_label.setToolTip(str(self.config_path))
        config_row.addWidget(self.config_title, 0, Qt.AlignTop)
        config_row.addWidget(self.config_label, 1)
        header_layout.addLayout(config_row)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.status_title = QLabel()
        self.status_title.setObjectName("MutedLabel")
        self.runtime_status = StatusPill(self.i18n, "STOPPED")
        self.load_button = QPushButton()
        self.save_as_button = QPushButton()
        self.save_button = QPushButton()
        self.start_button = QPushButton()
        self.start_button.setObjectName("PrimaryButton")
        self.stop_button = QPushButton()
        self.stop_button.setObjectName("DangerButton")
        self.stop_button.setEnabled(False)
        action_row.addWidget(self.status_title)
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
        self.retranslate_ui()

    def _wire_actions(self) -> None:
        self.load_button.clicked.connect(self.open_config)
        self.save_button.clicked.connect(self.save_current_config)
        self.save_as_button.clicked.connect(self.save_config_as)
        self.start_button.clicked.connect(self.start_recording)
        self.stop_button.clicked.connect(self.stop_recording)
        self.connection_page.test_button.clicked.connect(self.test_connection)
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)

    def _config_display_text(self) -> str:
        try:
            return str(self.config_path.relative_to(self.base_dir))
        except ValueError:
            return str(self.config_path)

    def _update_config_label(self) -> None:
        self.config_label.setText(self._config_display_text())
        self.config_label.setToolTip(str(self.config_path))

    def _on_language_changed(self, index: int) -> None:
        language = self.language_combo.itemData(index)
        if language and self.i18n.set_language(str(language)):
            self._apply_qt_translation()
            self.retranslate_ui()

    def _apply_qt_translation(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        if self._qt_translator is not None:
            app.removeTranslator(self._qt_translator)
            self._qt_translator.deleteLater()
            self._qt_translator = None
        if self.i18n.language != "zh":
            return
        translator = QTranslator(self)
        translations_path = QLibraryInfo.path(QLibraryInfo.TranslationsPath)
        if translator.load("qtbase_zh_CN", translations_path):
            app.installTranslator(translator)
            self._qt_translator = translator

    def retranslate_ui(self) -> None:
        t = self.i18n.text
        self.setWindowTitle(t("window.title"))
        self.brand_label.setText(t("brand.title"))
        self.brand_subtitle.setText(t("brand.subtitle"))
        self.version_label.setText(t("brand.version"))

        nav_keys = [
            "nav.dashboard",
            "nav.connection",
            "nav.output",
            "nav.cameras",
            "nav.advanced",
            "nav.logs",
        ]
        for button, key in zip(self.nav_buttons, nav_keys):
            button.setText(t(key))

        self.language_label.setText(t("language.label"))
        self.language_label.setToolTip(t("language.tooltip"))
        self.language_combo.setToolTip(t("language.tooltip"))
        self.language_combo.setAccessibleName(t("language.accessible_name"))
        self.language_combo.blockSignals(True)
        self.language_combo.setItemText(0, t("language.english"))
        self.language_combo.setItemText(1, t("language.chinese"))
        language_index = self.language_combo.findData(self.i18n.language)
        if language_index >= 0:
            self.language_combo.setCurrentIndex(language_index)
        self.language_combo.blockSignals(False)

        self.config_title.setText(t("header.current_config"))
        self.status_title.setText(t("header.runtime_status"))
        self.load_button.setText(t("action.open_config"))
        self.save_as_button.setText(t("action.save_as"))
        self.save_button.setText(t("action.save"))
        self.start_button.setText(t("action.start"))
        self.stop_button.setToolTip(t("action.stop_tooltip"))
        self.runtime_status.retranslate_ui()
        for page in self.pages:
            page.retranslate_ui()
        self._sync_controls()

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
                LOG.info(
                    "%s", self.i18n.text("log.default_created", path=self.config_path)
                )
            except Exception as exc:
                LOG.error("%s", self.i18n.text("log.default_create_failed", error=exc))
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
                LOG.error("%s", self.i18n.text("log.schema_rejected", error=exc))
                error_message = str(exc)
                QTimer.singleShot(
                    0,
                    lambda message=error_message: QMessageBox.critical(
                        self,
                        self.i18n.text("dialog.config_schema_title"),
                        self.i18n.text("dialog.config_schema_message", message=message),
                    ),
                )
        self._update_config_label()

    def _select_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.nav_buttons[index].setChecked(True)

    def _set_settings_enabled(self, enabled: bool) -> None:
        for page in [
            self.connection_page,
            self.output_page,
            self.cameras_page,
            self.advanced_page,
        ]:
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
        stop_key = (
            "action.stopping"
            if self._stop_requested and self._worker_active()
            else "action.stop"
        )
        self.stop_button.setText(self.i18n.text(stop_key))
        self._set_settings_enabled(policy.settings_enabled)
        # ConnectionPage may be disabled as a whole during recording; keep its
        # explicit child state aligned for when the page becomes enabled again.
        self.connection_page.test_button.setEnabled(policy.connection_test_enabled)
        self.save_action.setEnabled(policy.save_shortcut_enabled)

    def _config_or_error(self) -> AppConfig | None:
        try:
            return collect_from_window(self)
        except Exception as exc:
            QMessageBox.critical(
                self, self.i18n.text("dialog.invalid_config"), str(exc)
            )
            return None

    def save_current_config(self) -> bool:
        config = self._config_or_error()
        if config is None:
            return False
        try:
            save_config(config, self.config_path)
            self._update_config_label()
            self._config_ack_required = False
            LOG.info("%s", self.i18n.text("log.config_saved", path=self.config_path))
            return True
        except Exception as exc:
            QMessageBox.critical(self, self.i18n.text("dialog.save_failed"), str(exc))
            return False

    def save_config_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            self.i18n.text("dialog.save_as"),
            str(self.config_path),
            self.i18n.text("dialog.json_filter"),
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
            self.i18n.text("dialog.open_config"),
            str(self.config_path.parent),
            self.i18n.text("dialog.json_filter"),
        )
        if not path:
            return
        try:
            config = load_config(path)
            self.config_path = Path(path).resolve()
            apply_to_window(self, config)
            self._update_config_label()
            self._config_ack_required = False
            LOG.info("%s", self.i18n.text("log.config_loaded", path=self.config_path))
        except Exception as exc:
            QMessageBox.critical(
                self, self.i18n.text("dialog.config_read_failed"), str(exc)
            )

    def test_connection(self) -> None:
        if self._worker_active():
            QMessageBox.information(
                self,
                self.i18n.text("dialog.capture_running"),
                self.i18n.text("dialog.capture_running_message"),
            )
            return
        if self._connection_test_active or (
            self.connection_test and self.connection_test.isRunning()
        ):
            return
        try:
            host = self.connection_page.host.text().strip()
            ports = parse_ports(self.connection_page.ports.text(), self.i18n.text)
            if not host:
                raise ValueError(self.i18n.text("validation.host_required"))
        except Exception as exc:
            QMessageBox.warning(
                self, self.i18n.text("dialog.invalid_connection"), str(exc)
            )
            return

        self._connection_test_active = True
        self.connection_page.test_status.set_state("STARTING")
        self.connection_test = ConnectionTestThread(
            host, ports, timeout_sec=1.5, parent=self
        )
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
            "%s",
            self.i18n.text(
                "log.connection_test",
                host=self.connection_page.host.text().strip(),
                results=", ".join(
                    f"{port}={'OK' if good else 'FAIL'}"
                    for port, good in results.items()
                ),
            ),
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
                self.i18n.text("dialog.config_confirmation_title"),
                self.i18n.text("dialog.config_confirmation_message"),
            )
            return
        if self._connection_test_active:
            QMessageBox.information(
                self,
                self.i18n.text("dialog.connection_test_active"),
                self.i18n.text("dialog.connection_test_active_message"),
            )
            return
        config = self._config_or_error()
        if config is None:
            return

        try:
            save_config(config, self.config_path)
        except Exception as exc:
            QMessageBox.critical(
                self, self.i18n.text("dialog.runtime_config_save_failed"), str(exc)
            )
            return

        try:
            config.resolve_save_root(self.base_dir).mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            QMessageBox.critical(
                self, self.i18n.text("dialog.output_unavailable"), str(exc)
            )
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
            QMessageBox.critical(
                self, self.i18n.text("dialog.worker_start_failed"), str(exc)
            )
            return
        LOG.info(
            "%s",
            self.i18n.text(
                "log.capture_started",
                host=config.network.host,
                ports=config.network.ports,
                output=config.resolve_save_root(self.base_dir),
            ),
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
        LOG.info("%s", self.i18n.text("log.capture_stopping"))

    def _on_runtime_failed(self, message: str) -> None:
        self._last_runtime_error = message
        self.runtime_status.set_state("ERROR")
        QMessageBox.critical(self, self.i18n.text("dialog.runtime_failed"), message)

    def _on_runtime_finished(self) -> None:
        final_error = self._last_runtime_error
        if final_error is None and self._runtime_component_error:
            final_error = self.i18n.text("log.component_error")
        self.worker = None
        self._worker_launch_pending = False
        self._stop_requested = False
        self.runtime_status.set_state("ERROR" if final_error else "STOPPED")
        self._sync_controls()
        error_suffix = f" | ERROR: {final_error}" if final_error else ""
        LOG.info("%s", self.i18n.text("log.capture_finished", error=error_suffix))

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
                self.i18n.text("dialog.capture_active_close"),
                self.i18n.text("dialog.capture_active_close_message"),
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
                    self.i18n.text("dialog.safe_stop_title"),
                    self.i18n.text("dialog.safe_stop_message"),
                )
                event.ignore()
                return

        if self.connection_test is not None and self.connection_test.isRunning():
            self.connection_test.requestInterruption()
            if not self.connection_test.wait(5000):
                QMessageBox.warning(
                    self,
                    self.i18n.text("dialog.test_stopping_title"),
                    self.i18n.text("dialog.test_stopping_message"),
                )
                event.ignore()
                return

        if self._log_handler is not None:
            logging.getLogger().removeHandler(self._log_handler)
            self._log_handler = None
        event.accept()
