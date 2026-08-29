from __future__ import annotations

from collections.abc import Callable

from carmaker_recorder.config import (
    SCHEMA_VERSION,
    AppConfig,
    config_from_dict,
    config_to_dict,
)


def parse_ports(text: str, translate: Callable[..., str] | None = None) -> list[int]:
    messages = {
        "validation.duplicate_port": "Duplicate RSDS port: {port}",
        "validation.port_required": "Enter at least one RSDS port, for example 2210.",
    }

    def message(key: str, **values) -> str:
        if translate is not None:
            return translate(key, **values)
        return messages[key].format(**values)

    normalized = text.replace(";", ",").replace("，", ",").replace(" ", ",")
    ports: list[int] = []
    for token in normalized.split(","):
        token = token.strip()
        if not token:
            continue
        port = int(token)
        if port in ports:
            raise ValueError(message("validation.duplicate_port", port=port))
        ports.append(port)
    if not ports:
        raise ValueError(message("validation.port_required"))
    return ports


def collect_from_window(window) -> AppConfig:
    camera_names: dict[str, str] = {}
    table = window.cameras_page.table
    for row in range(table.rowCount()):
        id_item = table.item(row, 0)
        name_item = table.item(row, 1)
        if id_item is None or name_item is None:
            continue
        cam_id = id_item.text().strip()
        name = name_item.text().strip()
        if not cam_id or not name:
            continue
        int(cam_id)
        if cam_id in camera_names:
            raise ValueError(
                window.i18n.text("validation.duplicate_camera", camera_id=cam_id)
            )
        camera_names[cam_id] = name

    raw = {
        "schema_version": SCHEMA_VERSION,
        "network": {
            "host": window.connection_page.host.text().strip(),
            "ports": parse_ports(window.connection_page.ports.text()),
            "socket_timeout_sec": window.advanced_page.socket_timeout.value(),
            "connect_timeout_sec": window.advanced_page.connect_timeout.value(),
            "reconnect_delay_sec": window.advanced_page.reconnect_delay.value(),
            "max_timeouts_before_reconnect": window.advanced_page.max_timeouts.value(),
            "header_size": window.advanced_page.header_size.value(),
            "max_payload_bytes": window.advanced_page.max_payload_mb.value()
            * 1024
            * 1024,
        },
        "buffers": {
            "message_capacity": window.advanced_page.message_capacity.value(),
            "frame_capacity": window.advanced_page.frame_capacity.value(),
            "image_task_capacity": window.advanced_page.image_capacity.value(),
        },
        "video": {
            "enabled": window.connection_page.video_enabled.isChecked(),
            "fps": window.connection_page.video_fps.value(),
            "fourcc": window.advanced_page.fourcc.text().strip().upper(),
            "extension": window.advanced_page.video_extension.text()
            .strip()
            .lstrip("."),
            "max_gap_fill_frames": window.advanced_page.max_gap_fill_frames.value(),
        },
        "images": {
            "enabled": window.connection_page.images_enabled.isChecked(),
            "sample_hz": window.connection_page.image_hz.value(),
            "export_format": window.connection_page.image_format.currentText(),
            "jpeg_quality": window.connection_page.jpeg_quality.value(),
        },
        "reliability": {
            "writer_failure_policy": window.advanced_page.writer_failure_policy.currentData(),
            "min_free_disk_gb": window.advanced_page.min_free_disk_gb.value(),
            "disk_check_interval_sec": window.advanced_page.disk_check_interval.value(),
            "mark_degraded_on_drop": window.advanced_page.mark_degraded_on_drop.isChecked(),
            "sim_time_reset_threshold_sec": window.advanced_page.sim_reset_threshold.value(),
        },
        "logging": {
            "level": window.advanced_page.log_level.currentText(),
            "max_bytes": window.advanced_page.log_max_mb.value() * 1024 * 1024,
            "backup_count": window.advanced_page.log_backups.value(),
        },
        "output": {
            "save_root": window.output_page.save_root.text(),
            "camera_names": camera_names,
        },
        "gui": {
            "live_preview": window.connection_page.gui_preview.isChecked(),
            "preview_hz": window.advanced_page.preview_hz.value(),
        },
    }
    return config_from_dict(raw)


def apply_to_window(window, config: AppConfig) -> None:
    raw = config_to_dict(config)
    net = raw["network"]
    window.connection_page.host.setText(net["host"])
    window.connection_page.ports.setText(", ".join(str(p) for p in net["ports"]))

    video = raw["video"]
    window.connection_page.video_enabled.setChecked(video["enabled"])
    window.connection_page.video_fps.setValue(float(video["fps"]))

    images = raw["images"]
    window.connection_page.images_enabled.setChecked(images["enabled"])
    window.connection_page.image_hz.setValue(float(images["sample_hz"]))
    idx = window.connection_page.image_format.findText(images["export_format"])
    if idx >= 0:
        window.connection_page.image_format.setCurrentIndex(idx)
    window.connection_page.jpeg_quality.setValue(int(images["jpeg_quality"]))

    output = raw["output"]
    window.output_page.save_root.setText(output["save_root"])
    window.cameras_page.set_mapping(output["camera_names"])

    buffers = raw["buffers"]
    adv = window.advanced_page
    adv.message_capacity.setValue(int(buffers["message_capacity"]))
    adv.frame_capacity.setValue(int(buffers["frame_capacity"]))
    adv.image_capacity.setValue(int(buffers["image_task_capacity"]))
    adv.socket_timeout.setValue(float(net["socket_timeout_sec"]))
    adv.connect_timeout.setValue(float(net["connect_timeout_sec"]))
    adv.max_timeouts.setValue(int(net["max_timeouts_before_reconnect"]))
    adv.reconnect_delay.setValue(float(net["reconnect_delay_sec"]))
    adv.header_size.setValue(int(net["header_size"]))
    adv.max_payload_mb.setValue(
        max(1, int(round(net["max_payload_bytes"] / (1024 * 1024))))
    )
    adv.fourcc.setText(video["fourcc"])
    adv.video_extension.setText(video["extension"])
    adv.max_gap_fill_frames.setValue(int(video["max_gap_fill_frames"]))
    reliability = raw["reliability"]
    policy_index = adv.writer_failure_policy.findData(
        reliability["writer_failure_policy"]
    )
    if policy_index >= 0:
        adv.writer_failure_policy.setCurrentIndex(policy_index)
    adv.min_free_disk_gb.setValue(float(reliability["min_free_disk_gb"]))
    adv.disk_check_interval.setValue(float(reliability["disk_check_interval_sec"]))
    adv.mark_degraded_on_drop.setChecked(bool(reliability["mark_degraded_on_drop"]))
    adv.sim_reset_threshold.setValue(float(reliability["sim_time_reset_threshold_sec"]))

    log_cfg = raw["logging"]
    adv.log_level.setCurrentText(log_cfg["level"])
    adv.log_max_mb.setValue(max(1, int(round(log_cfg["max_bytes"] / (1024 * 1024)))))
    adv.log_backups.setValue(int(log_cfg["backup_count"]))

    gui = raw["gui"]
    window.connection_page.gui_preview.setChecked(bool(gui["live_preview"]))
    adv.preview_hz.setValue(float(gui["preview_hz"]))
