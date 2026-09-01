# Configuration Reference

`config.json` uses strict `schema_version: 5`. Missing keys, unknown keys and old keys are rejected.

## network

- `host`: CarMaker/MovieNX host/IP.
- `ports`: one or more unique TCP ports.
- `socket_timeout_sec`: connected read timeout.
- `connect_timeout_sec`: connect timeout.
- `reconnect_delay_sec`: independent port retry delay.
- `max_timeouts_before_reconnect`: consecutive timeouts before reconnect.
- `header_size`: RSDS fixed Header size; CarMaker 15 example is 64.
- `max_payload_bytes`: safety ceiling for one RSDS payload. Default 256 MiB.

## buffers

- `message_capacity`: all receiver → processor queue.
- `frame_capacity`: per-camera video queue.
- `image_task_capacity`: per-camera image queue.

Queue full policy is overwrite-oldest + explicit dropped telemetry.

## video

- `enabled`
- `fps`
- `backend`: `auto|opencv|nvenc|qsv|amf`. `auto` probes hardware encoders in that order and uses the first working option.
- `codec`: `h264|hevc|av1` for the FFmpeg hardware path.
- `bitrate_mbps`: target bitrate for the FFmpeg hardware path.
- `allow_cpu_fallback`: use OpenCV when the configured hardware path is unavailable.
- `ffmpeg_path`: executable name or file path used for hardware probing and encoding.
- `fourcc`: four-character codec used only by the OpenCV path.
- `extension`
- `max_gap_fill_frames`: gap larger than this starts a new segment.

Hardware availability is verified with a short FFmpeg encoder probe, rather than inferred from an encoder name alone. The selected backend is recorded per camera in the session manifest. FFmpeg receives BGR frames through a raw-video pipe, so hardware mode offloads encoding but still includes one host-memory transfer into FFmpeg.

## images

- `enabled`
- `sample_hz`: independent image cadence.
- `export_format`: `auto|ppm|g8|g16|raw|jpg`.
- `jpeg_quality`: 1..100.

Pixel channel conversion is automatic; there is no manual RGB/BGR compatibility switch.

## reliability

- `writer_failure_policy`: `stop` or `degraded`.
- `min_free_disk_gb`
- `disk_check_interval_sec`
- `mark_degraded_on_drop`
- `sim_time_reset_threshold_sec`: per `(port, CameraID)` rollback threshold.

## logging

- `level`: `DEBUG|INFO|WARNING|ERROR`
- `max_bytes`: rotating log size.
- `backup_count`

## output

- `save_root`
- `camera_names`: numeric CameraRSI ID → unique filesystem-safe display/output name.

## gui

- `live_preview`
- `preview_hz`: preview only; it does not affect stored data cadence.
