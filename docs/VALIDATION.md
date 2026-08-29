# Validation

Run:

```bash
python verify_project.py
```

Automated coverage includes:

- strict schema rejection of missing/unknown/old fields
- protocol header/payload parsing and resynchronization
- stoppable blocking recv/reconnect
- independent multi-port disconnect behavior
- 30 FPS → 30 Hz exact image sampling loopback
- BGR→RGB PPM and G16 big-endian PGM
- RGB/BGR/G8/G16 decoder matrix
- RingBuffer dropped/high-watermark visibility
- Image Writer failure propagation
- Video resolution-change segmentation
- bounded video time-gap handling
- Session directory uniqueness and Manifest generation
- disk preflight failure
- GUI control policy and static signal bindings
- system-language fallback, language preference persistence, and live interface switching
- optional real Qt mouse Start→Stop test when PySide6 is installed
- optional offscreen GUI smoke test in `verify_project.py`
- packaged Windows GUI smoke test after `scripts/windows/build.ps1`

The current non-Qt validation environment cannot certify Windows DPI rendering or a produced Windows EXE. Those two checks are intentionally executed by the Windows/Qt workflows rather than reported as locally passed.
