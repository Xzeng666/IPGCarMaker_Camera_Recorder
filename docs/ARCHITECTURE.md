# Architecture

## Runtime data flow

```text
CarMaker / MovieNX
      │
      │ RSDS TCP (one receiver per port)
      ▼
NetworkReceiver[port]
      │
      ├─ payload safety limit
      ├─ reconnect independently
      ├─ owned bytearray payload (no bytearray → bytes copy)
      └─ RingBuffer<Message>  ── dropped/high-watermark telemetry
                         │
                         ▼
               SequentialProcessor
                         │
                         ├─ ImageSaver per camera
                         └─ CameraWriter per camera
                                └─ FFmpeg hardware encoder or OpenCV fallback
                         │
                         ├─ independent preview encoder (Monitor)
                         ├─ disk health check
                         └─ SessionManager
                                 │
                                 ├─ Videos/
                                 ├─ Images/
                                 └─ session_manifest.json
```

The CPU owns TCP/RSDS parsing, routing, session lifecycle, filesystem operations, telemetry, and the GUI. Video encoding can be delegated to NVENC, Intel QSV, or AMD AMF through FFmpeg. Native BGR CameraRSI payloads are exposed to NumPy as read-only views; RGB and grayscale inputs still require CPU conversion before encoding.

Hardware detection runs a short encode probe and caches the result. This prevents an encoder compiled into FFmpeg but unusable on the current GPU or driver from being treated as available. The selected backend is stored in per-camera telemetry and the final manifest.

## Failure domains

- RSDS ports reconnect independently.
- Message RingBuffer overflow does not block TCP but is counted.
- Video/Image queue overflow is counted per camera.
- Writer failure policy is explicit: `stop` or `degraded`.
- Disk below minimum is fatal.
- Same RSDS stream simulation-time rollback is fatal.
- Different camera/port sim-times are never compared against one global maximum.

## Thread ownership

GUI does not spawn the CLI as a subprocess. It creates a `RecorderThread`, which owns a `RecorderRuntime`. Runtime owns NetworkReceiver threads and SequentialProcessor; Processor owns writers. UI status is read from one thread-safe `RecorderMonitor`.

The UI only returns to Start-enabled state after the `QThread.finished` event, preventing a previous run's late completion signal from clearing a newer worker.
