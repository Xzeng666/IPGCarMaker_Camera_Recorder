from __future__ import annotations

from pathlib import Path

from .config import AppConfig
from .runtime import RecorderRuntime


def run(config: AppConfig, base_dir: Path) -> None:
    """CLI-compatible blocking entry point."""
    runtime = RecorderRuntime(config, base_dir)
    try:
        runtime.run()
    except KeyboardInterrupt:
        runtime.stop()
