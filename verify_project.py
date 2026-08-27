from __future__ import annotations

import compileall
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

from carmaker_recorder.config import SCHEMA_VERSION, load_config

ROOT = Path(__file__).resolve().parent


def _run(command: list[str], *, env=None, timeout: float | None = None) -> int:
    result = subprocess.run(command, cwd=ROOT, check=False, env=env, timeout=timeout)
    return int(result.returncode)


def main() -> int:
    print("CarMaker CameraRSI Recorder - Project Verification")
    print(f"Python: {sys.version.split()[0]}")

    print("\n[1/5] Compiling Python sources...")
    if not compileall.compile_dir(ROOT / "carmaker_recorder", quiet=1):
        print("Core compile FAILED")
        return 1
    # GUI compile does not import PySide6 and is safe on core-only machines.
    if not compileall.compile_dir(ROOT / "carmaker_gui", quiet=1):
        print("GUI compile FAILED")
        return 1
    print("Compile: OK")

    print("\n[2/5] Validating config.json against the strict current schema...")
    try:
        config = load_config(ROOT / "config.json")
    except Exception as exc:
        print(f"Config validation FAILED: {exc}")
        return 1
    if config.schema_version != SCHEMA_VERSION:
        print(f"Config schema mismatch: {config.schema_version} != {SCHEMA_VERSION}")
        return 1
    print(f"Config schema v{SCHEMA_VERSION}: OK")

    print("\n[3/5] Checking dependencies...")
    for module in ("numpy", "cv2", "PySide6"):
        status = "OK" if importlib.util.find_spec(module) else "MISSING"
        print(f"Dependency {module}: {status}")
    for required in ("numpy", "cv2"):
        if not importlib.util.find_spec(required):
            print(f"Required core dependency missing: {required}")
            return 1

    print("\n[4/5] Running automated tests...")
    rc = _run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
    if rc:
        print("Unit/integration tests FAILED")
        return rc

    print("\n[5/5] Running real Qt offscreen smoke test when PySide6 is available...")
    if importlib.util.find_spec("PySide6"):
        env = os.environ.copy()
        env.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            rc = _run(
                [sys.executable, "run_gui.py", "--smoke-test", "--config", "config.json"],
                env=env,
                timeout=15,
            )
        except subprocess.TimeoutExpired:
            print("Qt smoke test FAILED: timeout")
            return 1
        if rc:
            print(f"Qt smoke test FAILED: exit code {rc}")
            return rc
        print("Qt smoke test: OK")
    else:
        print("Qt smoke test: SKIPPED (PySide6 is not installed in this environment)")

    print("\nVerification PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
