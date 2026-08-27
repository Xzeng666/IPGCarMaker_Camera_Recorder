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
      └─ RingBuffer<Message>  ── dropped/high-watermark telemetry
                         │
                         ▼
               SequentialProcessor
                         │
                         ├─ ImageSaver per camera
                         └─ CameraWriter per camera
                         │
                         ├─ independent preview encoder (Monitor)
                         ├─ disk health check
                         └─ SessionManager
                                 │
                                 ├─ Videos/
                                 ├─ Images/
                                 └─ session_manifest.json
```

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
